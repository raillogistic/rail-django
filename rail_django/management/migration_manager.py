"""
Schema migration management module.

This module provides comprehensive schema migration planning, execution,
and rollback capabilities for GraphQL schemas.
"""

import hashlib
import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.db import transaction
from graphql import GraphQLSchema, build_ast_schema, print_schema

from ..introspection import BreakingChangeLevel, ChangeType, SchemaComparator, SchemaComparison
from ..validation import SchemaValidator

logger = logging.getLogger(__name__)


class MigrationType(Enum):
    """Types of schema migrations."""
    MAJOR = "major"          # Breaking changes
    MINOR = "minor"          # Non-breaking additions
    PATCH = "patch"          # Bug fixes, no schema changes
    ROLLBACK = "rollback"    # Rollback to previous version


class MigrationStatus(Enum):
    """Migration execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationStep:
    """Individual migration step."""
    step_id: str
    description: str
    operation: str  # 'add_type', 'remove_field', 'modify_field', etc.
    target: str     # Target element (type, field, etc.)
    details: Dict[str, Any] = field(default_factory=dict)
    is_breaking: bool = False
    rollback_operation: Optional[str] = None
    rollback_details: Optional[Dict[str, Any]] = None


@dataclass
class SchemaMigration:
    """Represents a schema migration."""
    migration_id: str
    from_version: str
    to_version: str
    migration_type: MigrationType
    status: MigrationStatus
    created_at: datetime
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    executed_by: Optional[str] = None
    description: str = ""
    steps: List[MigrationStep] = field(default_factory=list)
    breaking_changes: List[str] = field(default_factory=list)
    rollback_migration_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_log: List[str] = field(default_factory=list)


@dataclass
class MigrationPlan:
    """Migration execution plan."""
    plan_id: str
    schema_name: str
    migrations: List[SchemaMigration] = field(default_factory=list)
    total_steps: int = 0
    breaking_changes_count: int = 0
    estimated_duration_minutes: float = 0.0
    requires_downtime: bool = False
    rollback_plan: Optional['MigrationPlan'] = None
    dependencies: List[str] = field(default_factory=list)
    pre_migration_checks: List[str] = field(default_factory=list)
    post_migration_checks: List[str] = field(default_factory=list)


@dataclass
class MigrationResult:
    """Migration execution result."""
    migration_id: str
    success: bool
    duration_seconds: float
    steps_completed: int
    steps_failed: int
    error_message: Optional[str] = None
    rollback_required: bool = False
    rollback_migration_id: Optional[str] = None


class MigrationManager:
    """
    Comprehensive schema migration management system.

    Handles migration planning, execution, rollback, and validation
    for GraphQL schema changes.
    """

    def __init__(self,
                 schema_comparator: SchemaComparator = None,
                 validator: SchemaValidator = None,
                 migration_storage_path: str = None,
                 enable_auto_rollback: bool = True,
                 max_migration_time_minutes: int = 60,
                 enable_dry_run: bool = True):

        self.schema_comparator = schema_comparator or SchemaComparator()
        self.validator = validator or SchemaValidator()
        self.migration_storage_path = Path(migration_storage_path or "migrations")
        self.enable_auto_rollback = enable_auto_rollback
        self.max_migration_time_minutes = max_migration_time_minutes
        self.enable_dry_run = enable_dry_run

        # Migration storage
        self._migrations: Dict[str, SchemaMigration] = {}
        self._migration_plans: Dict[str, MigrationPlan] = {}
        self._execution_history: List[MigrationResult] = []

        # Migration hooks
        self._pre_migration_hooks: List[Callable] = []
        self._post_migration_hooks: List[Callable] = []
        self._step_hooks: Dict[str, List[Callable]] = defaultdict(list)

        # Thread safety
        self._lock = threading.RLock()

        # Ensure migration storage directory exists
        self.migration_storage_path.mkdir(parents=True, exist_ok=True)

        # Load existing migrations
        self._load_migrations()

        self.logger = logging.getLogger(__name__)

    def create_migration(self,
                         schema_name: str,
                         from_schema: GraphQLSchema,
                         to_schema: GraphQLSchema,
                         from_version: str,
                         to_version: str,
                         description: str = "",
                         user_id: str = None) -> SchemaMigration:
        """
        Create a migration between two schema versions.

        Args:
            schema_name: Name of the schema
            from_schema: Source schema
            to_schema: Target schema
            from_version: Source version
            to_version: Target version
            description: Migration description
            user_id: User creating the migration

        Returns:
            Created migration
        """
        # Compare schemas
        comparison = self.schema_comparator.compare_schemas(from_schema, to_schema)

        # Determine migration type
        migration_type = self._determine_migration_type(comparison)

        # Generate migration ID
        migration_id = self._generate_migration_id(
            schema_name, from_version, to_version
        )

        # Create migration steps
        steps = self._create_migration_steps(comparison)

        # Identify breaking changes
        breaking_changes = [
            change.description for change in comparison.changes
            if change.breaking_level in [BreakingChangeLevel.BREAKING, BreakingChangeLevel.DANGEROUS]
        ]

        # Create migration
        migration = SchemaMigration(
            migration_id=migration_id,
            from_version=from_version,
            to_version=to_version,
            migration_type=migration_type,
            status=MigrationStatus.PENDING,
            created_at=datetime.now(),
            created_by=user_id,
            description=description,
            steps=steps,
            breaking_changes=breaking_changes
        )

        # Store migration
        with self._lock:
            self._migrations[migration_id] = migration
            self._save_migration(migration)

        self.logger.info(
            f"Migration created: {migration_id} ({from_version} -> {to_version})",
            extra={
                'migration_id': migration_id,
                'schema_name': schema_name,
                'from_version': from_version,
                'to_version': to_version,
                'migration_type': migration_type.value,
                'steps_count': len(steps),
                'breaking_changes_count': len(breaking_changes)
            }
        )

        return migration

    def create_migration_plan(self,
                              schema_name: str,
                              target_migrations: List[str],
                              description: str = "") -> MigrationPlan:
        """
        Create a migration execution plan.

        Args:
            schema_name: Name of the schema
            target_migrations: List of migration IDs to execute
            description: Plan description

        Returns:
            Migration plan
        """
        plan_id = f"plan_{schema_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Validate migrations exist
        migrations = []
        for migration_id in target_migrations:
            if migration_id not in self._migrations:
                raise ValueError(f"Migration {migration_id} not found")
            migrations.append(self._migrations[migration_id])

        # Sort migrations by dependency order
        sorted_migrations = self._sort_migrations_by_dependency(migrations)

        # Calculate plan metrics
        total_steps = sum(len(m.steps) for m in sorted_migrations)
        breaking_changes_count = sum(len(m.breaking_changes) for m in sorted_migrations)

        # Estimate duration (rough estimate: 1 minute per 10 steps)
        estimated_duration_minutes = max(1.0, total_steps / 10.0)

        # Check if downtime is required
        requires_downtime = any(
            m.migration_type == MigrationType.MAJOR for m in sorted_migrations
        )

        # Create rollback plan
        rollback_plan = self._create_rollback_plan(schema_name, sorted_migrations)

        # Create plan
        plan = MigrationPlan(
            plan_id=plan_id,
            schema_name=schema_name,
            migrations=sorted_migrations,
            total_steps=total_steps,
            breaking_changes_count=breaking_changes_count,
            estimated_duration_minutes=estimated_duration_minutes,
            requires_downtime=requires_downtime,
            rollback_plan=rollback_plan,
            pre_migration_checks=self._generate_pre_migration_checks(sorted_migrations),
            post_migration_checks=self._generate_post_migration_checks(sorted_migrations)
        )

        # Store plan
        with self._lock:
            self._migration_plans[plan_id] = plan

        self.logger.info(
            f"Migration plan created: {plan_id}",
            extra={
                'plan_id': plan_id,
                'schema_name': schema_name,
                'migrations_count': len(sorted_migrations),
                'total_steps': total_steps,
                'breaking_changes_count': breaking_changes_count,
                'estimated_duration_minutes': estimated_duration_minutes,
                'requires_downtime': requires_downtime
            }
        )

        return plan

    def execute_migration(self,
                          migration_id: str,
                          user_id: str = None,
                          dry_run: bool = False) -> MigrationResult:
        """
        Execute a single migration.

        Args:
            migration_id: Migration to execute
            user_id: User executing the migration
            dry_run: Perform dry run without actual changes

        Returns:
            Migration result
        """
        if migration_id not in self._migrations:
            raise ValueError(f"Migration {migration_id} not found")

        migration = self._migrations[migration_id]

        if migration.status != MigrationStatus.PENDING:
            raise ValueError(f"Migration {migration_id} is not in pending status")

        start_time = datetime.now()

        result = MigrationResult(
            migration_id=migration_id,
            success=False,
            duration_seconds=0.0,
            steps_completed=0,
            steps_failed=0
        )

        try:
            # Update migration status
            with self._lock:
                migration.status = MigrationStatus.RUNNING
                migration.executed_at = start_time
                migration.executed_by = user_id
                migration.execution_log.append(
                    f"[{start_time.isoformat()}] Migration started by {user_id}"
                )

            # Execute pre-migration hooks
            self._execute_pre_migration_hooks(migration, dry_run)

            # Execute migration steps
            for i, step in enumerate(migration.steps):
                try:
                    step_start = datetime.now()

                    if dry_run:
                        self.logger.info(f"[DRY RUN] Executing step: {step.description}")
                        migration.execution_log.append(
                            f"[{step_start.isoformat()}] [DRY RUN] Step {i+1}: {step.description}"
                        )
                    else:
                        self.logger.info(f"Executing step: {step.description}")
                        migration.execution_log.append(
                            f"[{step_start.isoformat()}] Step {i+1}: {step.description}"
                        )

                        # Execute step
                        self._execute_migration_step(step, migration)

                    result.steps_completed += 1

                    # Execute step hooks
                    self._execute_step_hooks(step.operation, step, migration)

                except Exception as e:
                    result.steps_failed += 1
                    error_msg = f"Step {i+1} failed: {e}"
                    migration.execution_log.append(
                        f"[{datetime.now().isoformat()}] ERROR: {error_msg}"
                    )

                    if not dry_run and self.enable_auto_rollback:
                        # Attempt rollback
                        self.logger.error(f"Step failed, attempting rollback: {e}")
                        rollback_result = self._rollback_migration_steps(
                            migration, i  # Rollback up to current step
                        )

                        if rollback_result:
                            result.rollback_required = True
                            migration.status = MigrationStatus.ROLLED_BACK
                        else:
                            migration.status = MigrationStatus.FAILED
                    else:
                        migration.status = MigrationStatus.FAILED

                    result.error_message = error_msg
                    raise

            # Mark migration as completed
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            with self._lock:
                if dry_run:
                    migration.status = MigrationStatus.PENDING  # Keep pending for dry run
                else:
                    migration.status = MigrationStatus.COMPLETED
                    migration.completed_at = end_time

                migration.execution_log.append(
                    f"[{end_time.isoformat()}] Migration completed successfully"
                )

            result.success = True
            result.duration_seconds = duration

            # Execute post-migration hooks
            self._execute_post_migration_hooks(migration, dry_run)

            self.logger.info(
                f"Migration {'dry run' if dry_run else 'execution'} completed: {migration_id}",
                extra={
                    'migration_id': migration_id,
                    'duration_seconds': duration,
                    'steps_completed': result.steps_completed,
                    'dry_run': dry_run
                }
            )

        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            result.duration_seconds = duration
            result.error_message = str(e)

            with self._lock:
                migration.error_message = str(e)
                migration.execution_log.append(
                    f"[{end_time.isoformat()}] Migration failed: {e}"
                )

            self.logger.error(
                f"Migration {'dry run' if dry_run else 'execution'} failed: {migration_id} - {e}",
                extra={
                    'migration_id': migration_id,
                    'duration_seconds': duration,
                    'steps_completed': result.steps_completed,
                    'steps_failed': result.steps_failed,
                    'error': str(e)
                }
            )

            raise

        finally:
            # Store result
            with self._lock:
                self._execution_history.append(result)
                self._save_migration(migration)

        return result

    def execute_migration_plan(self,
                               plan_id: str,
                               user_id: str = None,
                               dry_run: bool = False) -> List[MigrationResult]:
        """
        Execute a migration plan.

        Args:
            plan_id: Plan to execute
            user_id: User executing the plan
            dry_run: Perform dry run without actual changes

        Returns:
            List of migration results
        """
        if plan_id not in self._migration_plans:
            raise ValueError(f"Migration plan {plan_id} not found")

        plan = self._migration_plans[plan_id]
        results = []

        self.logger.info(
            f"Executing migration plan: {plan_id} ({'dry run' if dry_run else 'live'})",
            extra={
                'plan_id': plan_id,
                'schema_name': plan.schema_name,
                'migrations_count': len(plan.migrations),
                'dry_run': dry_run
            }
        )

        try:
            # Execute pre-migration checks
            if not dry_run:
                self._execute_pre_migration_checks(plan)

            # Execute migrations in order
            for migration in plan.migrations:
                result = self.execute_migration(
                    migration.migration_id,
                    user_id=user_id,
                    dry_run=dry_run
                )
                results.append(result)

                # Stop on failure
                if not result.success:
                    self.logger.error(
                        f"Migration plan execution stopped due to failure: {migration.migration_id}"
                    )
                    break

            # Execute post-migration checks
            if not dry_run and all(r.success for r in results):
                self._execute_post_migration_checks(plan)

            success_count = sum(1 for r in results if r.success)
            self.logger.info(
                f"Migration plan execution completed: {plan_id} "
                f"({success_count}/{len(plan.migrations)} successful)",
                extra={
                    'plan_id': plan_id,
                    'success_count': success_count,
                    'total_count': len(plan.migrations)
                }
            )

        except Exception as e:
            self.logger.error(
                f"Migration plan execution failed: {plan_id} - {e}",
                extra={'plan_id': plan_id, 'error': str(e)}
            )
            raise

        return results

    def rollback_migration(self,
                           migration_id: str,
                           user_id: str = None) -> MigrationResult:
        """
        Rollback a completed migration.

        Args:
            migration_id: Migration to rollback
            user_id: User performing rollback

        Returns:
            Rollback result
        """
        if migration_id not in self._migrations:
            raise ValueError(f"Migration {migration_id} not found")

        migration = self._migrations[migration_id]

        if migration.status != MigrationStatus.COMPLETED:
            raise ValueError(f"Can only rollback completed migrations")

        # Create rollback migration
        rollback_migration_id = f"rollback_{migration_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        rollback_steps = []
        for step in reversed(migration.steps):
            if step.rollback_operation:
                rollback_step = MigrationStep(
                    step_id=f"rollback_{step.step_id}",
                    description=f"Rollback: {step.description}",
                    operation=step.rollback_operation,
                    target=step.target,
                    details=step.rollback_details or {},
                    is_breaking=step.is_breaking
                )
                rollback_steps.append(rollback_step)

        rollback_migration = SchemaMigration(
            migration_id=rollback_migration_id,
            from_version=migration.to_version,
            to_version=migration.from_version,
            migration_type=MigrationType.ROLLBACK,
            status=MigrationStatus.PENDING,
            created_at=datetime.now(),
            created_by=user_id,
            description=f"Rollback of migration {migration_id}",
            steps=rollback_steps
        )

        # Store rollback migration
        with self._lock:
            self._migrations[rollback_migration_id] = rollback_migration
            migration.rollback_migration_id = rollback_migration_id

        # Execute rollback
        result = self.execute_migration(rollback_migration_id, user_id=user_id)

        if result.success:
            with self._lock:
                migration.status = MigrationStatus.ROLLED_BACK
                self._save_migration(migration)

        return result

    def get_migration(self, migration_id: str) -> Optional[SchemaMigration]:
        """Get migration by ID."""
        return self._migrations.get(migration_id)

    def list_migrations(self,
                        schema_name: str = None,
                        status: MigrationStatus = None,
                        migration_type: MigrationType = None) -> List[SchemaMigration]:
        """List migrations with optional filtering."""
        migrations = []

        with self._lock:
            for migration in self._migrations.values():
                # Apply filters
                if status and migration.status != status:
                    continue

                if migration_type and migration.migration_type != migration_type:
                    continue

                migrations.append(migration)

        # Sort by creation date
        migrations.sort(key=lambda m: m.created_at, reverse=True)
        return migrations

    def get_migration_plan(self, plan_id: str) -> Optional[MigrationPlan]:
        """Get migration plan by ID."""
        return self._migration_plans.get(plan_id)

    def get_execution_history(self,
                              migration_id: str = None,
                              hours_back: int = 24) -> List[MigrationResult]:
        """Get migration execution history."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        history = []
        for result in self._execution_history:
            if migration_id and result.migration_id != migration_id:
                continue

            # Note: MigrationResult doesn't have timestamp, using creation time from migration
            migration = self._migrations.get(result.migration_id)
            if migration and migration.executed_at and migration.executed_at >= cutoff_time:
                history.append(result)

        return history

    def add_pre_migration_hook(self, hook: Callable):
        """Add pre-migration hook."""
        self._pre_migration_hooks.append(hook)

    def add_post_migration_hook(self, hook: Callable):
        """Add post-migration hook."""
        self._post_migration_hooks.append(hook)

    def add_step_hook(self, operation: str, hook: Callable):
        """Add step-specific hook."""
        self._step_hooks[operation].append(hook)

    def export_migrations(self, format: str = 'json') -> str:
        """Export migration data."""
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'migrations': [],
            'plans': []
        }

        with self._lock:
            # Export migrations
            for migration in self._migrations.values():
                migration_data = {
                    'migration_id': migration.migration_id,
                    'from_version': migration.from_version,
                    'to_version': migration.to_version,
                    'migration_type': migration.migration_type.value,
                    'status': migration.status.value,
                    'created_at': migration.created_at.isoformat(),
                    'description': migration.description,
                    'steps_count': len(migration.steps),
                    'breaking_changes_count': len(migration.breaking_changes)
                }

                if migration.executed_at:
                    migration_data['executed_at'] = migration.executed_at.isoformat()

                if migration.completed_at:
                    migration_data['completed_at'] = migration.completed_at.isoformat()

                export_data['migrations'].append(migration_data)

            # Export plans
            for plan in self._migration_plans.values():
                plan_data = {
                    'plan_id': plan.plan_id,
                    'schema_name': plan.schema_name,
                    'migrations_count': len(plan.migrations),
                    'total_steps': plan.total_steps,
                    'breaking_changes_count': plan.breaking_changes_count,
                    'estimated_duration_minutes': plan.estimated_duration_minutes,
                    'requires_downtime': plan.requires_downtime
                }

                export_data['plans'].append(plan_data)

        if format == 'json':
            return json.dumps(export_data, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _determine_migration_type(self, comparison: SchemaComparison) -> MigrationType:
        """Determine migration type based on schema comparison."""
        has_breaking = any(
            change.breaking_level in [BreakingChangeLevel.BREAKING, BreakingChangeLevel.DANGEROUS]
            for change in comparison.changes
        )

        has_additions = any(
            change.change_type == ChangeType.ADDED
            for change in comparison.changes
        )

        if has_breaking:
            return MigrationType.MAJOR
        elif has_additions:
            return MigrationType.MINOR
        else:
            return MigrationType.PATCH

    def _generate_migration_id(self, schema_name: str,
                               from_version: str, to_version: str) -> str:
        """Generate unique migration ID."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        hash_input = f"{schema_name}_{from_version}_{to_version}_{timestamp}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"migration_{schema_name}_{from_version}_to_{to_version}_{hash_suffix}"

    def _create_migration_steps(self, comparison: SchemaComparison) -> List[MigrationStep]:
        """Create migration steps from schema comparison."""
        steps = []

        for i, change in enumerate(comparison.changes):
            step = MigrationStep(
                step_id=f"step_{i+1}",
                description=change.description,
                operation=self._change_type_to_operation(change.change_type),
                target=change.path,
                details={
                    'change_type': change.change_type.value,
                    'breaking_level': change.breaking_level.value,
                    'old_value': change.old_value,
                    'new_value': change.new_value
                },
                is_breaking=change.breaking_level in [
                    BreakingChangeLevel.BREAKING,
                    BreakingChangeLevel.DANGEROUS
                ]
            )

            # Add rollback operation if possible
            rollback_op = self._get_rollback_operation(change.change_type)
            if rollback_op:
                step.rollback_operation = rollback_op
                step.rollback_details = {
                    'change_type': change.change_type.value,
                    'restore_value': change.old_value
                }

            steps.append(step)

        return steps

    def _change_type_to_operation(self, change_type: ChangeType) -> str:
        """Convert change type to operation name."""
        mapping = {
            ChangeType.ADDED: 'add_element',
            ChangeType.REMOVED: 'remove_element',
            ChangeType.MODIFIED: 'modify_element',
            ChangeType.DEPRECATED: 'deprecate_element'
        }
        return mapping.get(change_type, 'unknown_operation')

    def _get_rollback_operation(self, change_type: ChangeType) -> Optional[str]:
        """Get rollback operation for change type."""
        mapping = {
            ChangeType.ADDED: 'remove_element',
            ChangeType.REMOVED: 'add_element',
            ChangeType.MODIFIED: 'restore_element',
            ChangeType.DEPRECATED: 'undeprecate_element'
        }
        return mapping.get(change_type)

    def _sort_migrations_by_dependency(self, migrations: List[SchemaMigration]) -> List[SchemaMigration]:
        """Sort migrations by dependency order."""
        # Simple sort by creation date for now
        # In a real implementation, you'd analyze dependencies
        return sorted(migrations, key=lambda m: m.created_at)

    def _create_rollback_plan(self, schema_name: str,
                              migrations: List[SchemaMigration]) -> Optional[MigrationPlan]:
        """Create rollback plan for migrations."""
        # Create rollback migrations for each migration
        rollback_migrations = []

        for migration in reversed(migrations):  # Reverse order for rollback
            if migration.migration_type != MigrationType.ROLLBACK:
                # Create rollback steps
                rollback_steps = []
                for step in reversed(migration.steps):
                    if step.rollback_operation:
                        rollback_step = MigrationStep(
                            step_id=f"rollback_{step.step_id}",
                            description=f"Rollback: {step.description}",
                            operation=step.rollback_operation,
                            target=step.target,
                            details=step.rollback_details or {}
                        )
                        rollback_steps.append(rollback_step)

                if rollback_steps:
                    rollback_migration = SchemaMigration(
                        migration_id=f"rollback_{migration.migration_id}",
                        from_version=migration.to_version,
                        to_version=migration.from_version,
                        migration_type=MigrationType.ROLLBACK,
                        status=MigrationStatus.PENDING,
                        created_at=datetime.now(),
                        description=f"Rollback of {migration.migration_id}",
                        steps=rollback_steps
                    )
                    rollback_migrations.append(rollback_migration)

        if rollback_migrations:
            rollback_plan = MigrationPlan(
                plan_id=f"rollback_plan_{schema_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                schema_name=schema_name,
                migrations=rollback_migrations,
                total_steps=sum(len(m.steps) for m in rollback_migrations)
            )
            return rollback_plan

        return None

    def _generate_pre_migration_checks(self, migrations: List[SchemaMigration]) -> List[str]:
        """Generate pre-migration checks."""
        checks = [
            "Verify schema registry is accessible",
            "Check for active GraphQL operations",
            "Validate migration dependencies",
            "Ensure backup is available"
        ]

        # Add specific checks based on migration types
        has_breaking = any(
            m.migration_type == MigrationType.MAJOR for m in migrations
        )

        if has_breaking:
            checks.extend([
                "Notify clients of breaking changes",
                "Verify client compatibility",
                "Schedule maintenance window"
            ])

        return checks

    def _generate_post_migration_checks(self, migrations: List[SchemaMigration]) -> List[str]:
        """Generate post-migration checks."""
        return [
            "Verify schema is valid",
            "Test GraphQL operations",
            "Check performance metrics",
            "Validate client compatibility",
            "Monitor error rates"
        ]

    def _execute_migration_step(self, step: MigrationStep, migration: SchemaMigration):
        """Execute a single migration step."""
        # This is a placeholder - in a real implementation, you'd have
        # specific handlers for each operation type

        operation_handlers = {
            'add_element': self._handle_add_element,
            'remove_element': self._handle_remove_element,
            'modify_element': self._handle_modify_element,
            'deprecate_element': self._handle_deprecate_element
        }

        handler = operation_handlers.get(step.operation)
        if handler:
            handler(step, migration)
        else:
            raise ValueError(f"Unknown operation: {step.operation}")

    def _handle_add_element(self, step: MigrationStep, migration: SchemaMigration):
        """Handle add element operation."""
        # Placeholder implementation
        self.logger.info(f"Adding element: {step.target}")

    def _handle_remove_element(self, step: MigrationStep, migration: SchemaMigration):
        """Handle remove element operation."""
        # Placeholder implementation
        self.logger.info(f"Removing element: {step.target}")

    def _handle_modify_element(self, step: MigrationStep, migration: SchemaMigration):
        """Handle modify element operation."""
        # Placeholder implementation
        self.logger.info(f"Modifying element: {step.target}")

    def _handle_deprecate_element(self, step: MigrationStep, migration: SchemaMigration):
        """Handle deprecate element operation."""
        # Placeholder implementation
        self.logger.info(f"Deprecating element: {step.target}")

    def _rollback_migration_steps(self, migration: SchemaMigration,
                                  up_to_step: int) -> bool:
        """Rollback migration steps up to specified step."""
        try:
            for i in range(up_to_step, -1, -1):
                step = migration.steps[i]
                if step.rollback_operation:
                    rollback_step = MigrationStep(
                        step_id=f"rollback_{step.step_id}",
                        description=f"Rollback: {step.description}",
                        operation=step.rollback_operation,
                        target=step.target,
                        details=step.rollback_details or {}
                    )
                    self._execute_migration_step(rollback_step, migration)

            return True

        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False

    def _execute_pre_migration_hooks(self, migration: SchemaMigration, dry_run: bool):
        """Execute pre-migration hooks."""
        for hook in self._pre_migration_hooks:
            try:
                hook(migration, dry_run)
            except Exception as e:
                self.logger.error(f"Pre-migration hook failed: {e}")

    def _execute_post_migration_hooks(self, migration: SchemaMigration, dry_run: bool):
        """Execute post-migration hooks."""
        for hook in self._post_migration_hooks:
            try:
                hook(migration, dry_run)
            except Exception as e:
                self.logger.error(f"Post-migration hook failed: {e}")

    def _execute_step_hooks(self, operation: str, step: MigrationStep,
                            migration: SchemaMigration):
        """Execute step-specific hooks."""
        for hook in self._step_hooks.get(operation, []):
            try:
                hook(step, migration)
            except Exception as e:
                self.logger.error(f"Step hook failed for {operation}: {e}")

    def _execute_pre_migration_checks(self, plan: MigrationPlan):
        """Execute pre-migration checks."""
        for check in plan.pre_migration_checks:
            self.logger.info(f"Pre-migration check: {check}")
            # Implement actual checks here

    def _execute_post_migration_checks(self, plan: MigrationPlan):
        """Execute post-migration checks."""
        for check in plan.post_migration_checks:
            self.logger.info(f"Post-migration check: {check}")
            # Implement actual checks here

    def _save_migration(self, migration: SchemaMigration):
        """Save migration to storage."""
        migration_file = self.migration_storage_path / f"{migration.migration_id}.json"

        migration_data = {
            'migration_id': migration.migration_id,
            'from_version': migration.from_version,
            'to_version': migration.to_version,
            'migration_type': migration.migration_type.value,
            'status': migration.status.value,
            'created_at': migration.created_at.isoformat(),
            'description': migration.description,
            'steps': [
                {
                    'step_id': step.step_id,
                    'description': step.description,
                    'operation': step.operation,
                    'target': step.target,
                    'details': step.details,
                    'is_breaking': step.is_breaking,
                    'rollback_operation': step.rollback_operation,
                    'rollback_details': step.rollback_details
                }
                for step in migration.steps
            ],
            'breaking_changes': migration.breaking_changes,
            'execution_log': migration.execution_log
        }

        if migration.executed_at:
            migration_data['executed_at'] = migration.executed_at.isoformat()

        if migration.completed_at:
            migration_data['completed_at'] = migration.completed_at.isoformat()

        if migration.error_message:
            migration_data['error_message'] = migration.error_message

        with open(migration_file, 'w', encoding='utf-8') as f:
            json.dump(migration_data, f, indent=2, ensure_ascii=False)

    def _load_migrations(self):
        """Load migrations from storage."""
        if not self.migration_storage_path.exists():
            return

        for migration_file in self.migration_storage_path.glob("*.json"):
            try:
                with open(migration_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Reconstruct migration steps
                steps = []
                for step_data in data.get('steps', []):
                    step = MigrationStep(
                        step_id=step_data['step_id'],
                        description=step_data['description'],
                        operation=step_data['operation'],
                        target=step_data['target'],
                        details=step_data.get('details', {}),
                        is_breaking=step_data.get('is_breaking', False),
                        rollback_operation=step_data.get('rollback_operation'),
                        rollback_details=step_data.get('rollback_details')
                    )
                    steps.append(step)

                # Reconstruct migration
                migration = SchemaMigration(
                    migration_id=data['migration_id'],
                    from_version=data['from_version'],
                    to_version=data['to_version'],
                    migration_type=MigrationType(data['migration_type']),
                    status=MigrationStatus(data['status']),
                    created_at=datetime.fromisoformat(data['created_at']),
                    description=data.get('description', ''),
                    steps=steps,
                    breaking_changes=data.get('breaking_changes', []),
                    execution_log=data.get('execution_log', [])
                )

                if 'executed_at' in data:
                    migration.executed_at = datetime.fromisoformat(data['executed_at'])

                if 'completed_at' in data:
                    migration.completed_at = datetime.fromisoformat(data['completed_at'])

                if 'error_message' in data:
                    migration.error_message = data['error_message']

                self._migrations[migration.migration_id] = migration

            except Exception as e:
                self.logger.error(f"Failed to load migration from {migration_file}: {e}")

        self.logger.info(f"Loaded {len(self._migrations)} migrations from storage")

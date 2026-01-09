"""
Schema management module.

This module provides comprehensive schema lifecycle management including
registration, updates, versioning, and administrative operations.
"""

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union, Tuple

from django.conf import settings
from django.db import transaction
from graphql import GraphQLSchema, build_ast_schema, validate

from ..debugging import DebugHooks, PerformanceMonitor
from ..introspection import SchemaComparison, SchemaIntrospector
from ..validation import SchemaValidator, ValidationResult

logger = logging.getLogger(__name__)


class SchemaOperation(Enum):
    """Types of schema operations."""
    REGISTER = "register"
    UPDATE = "update"
    DEACTIVATE = "deactivate"
    ACTIVATE = "activate"
    DELETE = "delete"
    MIGRATE = "migrate"
    BACKUP = "backup"
    RESTORE = "restore"


class SchemaStatus(Enum):
    """Schema status values."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    MIGRATING = "migrating"
    ERROR = "error"


@dataclass
class SchemaLifecycleEvent:
    """Represents a schema lifecycle event."""
    event_id: str
    schema_name: str
    operation: SchemaOperation
    timestamp: datetime
    user_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None


@dataclass
class SchemaMetadata:
    """Schema metadata information."""
    name: str
    version: str
    description: str
    status: SchemaStatus
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    deprecation_date: Optional[datetime] = None
    migration_path: Optional[str] = None
    backup_enabled: bool = True
    monitoring_enabled: bool = True


@dataclass
class SchemaHealth:
    """Schema health status."""
    schema_name: str
    status: str  # 'healthy', 'warning', 'critical'
    last_check: datetime
    issues: List[str] = field(default_factory=list)
    performance_score: float = 100.0
    error_rate: float = 0.0
    usage_stats: Dict[str, Any] = field(default_factory=dict)


class SchemaManager:
    """
    Comprehensive schema lifecycle management system.

    Manages GraphQL schema registration, updates, versioning,
    health monitoring, and administrative operations.
    """

    def __init__(self,
                 validator: SchemaValidator = None,
                 introspector: SchemaIntrospector = None,
                 debug_hooks: DebugHooks = None,
                 performance_monitor: PerformanceMonitor = None,
                 enable_caching: bool = True,
                 cache_timeout: int = 3600,
                 enable_health_monitoring: bool = True,
                 health_check_interval: int = 300):  # 5 minutes

        self.validator = validator or SchemaValidator()
        self.introspector = introspector or SchemaIntrospector()
        self.debug_hooks = debug_hooks
        self.performance_monitor = performance_monitor
        self.enable_caching = enable_caching
        self.cache_timeout = cache_timeout
        self.enable_health_monitoring = enable_health_monitoring
        self.health_check_interval = health_check_interval

        # Schema storage
        self._schemas: Dict[str, GraphQLSchema] = {}
        # In-memory per-process cache with TTL for quick schema access
        # Format: {name: (schema, expires_at_epoch_seconds)}
        self._schema_cache: Dict[str, Tuple[GraphQLSchema, float]] = {}
        self._metadata: Dict[str, SchemaMetadata] = {}
        self._lifecycle_events: List[SchemaLifecycleEvent] = []
        self._health_status: Dict[str, SchemaHealth] = {}

        # Lifecycle hooks
        self._pre_operation_hooks: Dict[SchemaOperation, List[Callable]] = defaultdict(list)
        self._post_operation_hooks: Dict[SchemaOperation, List[Callable]] = defaultdict(list)

        # Thread safety
        self._lock = threading.RLock()

        # Health monitoring
        self._health_monitor_thread = None
        self._stop_health_monitor = threading.Event()

        if self.enable_health_monitoring:
            self._start_health_monitoring()

        self.logger = logging.getLogger(__name__)

    def register_schema(self,
                        name: str,
                        schema: Union[GraphQLSchema, str],
                        version: str = "1.0.0",
                        description: str = "",
                        user_id: str = None,
                        tags: Dict[str, str] = None,
                        dependencies: List[str] = None,
                        force: bool = False) -> bool:
        """
        Register a new GraphQL schema.

        Args:
            name: Schema name
            schema: GraphQL schema object or SDL string
            version: Schema version
            description: Schema description
            user_id: User performing the operation
            tags: Additional metadata tags
            dependencies: Schema dependencies
            force: Force registration even if validation fails

        Returns:
            True if registration successful
        """
        event = self._create_event(
            schema_name=name,
            operation=SchemaOperation.REGISTER,
            user_id=user_id
        )

        try:
            start_time = datetime.now()

            # Execute pre-operation hooks
            self._execute_hooks(SchemaOperation.REGISTER, 'pre', {
                'name': name,
                'schema': schema,
                'version': version,
                'user_id': user_id
            })

            # Convert string schema to GraphQLSchema if needed
            if isinstance(schema, str):
                try:
                    schema = build_ast_schema(schema)
                except Exception as e:
                    raise ValueError(f"Invalid GraphQL SDL: {e}")

            # Validate schema
            if not force:
                validation_result = self.validator.validate_schema(
                    name=name,
                    schema=schema,
                    version=version,
                    description=description
                )

                if not validation_result.is_valid:
                    raise ValueError(f"Schema validation failed: {validation_result.errors}")

            # Check for conflicts
            if name in self._schemas and not force:
                existing_metadata = self._metadata.get(name)
                if existing_metadata and existing_metadata.version == version:
                    raise ValueError(f"Schema {name} version {version} already exists")

            with self._lock:
                # Store schema
                self._schemas[name] = schema

                # Create metadata
                metadata = SchemaMetadata(
                    name=name,
                    version=version,
                    description=description,
                    status=SchemaStatus.ACTIVE,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    created_by=user_id,
                    updated_by=user_id,
                    tags=tags or {},
                    dependencies=dependencies or []
                )

                self._metadata[name] = metadata

                # Initialize health status
                self._health_status[name] = SchemaHealth(
                    schema_name=name,
                    status='healthy',
                    last_check=datetime.now()
                )

                # Clear cache
                if self.enable_caching:
                    self._clear_schema_cache(name)

            # Record event
            event.success = True
            event.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            event.details = {
                'version': version,
                'description': description,
                'tags': tags or {},
                'dependencies': dependencies or []
            }

            # Execute post-operation hooks
            self._execute_hooks(SchemaOperation.REGISTER, 'post', {
                'name': name,
                'schema': schema,
                'metadata': metadata,
                'event': event
            })

            # Debug logging
            if self.debug_hooks:
                self.debug_hooks.log_schema_registration(
                    schema_name=name,
                    version=version,
                    success=True
                )

            self.logger.info(
                f"Schema registered successfully: {name} v{version}",
                extra={
                    'schema_name': name,
                    'version': version,
                    'user_id': user_id,
                    'duration_ms': event.duration_ms
                }
            )

            return True

        except Exception as e:
            event.success = False
            event.error_message = str(e)

            # Debug logging
            if self.debug_hooks:
                self.debug_hooks.log_schema_registration(
                    schema_name=name,
                    version=version,
                    success=False,
                    error=str(e)
                )

            self.logger.error(
                f"Schema registration failed: {name} - {e}",
                extra={
                    'schema_name': name,
                    'version': version,
                    'user_id': user_id,
                    'error': str(e)
                }
            )

            raise

        finally:
            self._lifecycle_events.append(event)

    def update_schema(self,
                      name: str,
                      schema: Union[GraphQLSchema, str] = None,
                      version: str = None,
                      description: str = None,
                      user_id: str = None,
                      tags: Dict[str, str] = None,
                      force: bool = False) -> bool:
        """
        Update an existing schema.

        Args:
            name: Schema name
            schema: New schema (optional)
            version: New version (optional)
            description: New description (optional)
            user_id: User performing the operation
            tags: Updated tags (optional)
            force: Force update even if validation fails

        Returns:
            True if update successful
        """
        if name not in self._schemas:
            raise ValueError(f"Schema {name} not found")

        event = self._create_event(
            schema_name=name,
            operation=SchemaOperation.UPDATE,
            user_id=user_id
        )

        try:
            start_time = datetime.now()

            # Execute pre-operation hooks
            self._execute_hooks(SchemaOperation.UPDATE, 'pre', {
                'name': name,
                'schema': schema,
                'version': version,
                'user_id': user_id
            })

            with self._lock:
                current_metadata = self._metadata[name]
                old_schema = self._schemas[name]

                # Prepare updates
                updates = {}

                if schema is not None:
                    if isinstance(schema, str):
                        schema = build_ast_schema(schema)

                    # Validate new schema
                    if not force:
                        validation_result = self.validator.validate_schema(
                            name=name,
                            schema=schema,
                            version=version or current_metadata.version
                        )

                        if not validation_result.is_valid:
                            raise ValueError(
                                f"Schema validation failed: {validation_result.errors}")

                    updates['schema'] = schema

                if version is not None:
                    updates['version'] = version

                if description is not None:
                    updates['description'] = description

                if tags is not None:
                    updates['tags'] = {**current_metadata.tags, **tags}

                # Apply updates
                if 'schema' in updates:
                    self._schemas[name] = updates['schema']

                # Update metadata
                for key, value in updates.items():
                    if key != 'schema':
                        setattr(current_metadata, key, value)

                current_metadata.updated_at = datetime.now()
                current_metadata.updated_by = user_id

                # Clear cache
                if self.enable_caching:
                    self._clear_schema_cache(name)

            # Record event
            event.success = True
            event.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            event.details = updates

            # Execute post-operation hooks
            self._execute_hooks(SchemaOperation.UPDATE, 'post', {
                'name': name,
                'old_schema': old_schema,
                'new_schema': self._schemas[name],
                'metadata': current_metadata,
                'event': event
            })

            self.logger.info(
                f"Schema updated successfully: {name}",
                extra={
                    'schema_name': name,
                    'user_id': user_id,
                    'updates': list(updates.keys()),
                    'duration_ms': event.duration_ms
                }
            )

            return True

        except Exception as e:
            event.success = False
            event.error_message = str(e)

            self.logger.error(
                f"Schema update failed: {name} - {e}",
                extra={
                    'schema_name': name,
                    'user_id': user_id,
                    'error': str(e)
                }
            )

            raise

        finally:
            self._lifecycle_events.append(event)

    def deactivate_schema(self, name: str, user_id: str = None) -> bool:
        """Deactivate a schema."""
        return self._change_schema_status(name, SchemaStatus.INACTIVE, user_id)

    def activate_schema(self, name: str, user_id: str = None) -> bool:
        """Activate a schema."""
        return self._change_schema_status(name, SchemaStatus.ACTIVE, user_id)

    def deprecate_schema(self, name: str, deprecation_date: datetime = None,
                         migration_path: str = None, user_id: str = None) -> bool:
        """Deprecate a schema with optional migration path."""
        if name not in self._schemas:
            raise ValueError(f"Schema {name} not found")

        with self._lock:
            metadata = self._metadata[name]
            metadata.status = SchemaStatus.DEPRECATED
            metadata.deprecation_date = deprecation_date or datetime.now()
            metadata.migration_path = migration_path
            metadata.updated_at = datetime.now()
            metadata.updated_by = user_id

        self.logger.info(
            f"Schema deprecated: {name}",
            extra={
                'schema_name': name,
                'deprecation_date': deprecation_date,
                'migration_path': migration_path,
                'user_id': user_id
            }
        )

        return True

    def delete_schema(self, name: str, user_id: str = None, force: bool = False) -> bool:
        """
        Delete a schema.

        Args:
            name: Schema name
            user_id: User performing the operation
            force: Force deletion even if schema is active

        Returns:
            True if deletion successful
        """
        if name not in self._schemas:
            raise ValueError(f"Schema {name} not found")

        event = self._create_event(
            schema_name=name,
            operation=SchemaOperation.DELETE,
            user_id=user_id
        )

        try:
            with self._lock:
                metadata = self._metadata[name]

                # Check if schema can be deleted
                if not force and metadata.status == SchemaStatus.ACTIVE:
                    raise ValueError(
                        f"Cannot delete active schema {name}. Deactivate first or use force=True")

                # Execute pre-operation hooks
                self._execute_hooks(SchemaOperation.DELETE, 'pre', {
                    'name': name,
                    'metadata': metadata,
                    'user_id': user_id
                })

                # Remove schema
                del self._schemas[name]
                del self._metadata[name]

                # Remove health status
                if name in self._health_status:
                    del self._health_status[name]

                # Clear cache
                if self.enable_caching:
                    self._clear_schema_cache(name)

            event.success = True

            # Execute post-operation hooks
            self._execute_hooks(SchemaOperation.DELETE, 'post', {
                'name': name,
                'event': event
            })

            self.logger.info(
                f"Schema deleted: {name}",
                extra={
                    'schema_name': name,
                    'user_id': user_id,
                    'force': force
                }
            )

            return True

        except Exception as e:
            event.success = False
            event.error_message = str(e)

            self.logger.error(
                f"Schema deletion failed: {name} - {e}",
                extra={
                    'schema_name': name,
                    'user_id': user_id,
                    'error': str(e)
                }
            )

            raise

        finally:
            self._lifecycle_events.append(event)

    def get_schema(self, name: str, use_cache: bool = True) -> Optional[GraphQLSchema]:
        """Get schema by name."""
        if use_cache and self.enable_caching:
            # Check in-memory cache first
            cached = self._schema_cache.get(name)
            if cached:
                schema, expires_at = cached
                if expires_at > time.time():
                    return schema
                # Expired entry: remove it
                self._schema_cache.pop(name, None)

        schema = self._schemas.get(name)

        if schema and use_cache and self.enable_caching:
            # Store in in-memory cache with TTL
            self._schema_cache[name] = (schema, time.time() + float(self.cache_timeout))

        return schema

    def get_schema_metadata(self, name: str) -> Optional[SchemaMetadata]:
        """Get schema metadata by name."""
        return self._metadata.get(name)

    def list_schemas(self,
                     status: SchemaStatus = None,
                     tags: Dict[str, str] = None,
                     include_deprecated: bool = True) -> List[SchemaMetadata]:
        """
        List schemas with optional filtering.

        Args:
            status: Filter by status
            tags: Filter by tags (all must match)
            include_deprecated: Include deprecated schemas

        Returns:
            List of schema metadata
        """
        schemas = []

        with self._lock:
            for metadata in self._metadata.values():
                # Status filter
                if status and metadata.status != status:
                    continue

                # Deprecated filter
                if not include_deprecated and metadata.status == SchemaStatus.DEPRECATED:
                    continue

                # Tags filter
                if tags:
                    if not all(
                        metadata.tags.get(key) == value
                        for key, value in tags.items()
                    ):
                        continue

                schemas.append(metadata)

        # Sort by name
        schemas.sort(key=lambda s: s.name)
        return schemas

    def get_schema_health(self, name: str) -> Optional[SchemaHealth]:
        """Get schema health status."""
        return self._health_status.get(name)

    def check_schema_health(self, name: str) -> SchemaHealth:
        """Perform health check on a schema."""
        if name not in self._schemas:
            raise ValueError(f"Schema {name} not found")

        schema = self._schemas[name]
        metadata = self._metadata[name]

        health = SchemaHealth(
            schema_name=name,
            status='healthy',
            last_check=datetime.now()
        )

        issues = []
        performance_score = 100.0

        # Check schema validity
        try:
            validation_errors = validate(schema, [])
            if validation_errors:
                issues.extend([str(error) for error in validation_errors])
                health.status = 'critical'
                performance_score -= 50
        except Exception as e:
            issues.append(f"Schema validation error: {e}")
            health.status = 'critical'
            performance_score -= 50

        # Check for deprecated fields
        if self.introspector:
            try:
                introspection = self.introspector.introspect_schema(schema)
                deprecated_count = sum(
                    1 for type_info in introspection.types.values()
                    for field in type_info.fields
                    if field.is_deprecated
                )

                if deprecated_count > 0:
                    issues.append(f"{deprecated_count} deprecated fields found")
                    if deprecated_count > 10:
                        health.status = 'warning'
                        performance_score -= 10
            except Exception as e:
                issues.append(f"Introspection error: {e}")

        # Check performance metrics
        if self.performance_monitor:
            try:
                stats = self.performance_monitor.get_operation_stats(
                    operation_name=f"schema:{name}",
                    hours_back=24
                )

                if stats:
                    avg_time = stats.get('avg_execution_time_ms', 0)
                    error_rate = stats.get('error_rate', 0)

                    health.error_rate = error_rate

                    if avg_time > 1000:  # > 1 second
                        issues.append(f"High average execution time: {avg_time:.2f}ms")
                        performance_score -= 20

                    if error_rate > 0.05:  # > 5% error rate
                        issues.append(f"High error rate: {error_rate:.2%}")
                        if error_rate > 0.1:
                            health.status = 'critical'
                        else:
                            health.status = 'warning'
                        performance_score -= 30
            except Exception as e:
                issues.append(f"Performance monitoring error: {e}")

        # Update health status
        health.issues = issues
        health.performance_score = max(0, performance_score)

        if health.status == 'healthy' and issues:
            health.status = 'warning'

        # Store health status
        with self._lock:
            self._health_status[name] = health

        return health

    def get_lifecycle_events(self,
                             schema_name: str = None,
                             operation: SchemaOperation = None,
                             hours_back: int = 24,
                             limit: int = 100) -> List[SchemaLifecycleEvent]:
        """Get lifecycle events with optional filtering."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        events = []
        for event in reversed(self._lifecycle_events):
            if event.timestamp < cutoff_time:
                continue

            if schema_name and event.schema_name != schema_name:
                continue

            if operation and event.operation != operation:
                continue

            events.append(event)

            if len(events) >= limit:
                break

        return events

    def add_lifecycle_hook(self, operation: SchemaOperation,
                           hook: Callable, when: str = 'post'):
        """
        Add lifecycle hook for schema operations.

        Args:
            operation: Schema operation to hook into
            hook: Callback function
            when: 'pre' or 'post' operation
        """
        if when == 'pre':
            self._pre_operation_hooks[operation].append(hook)
        elif when == 'post':
            self._post_operation_hooks[operation].append(hook)
        else:
            raise ValueError("when must be 'pre' or 'post'")

    def export_schemas(self, format: str = 'json',
                       include_sdl: bool = False) -> str:
        """
        Export schema metadata and optionally SDL.

        Args:
            format: Export format ('json' or 'yaml')
            include_sdl: Include GraphQL SDL in export

        Returns:
            Exported data as string
        """
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'schemas': []
        }

        with self._lock:
            for name, metadata in self._metadata.items():
                schema_data = {
                    'name': metadata.name,
                    'version': metadata.version,
                    'description': metadata.description,
                    'status': metadata.status.value,
                    'created_at': metadata.created_at.isoformat(),
                    'updated_at': metadata.updated_at.isoformat(),
                    'created_by': metadata.created_by,
                    'updated_by': metadata.updated_by,
                    'tags': metadata.tags,
                    'dependencies': metadata.dependencies
                }

                if metadata.deprecation_date:
                    schema_data['deprecation_date'] = metadata.deprecation_date.isoformat()

                if metadata.migration_path:
                    schema_data['migration_path'] = metadata.migration_path

                if include_sdl and name in self._schemas:
                    from graphql import print_schema
                    schema_data['sdl'] = print_schema(self._schemas[name])

                export_data['schemas'].append(schema_data)

        if format == 'json':
            return json.dumps(export_data, indent=2, ensure_ascii=False)
        elif format == 'yaml':
            import yaml
            return yaml.dump(export_data, default_flow_style=False)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def cleanup_old_events(self, days_to_keep: int = 30):
        """Clean up old lifecycle events."""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with self._lock:
            self._lifecycle_events = [
                event for event in self._lifecycle_events
                if event.timestamp >= cutoff_date
            ]

        self.logger.info(
            f"Cleaned up lifecycle events older than {days_to_keep} days"
        )

    def _change_schema_status(self, name: str, status: SchemaStatus,
                              user_id: str = None) -> bool:
        """Change schema status."""
        if name not in self._schemas:
            raise ValueError(f"Schema {name} not found")

        operation = SchemaOperation.ACTIVATE if status == SchemaStatus.ACTIVE else SchemaOperation.DEACTIVATE

        event = self._create_event(
            schema_name=name,
            operation=operation,
            user_id=user_id
        )

        try:
            with self._lock:
                metadata = self._metadata[name]
                old_status = metadata.status
                metadata.status = status
                metadata.updated_at = datetime.now()
                metadata.updated_by = user_id

                # Clear cache
                if self.enable_caching:
                    self._clear_schema_cache(name)

            event.success = True
            event.details = {
                'old_status': old_status.value,
                'new_status': status.value
            }

            self.logger.info(
                f"Schema status changed: {name} {old_status.value} -> {status.value}",
                extra={
                    'schema_name': name,
                    'old_status': old_status.value,
                    'new_status': status.value,
                    'user_id': user_id
                }
            )

            return True

        except Exception as e:
            event.success = False
            event.error_message = str(e)
            raise

        finally:
            self._lifecycle_events.append(event)

    def _create_event(self, schema_name: str, operation: SchemaOperation,
                      user_id: str = None) -> SchemaLifecycleEvent:
        """Create a lifecycle event."""
        return SchemaLifecycleEvent(
            event_id=f"{operation.value}_{schema_name}_{datetime.now().isoformat()}",
            schema_name=schema_name,
            operation=operation,
            timestamp=datetime.now(),
            user_id=user_id
        )

    def _execute_hooks(self, operation: SchemaOperation, when: str, context: Dict[str, Any]):
        """Execute lifecycle hooks."""
        hooks = (self._pre_operation_hooks[operation] if when == 'pre'
                 else self._post_operation_hooks[operation])

        for hook in hooks:
            try:
                hook(context)
            except Exception as e:
                self.logger.error(
                    f"Error in {when}-{operation.value} hook: {e}",
                    extra={'hook': str(hook), 'context': context}
                )

    def _clear_schema_cache(self, name: str):
        """Clear schema cache."""
        # Remove from in-memory cache
        self._schema_cache.pop(name, None)

    def _start_health_monitoring(self):
        """Start background health monitoring."""
        def monitor_health():
            while not self._stop_health_monitor.is_set():
                try:
                    with self._lock:
                        schema_names = list(self._schemas.keys())

                    for name in schema_names:
                        try:
                            self.check_schema_health(name)
                        except Exception as e:
                            self.logger.error(
                                f"Health check failed for schema {name}: {e}"
                            )

                    # Wait for next check
                    self._stop_health_monitor.wait(self.health_check_interval)

                except Exception as e:
                    self.logger.error(f"Health monitoring error: {e}")
                    self._stop_health_monitor.wait(60)  # Wait 1 minute on error

        self._health_monitor_thread = threading.Thread(
            target=monitor_health,
            daemon=True,
            name="SchemaHealthMonitor"
        )
        self._health_monitor_thread.start()

    def stop(self):
        """Stop the schema manager and cleanup resources."""
        if self._health_monitor_thread:
            self._stop_health_monitor.set()
            self._health_monitor_thread.join(timeout=5)

        self.logger.info("Schema manager stopped")

    def __del__(self):
        """Cleanup on destruction."""
        try:
            self.stop()
        except:
            pass

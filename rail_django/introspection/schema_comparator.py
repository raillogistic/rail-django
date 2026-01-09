"""
Schema comparison module.

This module provides capabilities for comparing GraphQL schemas,
detecting changes, and generating migration reports.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .schema_introspector import FieldInfo, SchemaIntrospection, TypeInfo

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Types of schema changes."""
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    DEPRECATED = "DEPRECATED"
    UNDEPRECATED = "UNDEPRECATED"


class BreakingChangeLevel(Enum):
    """Levels of breaking changes."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SchemaChange:
    """Represents a change between two schemas."""
    change_type: ChangeType
    element_type: str  # 'type', 'field', 'argument', 'directive', etc.
    element_path: str  # e.g., 'User.email', 'Query.users'
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    description: str = ""
    breaking_level: BreakingChangeLevel = BreakingChangeLevel.NONE
    migration_notes: str = ""


@dataclass
class SchemaComparison:
    """Result of comparing two schemas."""
    old_schema_name: str
    new_schema_name: str
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    comparison_date: datetime = field(default_factory=datetime.now)

    # Changes by category
    type_changes: List[SchemaChange] = field(default_factory=list)
    field_changes: List[SchemaChange] = field(default_factory=list)
    argument_changes: List[SchemaChange] = field(default_factory=list)
    directive_changes: List[SchemaChange] = field(default_factory=list)

    # Summary statistics
    total_changes: int = 0
    breaking_changes: int = 0
    non_breaking_changes: int = 0

    # Breaking change analysis
    breaking_change_level: BreakingChangeLevel = BreakingChangeLevel.NONE
    migration_required: bool = False
    compatibility_score: float = 1.0  # 0.0 = completely incompatible, 1.0 = fully compatible

    def get_all_changes(self) -> List[SchemaChange]:
        """Get all changes as a single list."""
        return (self.type_changes + self.field_changes +
                self.argument_changes + self.directive_changes)

    def get_breaking_changes(self) -> List[SchemaChange]:
        """Get only breaking changes."""
        return [change for change in self.get_all_changes()
                if change.breaking_level != BreakingChangeLevel.NONE]

    def get_changes_by_type(self, change_type: ChangeType) -> List[SchemaChange]:
        """Get changes by type (ADDED, REMOVED, etc.)."""
        return [change for change in self.get_all_changes()
                if change.change_type == change_type]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'old_schema_name': self.old_schema_name,
            'new_schema_name': self.new_schema_name,
            'old_version': self.old_version,
            'new_version': self.new_version,
            'comparison_date': self.comparison_date.isoformat(),
            'summary': {
                'total_changes': self.total_changes,
                'breaking_changes': self.breaking_changes,
                'non_breaking_changes': self.non_breaking_changes,
                'breaking_change_level': self.breaking_change_level.value,
                'migration_required': self.migration_required,
                'compatibility_score': self.compatibility_score
            },
            'changes': {
                'type_changes': [self._change_to_dict(change) for change in self.type_changes],
                'field_changes': [self._change_to_dict(change) for change in self.field_changes],
                'argument_changes': [self._change_to_dict(change) for change in self.argument_changes],
                'directive_changes': [self._change_to_dict(change) for change in self.directive_changes]
            }
        }

    def _change_to_dict(self, change: SchemaChange) -> Dict[str, Any]:
        """Convert SchemaChange to dictionary."""
        return {
            'change_type': change.change_type.value,
            'element_type': change.element_type,
            'element_path': change.element_path,
            'old_value': change.old_value,
            'new_value': change.new_value,
            'description': change.description,
            'breaking_level': change.breaking_level.value,
            'migration_notes': change.migration_notes
        }


class SchemaComparator:
    """
    Comprehensive GraphQL schema comparator.

    Compares two schema introspections and identifies changes,
    breaking changes, and migration requirements.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Define breaking change rules
        self.breaking_change_rules = {
            'type_removed': BreakingChangeLevel.CRITICAL,
            'field_removed': BreakingChangeLevel.HIGH,
            'field_type_changed': BreakingChangeLevel.HIGH,
            'argument_removed': BreakingChangeLevel.MEDIUM,
            'argument_type_changed': BreakingChangeLevel.MEDIUM,
            'nullable_to_non_null': BreakingChangeLevel.HIGH,
            'list_to_non_list': BreakingChangeLevel.HIGH,
            'enum_value_removed': BreakingChangeLevel.MEDIUM,
            'interface_removed': BreakingChangeLevel.HIGH,
            'union_type_removed': BreakingChangeLevel.HIGH,
            'directive_removed': BreakingChangeLevel.LOW
        }

    def compare_schemas(self, old_schema: SchemaIntrospection,
                        new_schema: SchemaIntrospection) -> SchemaComparison:
        """
        Compare two schema introspections.

        Args:
            old_schema: Previous schema introspection
            new_schema: New schema introspection

        Returns:
            SchemaComparison with detailed change analysis
        """
        self.logger.info(f"Comparing schemas: {old_schema.schema_name} -> {new_schema.schema_name}")

        comparison = SchemaComparison(
            old_schema_name=old_schema.schema_name,
            new_schema_name=new_schema.schema_name,
            old_version=old_schema.version,
            new_version=new_schema.version
        )

        try:
            # Compare types
            self._compare_types(old_schema, new_schema, comparison)

            # Compare root fields
            self._compare_root_fields(old_schema, new_schema, comparison)

            # Compare directives
            self._compare_directives(old_schema, new_schema, comparison)

            # Calculate summary statistics
            self._calculate_summary(comparison)

            # Analyze breaking changes
            self._analyze_breaking_changes(comparison)

            self.logger.info(f"Schema comparison completed: {comparison.total_changes} changes found, "
                             f"{comparison.breaking_changes} breaking")

        except Exception as e:
            self.logger.error(f"Error during schema comparison: {e}")
            raise

        return comparison

    def _compare_types(self, old_schema: SchemaIntrospection,
                       new_schema: SchemaIntrospection, comparison: SchemaComparison):
        """Compare types between schemas."""
        old_types = set(old_schema.types.keys())
        new_types = set(new_schema.types.keys())

        # Added types
        for type_name in new_types - old_types:
            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='type',
                element_path=type_name,
                new_value=new_schema.types[type_name].kind,
                description=f"Type '{type_name}' was added",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.type_changes.append(change)

        # Removed types
        for type_name in old_types - new_types:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='type',
                element_path=type_name,
                old_value=old_schema.types[type_name].kind,
                description=f"Type '{type_name}' was removed",
                breaking_level=self.breaking_change_rules.get(
                    'type_removed', BreakingChangeLevel.CRITICAL),
                migration_notes=f"All references to '{type_name}' must be updated"
            )
            comparison.type_changes.append(change)

        # Modified types
        for type_name in old_types & new_types:
            old_type = old_schema.types[type_name]
            new_type = new_schema.types[type_name]

            self._compare_type_details(old_type, new_type, comparison)

    def _compare_type_details(self, old_type: TypeInfo, new_type: TypeInfo,
                              comparison: SchemaComparison):
        """Compare details of a specific type."""
        type_name = old_type.name

        # Check if type kind changed
        if old_type.kind != new_type.kind:
            change = SchemaChange(
                change_type=ChangeType.MODIFIED,
                element_type='type',
                element_path=f"{type_name}.kind",
                old_value=old_type.kind,
                new_value=new_type.kind,
                description=f"Type '{type_name}' kind changed from {old_type.kind} to {new_type.kind}",
                breaking_level=BreakingChangeLevel.CRITICAL,
                migration_notes=f"Type '{type_name}' structure completely changed"
            )
            comparison.type_changes.append(change)
            return  # No point comparing fields if type kind changed

        # Compare fields (for object/interface types)
        if old_type.kind in ['OBJECT', 'INTERFACE']:
            self._compare_fields(old_type, new_type, comparison)

        # Compare enum values
        elif old_type.kind == 'ENUM':
            self._compare_enum_values(old_type, new_type, comparison)

        # Compare input fields
        elif old_type.kind == 'INPUT_OBJECT':
            self._compare_input_fields(old_type, new_type, comparison)

        # Compare interfaces (for object types)
        if old_type.kind == 'OBJECT':
            self._compare_interfaces(old_type, new_type, comparison)

        # Compare union types
        elif old_type.kind == 'UNION':
            self._compare_union_types(old_type, new_type, comparison)

    def _compare_fields(self, old_type: TypeInfo, new_type: TypeInfo,
                        comparison: SchemaComparison):
        """Compare fields between two types."""
        old_fields = {field['name']: field for field in old_type.fields}
        new_fields = {field['name']: field for field in new_type.fields}

        old_field_names = set(old_fields.keys())
        new_field_names = set(new_fields.keys())

        # Added fields
        for field_name in new_field_names - old_field_names:
            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='field',
                element_path=f"{old_type.name}.{field_name}",
                new_value=new_fields[field_name]['type'],
                description=f"Field '{field_name}' was added to type '{old_type.name}'",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.field_changes.append(change)

        # Removed fields
        for field_name in old_field_names - new_field_names:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='field',
                element_path=f"{old_type.name}.{field_name}",
                old_value=old_fields[field_name]['type'],
                description=f"Field '{field_name}' was removed from type '{old_type.name}'",
                breaking_level=self.breaking_change_rules.get(
                    'field_removed', BreakingChangeLevel.HIGH),
                migration_notes=f"Remove all queries using '{old_type.name}.{field_name}'"
            )
            comparison.field_changes.append(change)

        # Modified fields
        for field_name in old_field_names & new_field_names:
            old_field = old_fields[field_name]
            new_field = new_fields[field_name]

            self._compare_field_details(old_type.name, old_field, new_field, comparison)

    def _compare_field_details(self, type_name: str, old_field: Dict[str, Any],
                               new_field: Dict[str, Any], comparison: SchemaComparison):
        """Compare details of a specific field."""
        field_name = old_field['name']
        field_path = f"{type_name}.{field_name}"

        # Check type changes
        if old_field['type'] != new_field['type']:
            breaking_level = self.breaking_change_rules.get(
                'field_type_changed', BreakingChangeLevel.HIGH)

            change = SchemaChange(
                change_type=ChangeType.MODIFIED,
                element_type='field',
                element_path=f"{field_path}.type",
                old_value=old_field['type'],
                new_value=new_field['type'],
                description=f"Field '{field_path}' type changed from {old_field['type']} to {new_field['type']}",
                breaking_level=breaking_level,
                migration_notes=f"Update queries using '{field_path}' to handle new type"
            )
            comparison.field_changes.append(change)

        # Check nullability changes
        old_nullable = old_field.get('is_nullable', True)
        new_nullable = new_field.get('is_nullable', True)

        if old_nullable and not new_nullable:
            change = SchemaChange(
                change_type=ChangeType.MODIFIED,
                element_type='field',
                element_path=f"{field_path}.nullable",
                old_value=old_nullable,
                new_value=new_nullable,
                description=f"Field '{field_path}' became non-nullable",
                breaking_level=self.breaking_change_rules.get(
                    'nullable_to_non_null', BreakingChangeLevel.HIGH),
                migration_notes=f"Ensure '{field_path}' always has a value"
            )
            comparison.field_changes.append(change)
        elif not old_nullable and new_nullable:
            change = SchemaChange(
                change_type=ChangeType.MODIFIED,
                element_type='field',
                element_path=f"{field_path}.nullable",
                old_value=old_nullable,
                new_value=new_nullable,
                description=f"Field '{field_path}' became nullable",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.field_changes.append(change)

        # Check deprecation changes
        old_deprecated = old_field.get('is_deprecated', False)
        new_deprecated = new_field.get('is_deprecated', False)

        if not old_deprecated and new_deprecated:
            change = SchemaChange(
                change_type=ChangeType.DEPRECATED,
                element_type='field',
                element_path=field_path,
                description=f"Field '{field_path}' was deprecated: {new_field.get('deprecation_reason', 'No reason provided')}",
                breaking_level=BreakingChangeLevel.LOW,
                migration_notes=f"Plan to migrate away from '{field_path}'"
            )
            comparison.field_changes.append(change)
        elif old_deprecated and not new_deprecated:
            change = SchemaChange(
                change_type=ChangeType.UNDEPRECATED,
                element_type='field',
                element_path=field_path,
                description=f"Field '{field_path}' is no longer deprecated",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.field_changes.append(change)

        # Compare arguments
        self._compare_arguments(field_path, old_field.get('args', []),
                                new_field.get('args', []), comparison)

    def _compare_arguments(self, field_path: str, old_args: List[Dict[str, Any]],
                           new_args: List[Dict[str, Any]], comparison: SchemaComparison):
        """Compare arguments between two fields."""
        old_args_dict = {arg['name']: arg for arg in old_args}
        new_args_dict = {arg['name']: arg for arg in new_args}

        old_arg_names = set(old_args_dict.keys())
        new_arg_names = set(new_args_dict.keys())

        # Added arguments
        for arg_name in new_arg_names - old_arg_names:
            new_arg = new_args_dict[arg_name]
            # Adding required arguments is breaking
            breaking_level = (BreakingChangeLevel.HIGH if '!' in new_arg['type']
                              else BreakingChangeLevel.NONE)

            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='argument',
                element_path=f"{field_path}({arg_name})",
                new_value=new_arg['type'],
                description=f"Argument '{arg_name}' was added to '{field_path}'",
                breaking_level=breaking_level,
                migration_notes=f"Update queries using '{field_path}' to include '{arg_name}'" if breaking_level != BreakingChangeLevel.NONE else ""
            )
            comparison.argument_changes.append(change)

        # Removed arguments
        for arg_name in old_arg_names - new_arg_names:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='argument',
                element_path=f"{field_path}({arg_name})",
                old_value=old_args_dict[arg_name]['type'],
                description=f"Argument '{arg_name}' was removed from '{field_path}'",
                breaking_level=self.breaking_change_rules.get(
                    'argument_removed', BreakingChangeLevel.MEDIUM),
                migration_notes=f"Remove '{arg_name}' argument from queries using '{field_path}'"
            )
            comparison.argument_changes.append(change)

        # Modified arguments
        for arg_name in old_arg_names & new_arg_names:
            old_arg = old_args_dict[arg_name]
            new_arg = new_args_dict[arg_name]

            if old_arg['type'] != new_arg['type']:
                change = SchemaChange(
                    change_type=ChangeType.MODIFIED,
                    element_type='argument',
                    element_path=f"{field_path}({arg_name})",
                    old_value=old_arg['type'],
                    new_value=new_arg['type'],
                    description=f"Argument '{arg_name}' type changed in '{field_path}'",
                    breaking_level=self.breaking_change_rules.get(
                        'argument_type_changed', BreakingChangeLevel.MEDIUM),
                    migration_notes=f"Update '{arg_name}' argument usage in '{field_path}'"
                )
                comparison.argument_changes.append(change)

    def _compare_enum_values(self, old_type: TypeInfo, new_type: TypeInfo,
                             comparison: SchemaComparison):
        """Compare enum values between two enum types."""
        old_values = {val['name']: val for val in old_type.enum_values}
        new_values = {val['name']: val for val in new_type.enum_values}

        old_value_names = set(old_values.keys())
        new_value_names = set(new_values.keys())

        # Added enum values
        for value_name in new_value_names - old_value_names:
            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='enum_value',
                element_path=f"{old_type.name}.{value_name}",
                description=f"Enum value '{value_name}' was added to '{old_type.name}'",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.type_changes.append(change)

        # Removed enum values
        for value_name in old_value_names - new_value_names:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='enum_value',
                element_path=f"{old_type.name}.{value_name}",
                description=f"Enum value '{value_name}' was removed from '{old_type.name}'",
                breaking_level=self.breaking_change_rules.get(
                    'enum_value_removed', BreakingChangeLevel.MEDIUM),
                migration_notes=f"Replace usage of '{old_type.name}.{value_name}' with alternative values"
            )
            comparison.type_changes.append(change)

    def _compare_input_fields(self, old_type: TypeInfo, new_type: TypeInfo,
                              comparison: SchemaComparison):
        """Compare input fields between two input types."""
        old_fields = {field['name']: field for field in old_type.input_fields}
        new_fields = {field['name']: field for field in new_type.input_fields}

        old_field_names = set(old_fields.keys())
        new_field_names = set(new_fields.keys())

        # Added input fields
        for field_name in new_field_names - old_field_names:
            new_field = new_fields[field_name]
            # Adding required input fields is breaking
            breaking_level = (BreakingChangeLevel.HIGH if '!' in new_field['type']
                              else BreakingChangeLevel.NONE)

            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='input_field',
                element_path=f"{old_type.name}.{field_name}",
                new_value=new_field['type'],
                description=f"Input field '{field_name}' was added to '{old_type.name}'",
                breaking_level=breaking_level,
                migration_notes=f"Update input objects using '{old_type.name}' to include '{field_name}'" if breaking_level != BreakingChangeLevel.NONE else ""
            )
            comparison.field_changes.append(change)

        # Removed input fields
        for field_name in old_field_names - new_field_names:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='input_field',
                element_path=f"{old_type.name}.{field_name}",
                old_value=old_fields[field_name]['type'],
                description=f"Input field '{field_name}' was removed from '{old_type.name}'",
                breaking_level=BreakingChangeLevel.MEDIUM,
                migration_notes=f"Remove '{field_name}' from input objects using '{old_type.name}'"
            )
            comparison.field_changes.append(change)

    def _compare_interfaces(self, old_type: TypeInfo, new_type: TypeInfo,
                            comparison: SchemaComparison):
        """Compare interfaces implemented by object types."""
        old_interfaces = set(old_type.interfaces)
        new_interfaces = set(new_type.interfaces)

        # Removed interfaces
        for interface_name in old_interfaces - new_interfaces:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='interface',
                element_path=f"{old_type.name}.implements.{interface_name}",
                description=f"Type '{old_type.name}' no longer implements '{interface_name}'",
                breaking_level=self.breaking_change_rules.get(
                    'interface_removed', BreakingChangeLevel.HIGH),
                migration_notes=f"Update queries expecting '{old_type.name}' to implement '{interface_name}'"
            )
            comparison.type_changes.append(change)

        # Added interfaces
        for interface_name in new_interfaces - old_interfaces:
            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='interface',
                element_path=f"{old_type.name}.implements.{interface_name}",
                description=f"Type '{old_type.name}' now implements '{interface_name}'",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.type_changes.append(change)

    def _compare_union_types(self, old_type: TypeInfo, new_type: TypeInfo,
                             comparison: SchemaComparison):
        """Compare union member types."""
        old_types = set(old_type.possible_types)
        new_types = set(new_type.possible_types)

        # Removed union types
        for type_name in old_types - new_types:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='union_type',
                element_path=f"{old_type.name}.{type_name}",
                description=f"Type '{type_name}' was removed from union '{old_type.name}'",
                breaking_level=self.breaking_change_rules.get(
                    'union_type_removed', BreakingChangeLevel.HIGH),
                migration_notes=f"Update queries handling '{old_type.name}' union to remove '{type_name}' cases"
            )
            comparison.type_changes.append(change)

        # Added union types
        for type_name in new_types - old_types:
            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='union_type',
                element_path=f"{old_type.name}.{type_name}",
                description=f"Type '{type_name}' was added to union '{old_type.name}'",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.type_changes.append(change)

    def _compare_root_fields(self, old_schema: SchemaIntrospection,
                             new_schema: SchemaIntrospection, comparison: SchemaComparison):
        """Compare root fields (Query, Mutation, Subscription)."""
        # Compare queries
        self._compare_root_field_list("Query", old_schema.queries, new_schema.queries, comparison)

        # Compare mutations
        self._compare_root_field_list("Mutation", old_schema.mutations,
                                      new_schema.mutations, comparison)

        # Compare subscriptions
        self._compare_root_field_list(
            "Subscription", old_schema.subscriptions, new_schema.subscriptions, comparison)

    def _compare_root_field_list(self, root_type: str, old_fields: List[FieldInfo],
                                 new_fields: List[FieldInfo], comparison: SchemaComparison):
        """Compare a list of root fields."""
        old_fields_dict = {field.name: field for field in old_fields}
        new_fields_dict = {field.name: field for field in new_fields}

        old_field_names = set(old_fields_dict.keys())
        new_field_names = set(new_fields_dict.keys())

        # Added fields
        for field_name in new_field_names - old_field_names:
            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='root_field',
                element_path=f"{root_type}.{field_name}",
                new_value=new_fields_dict[field_name].type,
                description=f"{root_type} field '{field_name}' was added",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.field_changes.append(change)

        # Removed fields
        for field_name in old_field_names - new_field_names:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='root_field',
                element_path=f"{root_type}.{field_name}",
                old_value=old_fields_dict[field_name].type,
                description=f"{root_type} field '{field_name}' was removed",
                breaking_level=self.breaking_change_rules.get(
                    'field_removed', BreakingChangeLevel.HIGH),
                migration_notes=f"Remove all queries using '{root_type}.{field_name}'"
            )
            comparison.field_changes.append(change)

        # Modified fields
        for field_name in old_field_names & new_field_names:
            old_field = old_fields_dict[field_name]
            new_field = new_fields_dict[field_name]

            # Convert FieldInfo to dict for comparison
            old_field_dict = {
                'name': old_field.name,
                'type': old_field.type,
                'args': old_field.args,
                'is_deprecated': old_field.is_deprecated,
                'deprecation_reason': old_field.deprecation_reason,
                'is_nullable': old_field.is_nullable
            }
            new_field_dict = {
                'name': new_field.name,
                'type': new_field.type,
                'args': new_field.args,
                'is_deprecated': new_field.is_deprecated,
                'deprecation_reason': new_field.deprecation_reason,
                'is_nullable': new_field.is_nullable
            }

            self._compare_field_details(root_type, old_field_dict, new_field_dict, comparison)

    def _compare_directives(self, old_schema: SchemaIntrospection,
                            new_schema: SchemaIntrospection, comparison: SchemaComparison):
        """Compare directives between schemas."""
        old_directives = set(old_schema.directives.keys())
        new_directives = set(new_schema.directives.keys())

        # Added directives
        for directive_name in new_directives - old_directives:
            change = SchemaChange(
                change_type=ChangeType.ADDED,
                element_type='directive',
                element_path=f"@{directive_name}",
                description=f"Directive '@{directive_name}' was added",
                breaking_level=BreakingChangeLevel.NONE
            )
            comparison.directive_changes.append(change)

        # Removed directives
        for directive_name in old_directives - new_directives:
            change = SchemaChange(
                change_type=ChangeType.REMOVED,
                element_type='directive',
                element_path=f"@{directive_name}",
                description=f"Directive '@{directive_name}' was removed",
                breaking_level=self.breaking_change_rules.get(
                    'directive_removed', BreakingChangeLevel.LOW),
                migration_notes=f"Remove usage of '@{directive_name}' directive"
            )
            comparison.directive_changes.append(change)

    def _calculate_summary(self, comparison: SchemaComparison):
        """Calculate summary statistics for the comparison."""
        all_changes = comparison.get_all_changes()
        comparison.total_changes = len(all_changes)

        breaking_changes = [change for change in all_changes
                            if change.breaking_level != BreakingChangeLevel.NONE]
        comparison.breaking_changes = len(breaking_changes)
        comparison.non_breaking_changes = comparison.total_changes - comparison.breaking_changes

    def _analyze_breaking_changes(self, comparison: SchemaComparison):
        """Analyze breaking changes and determine overall impact."""
        breaking_changes = comparison.get_breaking_changes()

        if not breaking_changes:
            comparison.breaking_change_level = BreakingChangeLevel.NONE
            comparison.migration_required = False
            comparison.compatibility_score = 1.0
            return

        # Determine highest breaking change level
        max_level = max(change.breaking_level for change in breaking_changes)
        comparison.breaking_change_level = max_level

        # Determine if migration is required
        comparison.migration_required = max_level in [
            BreakingChangeLevel.HIGH,
            BreakingChangeLevel.CRITICAL
        ]

        # Calculate compatibility score
        level_weights = {
            BreakingChangeLevel.LOW: 0.1,
            BreakingChangeLevel.MEDIUM: 0.3,
            BreakingChangeLevel.HIGH: 0.6,
            BreakingChangeLevel.CRITICAL: 1.0
        }

        total_impact = sum(level_weights.get(change.breaking_level, 0)
                           for change in breaking_changes)

        # Normalize by total changes (with minimum impact)
        max_possible_impact = comparison.total_changes * 1.0
        comparison.compatibility_score = max(
            0.0, 1.0 - (total_impact / max(max_possible_impact, 1.0)))

"""
Schema validation module.

This module provides comprehensive validation for GraphQL schemas including
configuration validation, schema structure validation, and conflict detection.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from graphql import GraphQLSchema, build_ast_schema, validate
from graphql.error import GraphQLError

from .error_handlers import (
    InvalidSchemaConfigError,
    SchemaConflictError,
    SchemaValidationError,
    ValidationErrorHandler,
    handle_validation_exception,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of schema validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    info: List[str]
    schema_name: str
    validation_details: Dict[str, Any]

    @property
    def has_errors(self) -> bool:
        """Check if validation has errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if validation has warnings."""
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'is_valid': self.is_valid,
            'schema_name': self.schema_name,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'info_count': len(self.info),
            'errors': self.errors,
            'warnings': self.warnings,
            'info': self.info,
            'validation_details': self.validation_details
        }


class SchemaValidator:
    """
    Comprehensive schema validator for GraphQL schemas.

    Validates schema configuration, GraphQL schema structure,
    and detects conflicts between schemas.
    """

    # Schema name validation pattern
    SCHEMA_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*$')

    # Reserved schema names
    RESERVED_NAMES = {'admin', 'api', 'graphql', 'schema', 'introspection'}

    # Maximum schema name length
    MAX_SCHEMA_NAME_LENGTH = 50

    def __init__(self):
        self.error_handler = ValidationErrorHandler()

    @handle_validation_exception
    def validate_schema(self, schema_info) -> ValidationResult:
        """
        Validate a complete schema configuration and GraphQL schema.

        Args:
            schema_info: Schema information object containing name, schema, etc.

        Returns:
            ValidationResult with validation details

        Raises:
            SchemaValidationError: If validation fails
        """
        self.error_handler.clear()

        # Validate schema configuration
        self._validate_schema_config(schema_info)

        # Validate GraphQL schema
        if hasattr(schema_info, 'schema') and schema_info.schema:
            self._validate_graphql_schema(schema_info.schema, schema_info.name)

        # Validate Django app dependencies
        if hasattr(schema_info, 'apps') and schema_info.apps:
            self._validate_django_apps(schema_info.apps, schema_info.name)

        # Validate schema metadata
        self._validate_schema_metadata(schema_info)

        # Create validation result
        result = ValidationResult(
            is_valid=not self.error_handler.has_errors(),
            errors=[error.message for error in self.error_handler.errors],
            warnings=[warning.message for warning in self.error_handler.warnings],
            info=[],
            schema_name=getattr(schema_info, 'name', 'unknown'),
            validation_details=self._get_validation_details(schema_info)
        )

        logger.info(f"Schema validation completed for '{result.schema_name}': "
                    f"valid={result.is_valid}, errors={len(result.errors)}, "
                    f"warnings={len(result.warnings)}")

        return result

    def _validate_schema_config(self, schema_info):
        """Validate basic schema configuration."""
        # Validate schema name
        if not hasattr(schema_info, 'name') or not schema_info.name:
            self.error_handler.add_error(
                'name',
                'Schema name is required',
                'MISSING_SCHEMA_NAME'
            )
            return

        name = schema_info.name

        # Check name format
        if not self.SCHEMA_NAME_PATTERN.match(name):
            self.error_handler.add_error(
                'name',
                f"Schema name '{name}' must start with a letter and contain only "
                "letters, numbers, underscores, and hyphens",
                'INVALID_SCHEMA_NAME_FORMAT'
            )

        # Check name length
        if len(name) > self.MAX_SCHEMA_NAME_LENGTH:
            self.error_handler.add_error(
                'name',
                f"Schema name '{name}' exceeds maximum length of {self.MAX_SCHEMA_NAME_LENGTH}",
                'SCHEMA_NAME_TOO_LONG'
            )

        # Check reserved names
        if name.lower() in self.RESERVED_NAMES:
            self.error_handler.add_error(
                'name',
                f"Schema name '{name}' is reserved and cannot be used",
                'RESERVED_SCHEMA_NAME'
            )

        # Validate required GraphQL schema
        if not hasattr(schema_info, 'schema') or not schema_info.schema:
            self.error_handler.add_error(
                'schema',
                'GraphQL schema is required',
                'MISSING_GRAPHQL_SCHEMA'
            )

    def _validate_graphql_schema(self, graphql_schema: GraphQLSchema, schema_name: str):
        """Validate GraphQL schema structure."""
        try:
            # Validate schema using GraphQL's built-in validation
            validation_errors = validate(graphql_schema, [])

            if validation_errors:
                for error in validation_errors:
                    self.error_handler.add_error(
                        'schema',
                        f"GraphQL schema validation error: {error.message}",
                        'GRAPHQL_SCHEMA_ERROR'
                    )

            # Check for required Query type
            if not graphql_schema.query_type:
                self.error_handler.add_error(
                    'schema',
                    'GraphQL schema must have a Query type',
                    'MISSING_QUERY_TYPE'
                )

            # Validate schema complexity
            self._validate_schema_complexity(graphql_schema, schema_name)

            # Check for deprecated fields
            self._check_deprecated_fields(graphql_schema, schema_name)

        except GraphQLError as e:
            self.error_handler.add_error(
                'schema',
                f"Invalid GraphQL schema: {e.message}",
                'INVALID_GRAPHQL_SCHEMA'
            )
        except Exception as e:
            self.error_handler.add_error(
                'schema',
                f"Error validating GraphQL schema: {str(e)}",
                'SCHEMA_VALIDATION_ERROR'
            )

    def _validate_django_apps(self, app_names: List[str], schema_name: str):
        """Validate Django app dependencies."""
        for app_name in app_names:
            try:
                apps.get_app_config(app_name)
            except LookupError:
                self.error_handler.add_error(
                    'apps',
                    f"Django app '{app_name}' not found or not installed",
                    'MISSING_DJANGO_APP'
                )
            except Exception as e:
                self.error_handler.add_error(
                    'apps',
                    f"Error validating Django app '{app_name}': {str(e)}",
                    'DJANGO_APP_ERROR'
                )

    def _validate_schema_metadata(self, schema_info):
        """Validate schema metadata."""
        # Validate version format if provided
        if hasattr(schema_info, 'version') and schema_info.version:
            version = schema_info.version
            version_pattern = re.compile(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$')
            if not version_pattern.match(version):
                self.error_handler.add_warning(
                    'version',
                    f"Version '{version}' does not follow semantic versioning (x.y.z)",
                    'INVALID_VERSION_FORMAT'
                )

        # Validate description length
        if hasattr(schema_info, 'description') and schema_info.description:
            if len(schema_info.description) > 500:
                self.error_handler.add_warning(
                    'description',
                    'Schema description is very long (>500 characters)',
                    'LONG_DESCRIPTION'
                )

    def _validate_schema_complexity(self, graphql_schema: GraphQLSchema, schema_name: str):
        """Validate schema complexity metrics."""
        try:
            type_map = graphql_schema.type_map

            # Count types
            type_count = len([t for name, t in type_map.items()
                              if not name.startswith('__')])

            if type_count > 100:
                self.error_handler.add_warning(
                    'schema',
                    f"Schema has {type_count} types, which may impact performance",
                    'HIGH_TYPE_COUNT'
                )

            # Check for circular references (simplified check)
            self._check_circular_references(graphql_schema)

        except Exception as e:
            logger.warning(f"Could not validate schema complexity for '{schema_name}': {e}")

    def _check_circular_references(self, graphql_schema: GraphQLSchema):
        """Check for potential circular references in schema."""
        # This is a simplified check - a full implementation would be more complex
        visited = set()

        def check_type(type_obj, path: Set[str]):
            if hasattr(type_obj, 'name') and type_obj.name in path:
                self.error_handler.add_warning(
                    'schema',
                    f"Potential circular reference detected involving type '{type_obj.name}'",
                    'CIRCULAR_REFERENCE'
                )
                return

            # Add more sophisticated circular reference detection here

        # Start checking from Query type
        if graphql_schema.query_type:
            check_type(graphql_schema.query_type, set())

    def _check_deprecated_fields(self, graphql_schema: GraphQLSchema, schema_name: str):
        """Check for deprecated fields in schema."""
        deprecated_count = 0

        try:
            for type_name, type_obj in graphql_schema.type_map.items():
                if hasattr(type_obj, 'fields'):
                    for field_name, field in type_obj.fields.items():
                        if hasattr(field, 'deprecation_reason') and field.deprecation_reason:
                            deprecated_count += 1

            if deprecated_count > 0:
                self.error_handler.add_info(
                    'schema',
                    f"Schema contains {deprecated_count} deprecated field(s)",
                    'DEPRECATED_FIELDS'
                )
        except Exception as e:
            logger.warning(f"Could not check deprecated fields for '{schema_name}': {e}")

    def _get_validation_details(self, schema_info) -> Dict[str, Any]:
        """Get detailed validation information."""
        details = {
            'schema_name': getattr(schema_info, 'name', 'unknown'),
            'has_graphql_schema': hasattr(schema_info, 'schema') and schema_info.schema is not None,
            'has_apps': hasattr(schema_info, 'apps') and bool(schema_info.apps),
            'has_version': hasattr(schema_info, 'version') and bool(schema_info.version),
            'has_description': hasattr(schema_info, 'description') and bool(schema_info.description),
        }

        # Add schema complexity metrics if available
        if hasattr(schema_info, 'schema') and schema_info.schema:
            try:
                type_map = schema_info.schema.type_map
                details['type_count'] = len([t for name, t in type_map.items()
                                             if not name.startswith('__')])
                details['has_mutations'] = schema_info.schema.mutation_type is not None
                details['has_subscriptions'] = schema_info.schema.subscription_type is not None
            except Exception:
                pass

        return details

    def validate_schema_conflict(self, new_schema_info, existing_schema_info) -> ValidationResult:
        """
        Validate potential conflicts between schemas.

        Args:
            new_schema_info: New schema being registered
            existing_schema_info: Existing schema with same name

        Returns:
            ValidationResult indicating conflicts
        """
        self.error_handler.clear()

        # Check version conflicts
        if (hasattr(new_schema_info, 'version') and hasattr(existing_schema_info, 'version') and
                new_schema_info.version and existing_schema_info.version):

            if new_schema_info.version == existing_schema_info.version:
                self.error_handler.add_error(
                    'version',
                    f"Schema version '{new_schema_info.version}' already exists",
                    'DUPLICATE_VERSION'
                )
            elif new_schema_info.version < existing_schema_info.version:
                self.error_handler.add_warning(
                    'version',
                    f"New version '{new_schema_info.version}' is older than existing "
                    f"version '{existing_schema_info.version}'",
                    'OLDER_VERSION'
                )

        # Check for breaking changes (simplified)
        if hasattr(new_schema_info, 'schema') and hasattr(existing_schema_info, 'schema'):
            self._check_breaking_changes(new_schema_info.schema, existing_schema_info.schema)

        return ValidationResult(
            is_valid=not self.error_handler.has_errors(),
            errors=[error.message for error in self.error_handler.errors],
            warnings=[warning.message for warning in self.error_handler.warnings],
            info=[],
            schema_name=getattr(new_schema_info, 'name', 'unknown'),
            validation_details={'conflict_check': True}
        )

    def _check_breaking_changes(self, new_schema: GraphQLSchema, existing_schema: GraphQLSchema):
        """Check for breaking changes between schema versions."""
        try:
            # This is a simplified check - a full implementation would be more comprehensive
            new_types = set(new_schema.type_map.keys())
            existing_types = set(existing_schema.type_map.keys())

            # Check for removed types
            removed_types = existing_types - new_types
            if removed_types:
                for type_name in removed_types:
                    if not type_name.startswith('__'):  # Skip introspection types
                        self.error_handler.add_error(
                            'schema',
                            f"Breaking change: Type '{type_name}' was removed",
                            'BREAKING_CHANGE_REMOVED_TYPE'
                        )

            # Check for added types (usually not breaking, but worth noting)
            added_types = new_types - existing_types
            if added_types:
                non_introspection_added = [t for t in added_types if not t.startswith('__')]
                if non_introspection_added:
                    self.error_handler.add_info(
                        'schema',
                        f"Added {len(non_introspection_added)} new type(s): {', '.join(non_introspection_added[:5])}",
                        'SCHEMA_EVOLUTION_NEW_TYPES'
                    )

        except Exception as e:
            logger.warning(f"Could not check breaking changes: {e}")

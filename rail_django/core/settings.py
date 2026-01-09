"""
Settings module for Django GraphQL Auto-Generation.

This module defines the configuration classes used to customize the behavior
of the GraphQL schema generation process with hierarchical settings loading.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, Union

import graphene
from django.conf import settings as django_settings
from django.db.models import Field


def _merge_settings_dicts(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge multiple settings dictionaries with later ones taking precedence.

    Args:
        *dicts: Variable number of dictionaries to merge

    Returns:
        Dict[str, Any]: Merged dictionary
    """
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result


def _get_schema_registry_settings(schema_name: str) -> Dict[str, Any]:
    """
    Get settings from schema registry for a specific schema.

    Args:
        schema_name: Name of the schema

    Returns:
        Dict[str, Any]: Schema registry settings
    """
    try:
        from .registry import schema_registry

        schema_info = schema_registry.get_schema(schema_name)

        return schema_info.settings if schema_info else {}
    except (ImportError, AttributeError):
        return {}


def _get_global_settings(schema_name: str) -> Dict[str, Any]:
    """
    Get global settings from Django settings for a specific schema.

    Args:
        schema_name: Name of the schema

    Returns:
        Dict[str, Any]: Global settings for the schema
    """
    rail_settings = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {})
    # Primary: schema-scoped settings (e.g., {"default": { ... }})
    if schema_name in rail_settings:
        return rail_settings.get(schema_name, {})

    # Fallback: legacy/global settings (unscoped)
    # If the dictionary already looks like a settings block with known keys,
    # return it directly so projects that didn't namespace by schema keep working.
    known_section_keys = {
        "schema_settings",
        "query_settings",
        "mutation_settings",
        "TYPE_SETTINGS",
        "FILTERING",
        "PAGINATION",
        "SECURITY",
        "PERFORMANCE",
        "CUSTOM_SCALARS",
        "FIELD_CONVERTERS",
        "SCHEMA_HOOKS",
        "MIDDLEWARE",
        "NESTED_OPERATIONS",
        "RELATIONSHIP_HANDLING",
        "DEVELOPMENT",
        "I18N",
    }
    if any(k in rail_settings for k in known_section_keys):
        return rail_settings

    return {}


def _get_library_defaults() -> Dict[str, Any]:
    """
    Get library default settings.

    Returns:
        Dict[str, Any]: Library default settings
    """
    try:
        from ..defaults import LIBRARY_DEFAULTS

        return LIBRARY_DEFAULTS.copy()
    except ImportError:
        return {}


@dataclass
class TypeGeneratorSettings:
    """Settings for controlling GraphQL type generation."""

    # Fields to exclude from types, per model
    exclude_fields: Dict[str, List[str]] = field(default_factory=dict)
    excluded_fields: Dict[str, List[str]] = field(
        default_factory=dict
    )  # Alias for exclude_fields

    # Fields to include in types, per model (if None, include all non-excluded fields)
    include_fields: Optional[Dict[str, List[str]]] = None

    # Custom field type mappings
    custom_field_mappings: Dict[Type[Field], Type[graphene.Scalar]] = field(
        default_factory=dict
    )

    # Enable filter generation for types
    generate_filters: bool = True

    # Enable filtering support (alias for generate_filters)
    enable_filtering: bool = True

    # Enable auto-camelcase for field names
    auto_camelcase: bool = False

    # Enable field descriptions
    generate_descriptions: bool = True

    @classmethod
    def from_schema(cls, schema_name: str) -> "TypeGeneratorSettings":
        """
        Create TypeGeneratorSettings with hierarchical loading.

        Priority order:
        1. Schema registry settings
        2. Global Django settings
        3. Library defaults

        Args:
            schema_name: Name of the schema

        Returns:
            TypeGeneratorSettings: Configured settings instance
        """
        # Get settings from all sources
        defaults = _get_library_defaults().get("type_generation_settings", {})
        global_settings = _get_global_settings(schema_name).get(
            "type_generation_settings", {}
        )
        schema_settings = _get_schema_registry_settings(schema_name).get(
            "type_generation_settings", {}
        )

        # Merge settings with proper priority
        merged_settings = _merge_settings_dicts(
            defaults, global_settings, schema_settings
        )

        # Filter to only include valid fields for this dataclass
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {
            k: v for k, v in merged_settings.items() if k in valid_fields
        }

        return cls(**filtered_settings)


@dataclass
class QueryGeneratorSettings:
    """Settings for controlling GraphQL query generation."""

    # Enable filtering support
    generate_filters: bool = True

    # Enable ordering support
    generate_ordering: bool = True

    # Enable pagination support
    generate_pagination: bool = True

    # Enable pagination support (alias for generate_pagination)
    enable_pagination: bool = True

    # Enable ordering support (alias for generate_ordering)
    enable_ordering: bool = True

    # Enable Relay-style pagination
    use_relay: bool = False

    # Default page size for paginated queries
    default_page_size: int = 20

    # Maximum allowed page size
    max_page_size: int = 100

    # Maximum number of buckets returned by grouping queries
    max_grouping_buckets: int = 200

    # Additional fields to use for lookups (e.g., slug, uuid)
    additional_lookup_fields: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_schema(cls, schema_name: str) -> "QueryGeneratorSettings":
        """
        Create QueryGeneratorSettings with hierarchical loading.

        Priority order:
        1. Schema registry settings
        2. Global Django settings
        3. Library defaults

        Args:
            schema_name: Name of the schema

        Returns:
            QueryGeneratorSettings: Configured settings instance
        """
        # Get settings from all sources
        defaults = _get_library_defaults().get("query_settings", {})
        global_settings = _get_global_settings(schema_name).get("query_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get(
            "query_settings", {}
        )

        # Merge settings with proper priority
        merged_settings = _merge_settings_dicts(
            defaults, global_settings, schema_settings
        )

        # Filter to only include valid fields for this dataclass
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {
            k: v for k, v in merged_settings.items() if k in valid_fields
        }

        return cls(**filtered_settings)


@dataclass
class MutationGeneratorSettings:
    """Settings for controlling GraphQL mutation generation."""

    # Enable create mutations
    generate_create: bool = True

    # Enable update mutations
    generate_update: bool = True

    # Enable delete mutations
    generate_delete: bool = True

    # Enable bulk mutations
    generate_bulk: bool = False

    # Enable create mutations (alias for generate_create)
    enable_create: bool = True

    # Enable update mutations (alias for generate_update)
    enable_update: bool = True

    # Enable delete mutations (alias for generate_delete)
    enable_delete: bool = True

    # Enable bulk operations
    enable_bulk_operations: bool = False

    # Enable method mutations
    enable_method_mutations: bool = True

    # Maximum number of items in bulk operations
    bulk_batch_size: int = 100

    # Fields required for update operations
    required_update_fields: Dict[str, List[str]] = field(default_factory=dict)

    # NEW: Enable/disable nested relationship fields in mutations
    enable_nested_relations: bool = True

    # NEW: Per-model configuration for nested relations
    nested_relations_config: Dict[str, bool] = field(default_factory=dict)

    # NEW: Per-field configuration for nested relations (model.field -> bool)
    nested_field_config: Dict[str, Dict[str, bool]] = field(default_factory=dict)

    @classmethod
    def from_schema(cls, schema_name: str) -> "MutationGeneratorSettings":
        """
        Create MutationGeneratorSettings with hierarchical loading.

        Priority order:
        1. Schema registry settings
        2. Global Django settings
        3. Library defaults

        Args:
            schema_name: Name of the schema

        Returns:
            MutationGeneratorSettings: Configured settings instance
        """
        # Get settings from all sources
        defaults = _get_library_defaults().get("mutation_settings", {})
        global_settings = _get_global_settings(schema_name).get("mutation_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get(
            "mutation_settings", {}
        )

        # Merge settings with proper priority
        merged_settings = _merge_settings_dicts(
            defaults, global_settings, schema_settings
        )

        # Filter to only include valid fields for this dataclass
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {
            k: v for k, v in merged_settings.items() if k in valid_fields
        }

        return cls(**filtered_settings)


@dataclass
class SchemaSettings:
    """Settings for controlling overall schema behavior."""

    # Apps to exclude from schema generation
    excluded_apps: List[str] = field(default_factory=list)

    # Models to exclude from schema generation
    excluded_models: List[str] = field(default_factory=list)

    # Enable schema introspection
    enable_introspection: bool = True

    # Enable GraphiQL interface
    enable_graphiql: bool = True

    # Auto-refresh schema when models change
    auto_refresh_on_model_change: bool = False

    # Auto-refresh schema after Django migrations
    auto_refresh_on_migration: bool = True

    # Prebuild GraphQL schema on server startup (AppConfig.ready)
    prebuild_on_startup: bool = False

    # Require authentication for the schema by default
    authentication_required: bool = True

    # Enable pagination support
    enable_pagination: bool = True

    # Enable auto-camelcase for GraphQL schema
    auto_camelcase: bool = False

    # Disable security mutations (e.g., login, logout)
    disable_security_mutations: bool = False

    # Enable model metadata exposure for frontend rich tables and forms
    show_metadata: bool = False

    # Custom GraphQL query extensions loaded by path
    query_extensions: List[str] = field(default_factory=list)

    # Custom GraphQL mutation extensions loaded by path
    mutation_extensions: List[str] = field(default_factory=list)

    @classmethod
    def from_schema(cls, schema_name: str) -> "SchemaSettings":
        """
        Create SchemaSettings with hierarchical loading.

        Priority order:
        1. Schema registry settings
        2. Global Django settings
        3. Library defaults

        Args:
            schema_name: Name of the schema

        Returns:
            SchemaSettings: Configured settings instance
        """
        # Get settings from all sources
        defaults = _get_library_defaults().get("schema_settings", {})
        global_settings = _get_global_settings(schema_name).get("schema_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get(
            "schema_settings", {}
        )
        # Also check for direct schema-level settings (backward compatibility)
        schema_registry_settings = _get_schema_registry_settings(schema_name)
        direct_settings = {
            k: v
            for k, v in schema_registry_settings.items()
            if k in cls.__dataclass_fields__
        }

        # Merge settings with proper priority
        merged_settings = _merge_settings_dicts(
            defaults, global_settings, schema_settings, direct_settings
        )

        # Filter to only include valid fields for this dataclass
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {
            k: v for k, v in merged_settings.items() if k in valid_fields
        }

        return cls(**filtered_settings)


class GraphQLAutoConfig:
    """
    Configuration class for managing model-specific GraphQL auto-generation settings.
    """

    def __init__(
        self,
        type_settings: Optional[TypeGeneratorSettings] = None,
        query_settings: Optional[QueryGeneratorSettings] = None,
        mutation_settings: Optional[MutationGeneratorSettings] = None,
        schema_settings: Optional[SchemaSettings] = None,
    ):
        self.type_settings = type_settings or TypeGeneratorSettings()
        self.query_settings = query_settings or QueryGeneratorSettings()
        self.mutation_settings = mutation_settings or MutationGeneratorSettings()
        self.schema_settings = schema_settings or SchemaSettings()

    def should_include_model(self, model_name: str) -> bool:
        """
        Determine if a model should be included in the schema.

        Args:
            model_name: The name of the model to check

        Returns:
            bool: True if the model should be included, False otherwise
        """
        return (
            model_name not in self.schema_settings.excluded_models
            and model_name not in self.schema_settings.excluded_apps
        )

    def should_include_field(self, model_name: str, field_name: str) -> bool:
        """
        Determine if a field should be included in the schema.

        Args:
            model_name: The name of the model containing the field
            field_name: The name of the field to check

        Returns:
            bool: True if the field should be included, False otherwise
        """
        # Check excluded fields
        excluded = set()
        excluded.update(self.type_settings.exclude_fields.get(model_name, []))
        excluded.update(self.type_settings.excluded_fields.get(model_name, []))
        if field_name in excluded:
            return False

        # Check included fields
        if self.type_settings.include_fields is not None:
            included = self.type_settings.include_fields.get(model_name, [])
            return field_name in included

        return True

    def get_additional_lookup_fields(self, model_name: str) -> List[str]:
        """
        Get additional lookup fields for a model.

        Args:
            model_name: The name of the model

        Returns:
            List[str]: List of additional lookup field names
        """
        return self.query_settings.additional_lookup_fields.get(model_name, [])

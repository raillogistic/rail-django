"""
Configuration management for Rail Django GraphQL.

This module provides a settings proxy that handles hierarchical configuration
resolution from schema-specific, Django global, and library default settings.
"""

from typing import Any, Dict, Optional

from django.conf import settings

# Import comprehensive library defaults from defaults.py
from .defaults import LIBRARY_DEFAULTS


class SettingsProxy:
    """
    Proxy for accessing Rail Django GraphQL settings with hierarchical resolution.

    Settings are resolved in the following order:
    1. Schema-specific settings (RAIL_DJANGO_GRAPHQL_SCHEMAS[schema_name])
    2. Global Django settings (RAIL_DJANGO_GRAPHQL)
    3. Library defaults (LIBRARY_DEFAULTS)
    """

    def __init__(self, schema_name: Optional[str] = None):
        """
        Initialize the settings proxy.

        Args:
            schema_name: Name of the schema for schema-specific settings
        """
        self.schema_name = schema_name
        self._cache: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value with hierarchical resolution and caching.

        Args:
            key: Setting key to retrieve
            default: Default value if setting is not found

        Returns:
            The setting value from the highest priority source
        """
        # Create cache key
        cache_key = f"{self.schema_name}:{key}" if self.schema_name else f"global:{key}"

        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try schema-specific settings first
        schema_value = self._get_schema_setting(key)
        if schema_value is not None:
            self._cache[cache_key] = schema_value
            return schema_value

        # Try Django global settings
        django_value = self._get_django_setting(key)
        if django_value is not None:
            self._cache[cache_key] = django_value
            return django_value

        # Try library defaults
        library_value = self._get_library_default(key)
        if library_value is not None:
            self._cache[cache_key] = library_value
            return library_value

        # Return provided default if nothing found
        self._cache[cache_key] = default
        return default

    def _get_schema_setting(self, key: str) -> Any:
        """
        Get setting from schema-specific configuration.

        Args:
            key: Setting key to retrieve

        Returns:
            The setting value or None if not found
        """
        if not self.schema_name:
            return None

        schema_settings = getattr(settings, "RAIL_DJANGO_GRAPHQL_SCHEMAS", {})
        if self.schema_name not in schema_settings:
            return None

        schema_config = schema_settings[self.schema_name]
        return self._get_nested_value(schema_config, key)

    def _get_django_setting(self, key: str) -> Any:
        """
        Get setting from global Django RAIL_DJANGO_GRAPHQL settings.

        Args:
            key: Setting key to retrieve

        Returns:
            The setting value or None if not found
        """
        django_settings = getattr(settings, "RAIL_DJANGO_GRAPHQL", {})
        return self._get_nested_value(django_settings, key)

    def _get_library_default(self, key: str) -> Any:
        """
        Get setting from library defaults.

        Args:
            key: Setting key to retrieve

        Returns:
            The setting value or None if not found
        """
        return self._get_nested_value(LIBRARY_DEFAULTS, key)

    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Any:
        """
        Get nested value from dictionary using dot notation.

        Args:
            data: Dictionary to search in
            key: Key to retrieve (supports dot notation for nested access)

        Returns:
            The value or None if not found
        """
        if not isinstance(data, dict):
            return None

        keys = key.split(".")
        current = data

        for k in keys:
            if not isinstance(current, dict) or k not in current:
                return None
            current = current[k]

        return current

    def set(self, key: str, value: Any) -> None:
        """
        Set a setting value (runtime only, not persistent).

        Args:
            key: Setting key to set
            value: Value to set
        """
        # Clear cache for this key
        cache_key = f"{self.schema_name}:{key}" if self.schema_name else f"global:{key}"
        if cache_key in self._cache:
            del self._cache[cache_key]

        # Set in Django settings (runtime only)
        if not hasattr(settings, "RAIL_DJANGO_GRAPHQL"):
            settings.RAIL_DJANGO_GRAPHQL = {}

        self._set_nested_value(settings.RAIL_DJANGO_GRAPHQL, key, value)

    def _set_nested_value(self, data: Dict[str, Any], key: str, value: Any) -> None:
        """
        Set nested value in dictionary using dot notation.

        Args:
            data: Dictionary to set value in
            key: Key to set (supports dot notation for nested access)
            value: Value to set
        """
        keys = key.split(".")
        current = data

        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        # Set the final value
        current[keys[-1]] = value

    def clear_cache(self) -> None:
        """Clear the settings cache."""
        self._cache.clear()

    def validate(self) -> Dict[str, Any]:
        """
        Validate current settings configuration.

        Returns:
            Dictionary with validation results
        """
        validation_results = {"valid": True, "errors": [], "warnings": []}

        # Validate schema-specific settings if schema_name is provided
        if self.schema_name:
            schema_settings = getattr(settings, "RAIL_DJANGO_GRAPHQL_SCHEMAS", {})
            if self.schema_name not in schema_settings:
                validation_results["warnings"].append(
                    f"Schema '{self.schema_name}' not found in RAIL_DJANGO_GRAPHQL_SCHEMAS"
                )

        # Validate critical settings
        critical_settings = [
            "disable_security_mutations",
            "max_query_depth",
            "max_query_complexity",
        ]
        for setting in critical_settings:
            value = self.get(setting)
            if value is None:
                validation_results["errors"].append(
                    f"Critical setting '{setting}' is None"
                )
                validation_results["valid"] = False

        return validation_results


# Global settings proxy instance (no schema-specific settings)
settings_proxy = SettingsProxy()


def get_settings_proxy(schema_name: Optional[str] = None) -> SettingsProxy:
    """
    Get a settings proxy instance for the specified schema.

    Args:
        schema_name: Name of the schema for schema-specific settings

    Returns:
        SettingsProxy instance
    """
    return SettingsProxy(schema_name)


def get_setting(
    key: str, default: Any = None, schema_name: Optional[str] = None
) -> Any:
    """
    Get a setting value using the hierarchical settings system.

    Args:
        key: Setting key to retrieve
        default: Default value if setting is not found
        schema_name: Name of the schema for schema-specific settings

    Returns:
        The setting value from the highest priority source
    """
    proxy = get_settings_proxy(schema_name)
    return proxy.get(key, default)


def configure_schema_settings(schema_name: str, **overrides: Any) -> None:
    """
    Configure schema-specific settings overrides.

    Args:
        schema_name: Name of the schema to configure
        **overrides: Setting key-value pairs to override for this schema
    """
    from django.conf import settings

    # Ensure RAIL_DJANGO_GRAPHQL_SCHEMAS exists
    if not hasattr(settings, "RAIL_DJANGO_GRAPHQL_SCHEMAS"):
        settings.RAIL_DJANGO_GRAPHQL_SCHEMAS = {}

    # Initialize schema settings if not exists
    if schema_name not in settings.RAIL_DJANGO_GRAPHQL_SCHEMAS:
        settings.RAIL_DJANGO_GRAPHQL_SCHEMAS[schema_name] = {}

    # Apply overrides
    settings.RAIL_DJANGO_GRAPHQL_SCHEMAS[schema_name].update(overrides)


def get_settings_for_schema(schema_name: str) -> SettingsProxy:
    """
    Get a settings proxy instance for the specified schema.

    Args:
        schema_name: Name of the schema to get settings for

    Returns:
        SettingsProxy instance configured for the schema
    """
    return get_settings_proxy(schema_name)


def get_schema_settings(schema_name: str) -> SettingsProxy:
    """
    Get settings for a specific schema.

    Args:
        schema_name: Name of the schema to get settings for

    Returns:
        SettingsProxy instance configured for the schema
    """
    return get_settings_for_schema(schema_name)


def get_mutation_generator_settings(schema_name: str) -> "MutationGeneratorSettings":
    """
    Get mutation generator settings for a specific schema using hierarchical loading.

    Args:
        schema_name: Name of the schema to get mutation settings for

    Returns:
        MutationGeneratorSettings instance
    """
    from .core.settings import MutationGeneratorSettings

    return MutationGeneratorSettings.from_schema(schema_name)


def get_type_generator_settings(schema_name: Optional[str] = None):
    """
    Get type generator settings for the specified schema using hierarchical loading.

    Args:
        schema_name: Name of the schema for schema-specific settings

    Returns:
        TypeGeneratorSettings instance
    """
    from .core.settings import TypeGeneratorSettings

    if schema_name is None:
        schema_name = "default"

    return TypeGeneratorSettings.from_schema(schema_name)


def get_query_generator_settings(schema_name: Optional[str] = None):
    """
    Get query generator settings for the specified schema using hierarchical loading.

    Args:
        schema_name: Name of the schema for schema-specific settings

    Returns:
        QueryGeneratorSettings instance
    """
    from .core.settings import QueryGeneratorSettings

    if schema_name is None:
        schema_name = "default"

    return QueryGeneratorSettings.from_schema(schema_name)


def get_core_schema_settings(schema_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get core schema settings for the specified schema using hierarchical loading.

    Args:
        schema_name: Name of the schema for schema-specific settings

    Returns:
        Dictionary containing core schema settings
    """
    from .core.settings import SchemaSettings

    if schema_name is None:
        schema_name = "default"

    schema_settings = SchemaSettings.from_schema(schema_name)

    # Convert dataclass to dictionary
    return {
        field.name: getattr(schema_settings, field.name)
        for field in schema_settings.__dataclass_fields__.values()
    }

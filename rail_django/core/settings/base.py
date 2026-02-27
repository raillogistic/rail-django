"""
Internal utility functions for settings loading.
"""

from typing import Any
from django.conf import settings as django_settings


def _merge_settings_dicts(*dicts: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge settings dictionaries with later values taking precedence."""
    result: dict[str, Any] = {}
    for data in dicts:
        if not data:
            continue
        for key, value in data.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = _merge_settings_dicts(result[key], value)
            else:
                result[key] = value
    return result


def _get_schema_registry_settings(schema_name: str) -> dict[str, Any]:
    """Get settings from schema registry for a specific schema."""
    try:
        from ..registry import schema_registry
        schema_info = schema_registry.get_schema(schema_name)
        if not schema_info: return {}
        return schema_info.settings
    except (ImportError, AttributeError): return {}


def _get_global_settings(schema_name: str) -> dict[str, Any]:
    """Get global settings from Django settings for a specific schema."""
    rail_settings = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {})
    if schema_name in rail_settings: return rail_settings.get(schema_name, {})
    known_section_keys = {"schema_settings", "query_settings", "mutation_settings", "subscription_settings", "persisted_query_settings", "filtering_settings", "task_settings", "security_settings", "performance_settings", "middleware_settings", "plugin_settings", "webhook_settings", "multitenancy_settings", "schema_registry"}
    if any(k in rail_settings for k in known_section_keys): return rail_settings
    return {}


def _get_library_defaults() -> dict[str, Any]:
    """Get library default settings."""
    try:
        from rail_django.config.defaults import LIBRARY_DEFAULTS, get_environment_defaults, merge_settings
        env = getattr(django_settings, "ENVIRONMENT", None)
        if not env: env = "production" if not getattr(django_settings, "DEBUG", False) else "development"
        return merge_settings(LIBRARY_DEFAULTS, get_environment_defaults(env))
    except ImportError: return {}

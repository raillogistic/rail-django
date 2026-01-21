"""
Internal utility functions for settings loading.
"""

from typing import Any, Dict, Optional
from django.conf import settings as django_settings


def _merge_settings_dicts(*dicts: dict[str, Any]) -> dict[str, Any]:
    """Merge multiple settings dictionaries with later ones taking precedence."""
    result = {}
    for d in dicts:
        if d: result.update(d)
    return result


def _normalize_legacy_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Map legacy section names to current settings keys."""
    if not isinstance(config, dict): return config
    normalized = dict(config)
    if "TYPE_SETTINGS" in config and "type_generation_settings" not in config: normalized["type_generation_settings"] = config["TYPE_SETTINGS"]
    if "FILTERING" in config and "filtering_settings" not in config: normalized["filtering_settings"] = config["FILTERING"]
    if "PERFORMANCE" in config and "performance_settings" not in config: normalized["performance_settings"] = config["PERFORMANCE"]
    if "SECURITY" in config and "security_settings" not in config: normalized["security_settings"] = config["SECURITY"]
    return normalized


def _get_schema_registry_settings(schema_name: str) -> dict[str, Any]:
    """Get settings from schema registry for a specific schema."""
    try:
        from ..registry import schema_registry
        schema_info = schema_registry.get_schema(schema_name)
        if not schema_info: return {}
        return _normalize_legacy_settings(schema_info.settings)
    except (ImportError, AttributeError): return {}


def _get_global_settings(schema_name: str) -> dict[str, Any]:
    """Get global settings from Django settings for a specific schema."""
    rail_settings = _normalize_legacy_settings(getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {}))
    if schema_name in rail_settings: return _normalize_legacy_settings(rail_settings.get(schema_name, {}))
    known_section_keys = {"schema_settings", "query_settings", "mutation_settings", "subscription_settings", "persisted_query_settings", "filtering_settings", "TYPE_SETTINGS", "FILTERING", "PAGINATION", "SECURITY", "PERFORMANCE", "CUSTOM_SCALARS", "FIELD_CONVERTERS", "SCHEMA_HOOKS", "MIDDLEWARE", "NESTED_OPERATIONS", "RELATIONSHIP_HANDLING", "DEVELOPMENT", "I18N", "plugin_settings", "webhook_settings", "multitenancy_settings"}
    if any(k in rail_settings for k in known_section_keys): return rail_settings
    return {}


def _get_library_defaults() -> dict[str, Any]:
    """Get library default settings."""
    try:
        from ...defaults import LIBRARY_DEFAULTS, get_environment_defaults, merge_settings
        env = getattr(django_settings, "ENVIRONMENT", None)
        if not env: env = "production" if not getattr(django_settings, "DEBUG", False) else "development"
        return merge_settings(LIBRARY_DEFAULTS, get_environment_defaults(env))
    except ImportError: return {}

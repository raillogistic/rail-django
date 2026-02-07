"""
Builder and instance management for SchemaRegistry.
"""

import logging
from typing import Optional

from .registry import SchemaRegistry

logger = logging.getLogger(__name__)


def get_schema_builder(registry: SchemaRegistry, name: str):
    """Get or create a schema builder for the given schema."""
    if name not in registry._schema_builders:
        schema_info = registry.get_schema(name)
        if not schema_info:
            raise ValueError(f"Schema '{name}' not found")
        if not schema_info.enabled:
            raise ValueError(f"Schema '{name}' is disabled")

        try:
            from ...config_proxy import configure_schema_settings, get_core_schema_settings
            from ..schema import SchemaBuilder
            from ..settings import SchemaSettings

            if schema_info.settings:
                overrides = {}
                schema_settings_overrides = {}
                direct_schema_overrides = {}
                valid_schema_fields = {field.name for field in SchemaSettings.__dataclass_fields__.values()}

                for key, value in schema_info.settings.items():
                    if key == "schema_settings" and isinstance(value, dict):
                        schema_settings_overrides.update(value)
                        continue
                    key_name = str(key)
                    upper_key = key_name.upper()
                    if upper_key == "ENABLE_GRAPHIQL":
                        direct_schema_overrides["enable_graphiql"] = value
                        continue
                    if upper_key == "ENABLE_INTROSPECTION":
                        direct_schema_overrides["enable_introspection"] = value
                        continue
                    if upper_key == "AUTHENTICATION_REQUIRED":
                        direct_schema_overrides["authentication_required"] = value
                        continue
                    if key_name in valid_schema_fields:
                        direct_schema_overrides[key_name] = value

                if direct_schema_overrides:
                    schema_settings_overrides.update(direct_schema_overrides)
                if schema_settings_overrides:
                    overrides["schema_settings"] = schema_settings_overrides
                if overrides:
                    configure_schema_settings(name, **overrides)

            schema_settings_dict = get_core_schema_settings(name) or {}
            valid_fields = SchemaSettings.__dataclass_fields__.keys()
            schema_settings = SchemaSettings(
                **{key: value for key, value in schema_settings_dict.items() if key in valid_fields}
            )
            raw_settings = {"schema_settings": schema_settings_dict}
            builder = SchemaBuilder(
                settings=schema_settings,
                schema_name=name,
                raw_settings=raw_settings,
                registry=registry,
            )
            registry._schema_builders[name] = builder
            schema_info.builder = builder
        except ImportError as e:
            logger.error(f"Could not import SchemaBuilder: {e}")
            raise
    return registry._schema_builders[name]


def get_schema_instance(registry: SchemaRegistry, name: str):
    """Get a cached schema instance for a schema name."""
    builder = get_schema_builder(registry, name)
    current_version = getattr(builder, "get_schema_version", lambda: 0)()
    cached = registry._schema_instance_cache.get(name)
    if cached and cached.get("version") == current_version:
        return cached.get("schema")
    schema_instance = builder.get_schema()
    with registry._lock:
        registry._schema_instance_cache[name] = {
            "version": current_version,
            "schema": schema_instance,
        }
    return schema_instance

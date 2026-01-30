"""
SchemaSettings implementation.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from .base import (
    _get_library_defaults,
    _get_global_settings,
    _get_schema_registry_settings,
    _merge_settings_dicts,
)


@dataclass
class SchemaSettings:
    """Settings for controlling overall schema behavior."""

    excluded_apps: List[str] = field(default_factory=list)
    excluded_models: List[str] = field(default_factory=list)
    enable_introspection: bool = True
    enable_graphiql: bool = True
    graphiql_superuser_only: bool = False
    graphiql_allowed_hosts: List[str] = field(default_factory=list)
    auto_refresh_on_model_change: bool = False
    auto_refresh_on_migration: bool = True
    prebuild_on_startup: bool = False
    authentication_required: bool = False
    enable_pagination: bool = True
    auto_camelcase: bool = True
    disable_security_mutations: bool = False
    enable_extension_mutations: bool = True
    show_metadata: bool = True
    query_extensions: List[str] = field(default_factory=list)
    mutation_extensions: List[str] = field(default_factory=list)
    query_field_allowlist: Optional[List[str]] = None
    mutation_field_allowlist: Optional[List[str]] = None
    subscription_field_allowlist: Optional[List[str]] = None

    @classmethod
    def from_schema(cls, schema_name: str) -> "SchemaSettings":
        defaults = _get_library_defaults().get("schema_settings", {})
        global_settings = _get_global_settings(schema_name).get("schema_settings", {})
        schema_registry_settings = _get_schema_registry_settings(schema_name)
        schema_settings = schema_registry_settings.get("schema_settings", {})
        direct_settings = {
            k: v
            for k, v in schema_registry_settings.items()
            if k in cls.__dataclass_fields__
        }
        merged = _merge_settings_dicts(
            defaults, global_settings, schema_settings, direct_settings
        )
        valid_fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in merged.items() if k in valid_fields})

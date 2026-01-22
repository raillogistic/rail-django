"""
SubscriptionGeneratorSettings implementation.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from .base import _get_library_defaults, _get_global_settings, _get_schema_registry_settings, _merge_settings_dicts


@dataclass
class SubscriptionGeneratorSettings:
    """Settings for controlling GraphQL subscription generation."""
    enable_subscriptions: bool = True
    enable_create: bool = True
    enable_update: bool = True
    enable_delete: bool = True
    enable_filters: bool = True
    discover_models: bool = False
    include_models: List[str] = field(default_factory=list)
    exclude_models: List[str] = field(default_factory=list)

    @classmethod
    def from_schema(cls, schema_name: str) -> "SubscriptionGeneratorSettings":
        defaults = _get_library_defaults().get("subscription_settings", {})
        global_settings = _get_global_settings(schema_name).get("subscription_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get("subscription_settings", {})
        merged = _merge_settings_dicts(defaults, global_settings, schema_settings)
        valid_fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in merged.items() if k in valid_fields})

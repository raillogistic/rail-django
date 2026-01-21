"""
QueryGeneratorSettings implementation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .base import _get_library_defaults, _get_global_settings, _get_schema_registry_settings, _merge_settings_dicts


@dataclass
class QueryGeneratorSettings:
    """Settings for controlling GraphQL query generation."""
    generate_filters: bool = True
    generate_ordering: bool = True
    generate_pagination: bool = True
    enable_pagination: bool = True
    enable_ordering: bool = True
    use_relay: bool = False
    default_page_size: int = 20
    max_page_size: int = 100
    max_grouping_buckets: int = 200
    max_property_ordering_results: int = 2000
    property_ordering_warn_on_cap: bool = True
    additional_lookup_fields: Dict[str, List[str]] = field(default_factory=dict)
    require_model_permissions: bool = True
    model_permission_codename: str = "view"

    @classmethod
    def from_schema(cls, schema_name: str) -> "QueryGeneratorSettings":
        defaults = _get_library_defaults().get("query_settings", {})
        global_settings = _get_global_settings(schema_name).get("query_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get("query_settings", {})
        merged = _merge_settings_dicts(defaults, global_settings, schema_settings)
        valid_fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in merged.items() if k in valid_fields})

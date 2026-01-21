"""
FilteringSettings implementation.
"""

from dataclasses import dataclass
from typing import Optional
from .base import _get_library_defaults, _get_global_settings, _get_schema_registry_settings, _merge_settings_dicts


@dataclass
class FilteringSettings:
    """Settings for advanced filtering features."""
    enable_full_text_search: bool = False
    fts_config: str = "english"
    fts_search_type: str = "websearch"
    fts_rank_threshold: Optional[float] = None
    enable_window_filters: bool = True
    enable_subquery_filters: bool = True
    enable_conditional_aggregation: bool = True
    enable_array_filters: bool = True
    enable_field_comparison: bool = True
    enable_distinct_count: bool = True
    enable_date_trunc_filters: bool = True
    enable_extract_date_filters: bool = True
    max_filter_depth: int = 10
    max_filter_clauses: int = 50
    max_regex_length: int = 500
    reject_unsafe_regex: bool = True

    @classmethod
    def from_schema(cls, schema_name: str) -> "FilteringSettings":
        defaults = _get_library_defaults().get("filtering_settings", {})
        global_settings = _get_global_settings(schema_name).get("filtering_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get("filtering_settings", {})
        merged = _merge_settings_dicts(defaults, global_settings, schema_settings)
        valid_fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in merged.items() if k in valid_fields})

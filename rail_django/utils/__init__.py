"""
Utility modules for Rail Django GraphQL.

This package contains utility functions and helpers used throughout
the Rail Django GraphQL library.
"""

from .coercion import (
    coerce_int,
    coerce_bool,
    coerce_str,
    coerce_float,
    coerce_list,
    coerce_optional,
)
from .datetime_utils import (
    parse_iso_datetime,
    format_iso_datetime,
    parse_date,
    coerce_date,
    now_utc,
    format_date,
)
from .sanitization import (
    sanitize_filename,
    sanitize_filename_basic,
    sanitize_query,
    sanitize_variables,
    sanitize_html,
    escape_css,
    sanitize_log_value,
)
from .cache import (
    make_cache_key,
    make_hashed_cache_key,
    get_cache_timeout,
    get_user_cache_key,
    cache_result,
    invalidate_cache_pattern,
    invalidate_cache_keys,
    get_or_set,
)
from .normalization import (
    normalize_list,
    normalize_string_list,
    normalize_accessor,
    normalize_header_key,
    normalize_legacy_config,
    normalize_model_label,
    normalize_dict_keys,
    normalize_filter_value,
    normalize_ordering,
)
from .graphql_meta import (
    get_model_graphql_meta,
    get_custom_filters,
    get_quick_filter_fields,
    get_filter_fields,
)

__all__ = [
    # Coercion
    "coerce_int",
    "coerce_bool",
    "coerce_str",
    "coerce_float",
    "coerce_list",
    "coerce_optional",
    # Datetime
    "parse_iso_datetime",
    "format_iso_datetime",
    "parse_date",
    "coerce_date",
    "now_utc",
    "format_date",
    # Sanitization
    "sanitize_filename",
    "sanitize_filename_basic",
    "sanitize_query",
    "sanitize_variables",
    "sanitize_html",
    "escape_css",
    "sanitize_log_value",
    # Cache
    "make_cache_key",
    "make_hashed_cache_key",
    "get_cache_timeout",
    "get_user_cache_key",
    "cache_result",
    "invalidate_cache_pattern",
    "invalidate_cache_keys",
    "get_or_set",
    # Normalization
    "normalize_list",
    "normalize_string_list",
    "normalize_accessor",
    "normalize_header_key",
    "normalize_legacy_config",
    "normalize_model_label",
    "normalize_dict_keys",
    "normalize_filter_value",
    "normalize_ordering",
    # GraphQL Meta
    "get_model_graphql_meta",
    "get_custom_filters",
    "get_quick_filter_fields",
    "get_filter_fields",
]

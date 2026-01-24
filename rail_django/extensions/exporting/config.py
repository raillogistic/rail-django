"""Export Configuration and Settings

This module contains export settings, configuration helpers, and model access utilities
used throughout the exporting package.
"""

import re
from typing import Any, Iterable, Optional

from django.conf import settings

from ...utils.sanitization import sanitize_filename_basic

# Default list of sensitive field names that should never be exported
DEFAULT_SENSITIVE_FIELDS = [
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "private_key",
    "ssh_key",
    "session",
    "ssn",
    "social_security",
    "social_security_number",
    "credit_card",
    "card_number",
    "cvv",
    "cvc",
    "pin",
    "otp",
    "mfa_secret",
]

# Default allowed filter lookups for export queries
DEFAULT_ALLOWED_FILTER_LOOKUPS = [
    "exact",
    "iexact",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "in",
    "range",
    "isnull",
    "gt",
    "gte",
    "lt",
    "lte",
    "regex",
    "iregex",
]

# Default allowed filter transforms for export queries
DEFAULT_ALLOWED_FILTER_TRANSFORMS = [
    "date",
    "year",
    "month",
    "day",
    "week",
    "week_day",
    "quarter",
    "time",
    "hour",
    "minute",
    "second",
]

# Characters that indicate a formula in spreadsheet applications
FORMULA_PREFIXES = ("=", "+", "-", "@")

# Default export configuration values
EXPORT_DEFAULTS = {
    "max_rows": 5000,
    "stream_csv": True,
    "csv_chunk_size": 1000,
    "enforce_streaming_csv": True,
    "excel_write_only": False,  # Use full mode for professional styling
    "excel_auto_width": True,
    "excel_auto_width_max_columns": 50,
    "excel_auto_width_max_rows": 2000,
    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30,
        "trusted_proxies": [],
    },
    "allowed_models": [],
    "allowed_fields": {},  # legacy alias for export_fields
    "export_fields": {},
    "export_exclude": {},
    "sensitive_fields": DEFAULT_SENSITIVE_FIELDS,
    "require_export_fields": False,
    "require_model_permissions": True,
    "require_field_permissions": False,
    "required_permissions": [],
    "allow_callables": False,
    "allow_dunder_access": False,
    "filterable_fields": {},
    "orderable_fields": {},
    "filterable_special_fields": [],
    "allowed_filter_lookups": DEFAULT_ALLOWED_FILTER_LOOKUPS,
    "allowed_filter_transforms": DEFAULT_ALLOWED_FILTER_TRANSFORMS,
    "max_filters": 50,
    "max_or_depth": 3,
    "max_prefetch_depth": 2,
    "sanitize_formulas": True,
    "formula_escape_strategy": "prefix",
    "formula_escape_prefix": "'",
    "field_formatters": {},
    "export_templates": {},
    "async_jobs": {
        "enable": True,
        "backend": "thread",
        "expires_seconds": 3600,
        "storage_dir": None,
        "track_progress": True,
        "progress_update_rows": 500,
    },
}


def get_export_settings() -> dict[str, Any]:
    """Return merged export settings with defaults applied.

    Checks for RAIL_DJANGO_EXPORT settings first, then falls back to
    RAIL_DJANGO_GRAPHQL['export_settings'] for backward compatibility.

    Returns:
        Dictionary of export settings with all defaults applied.
    """
    export_settings = getattr(settings, "RAIL_DJANGO_EXPORT", None)
    if export_settings is None:
        export_settings = (getattr(settings, "RAIL_DJANGO_GRAPHQL", {}) or {}).get(
            "export_settings", {}
        )

    merged = dict(EXPORT_DEFAULTS)
    if isinstance(export_settings, dict):
        merged.update(export_settings)
        rate_limit_override = export_settings.get("rate_limit")
        rate_limit = dict(EXPORT_DEFAULTS["rate_limit"])
        if isinstance(rate_limit_override, dict):
            rate_limit.update(rate_limit_override)
        merged["rate_limit"] = rate_limit
        async_override = export_settings.get("async_jobs")
        async_jobs = dict(EXPORT_DEFAULTS["async_jobs"])
        if isinstance(async_override, dict):
            async_jobs.update(async_override)
        merged["async_jobs"] = async_jobs

    return merged


def model_key_candidates(model: type) -> list[str]:
    """Return possible identifiers for a model.

    Args:
        model: Django model class.

    Returns:
        List of possible string identifiers for the model.
    """
    return [
        model._meta.label_lower,
        f"{model._meta.app_label}.{model.__name__}",
        model.__name__,
        model._meta.model_name,
    ]


def normalize_allowed_list(values: Iterable[Any]) -> list[str]:
    """Normalize allowlist values into lowercase strings.

    Args:
        values: Iterable of values to normalize.

    Returns:
        List of lowercase stripped strings.
    """
    return [str(value).strip().lower() for value in values if str(value).strip()]


def is_model_allowed(model: type, export_settings: dict[str, Any]) -> bool:
    """Check if the model is allowed for export.

    Args:
        model: Django model class.
        export_settings: Export configuration dictionary.

    Returns:
        True if the model is allowed for export, False otherwise.
    """
    allowed_models = export_settings.get("allowed_models") or []
    if not allowed_models:
        return True

    allowed = set(normalize_allowed_list(allowed_models))
    return any(key.lower() in allowed for key in model_key_candidates(model))


def get_allowed_fields(model: type, export_settings: dict[str, Any]) -> list[str]:
    """Return the allowed field accessors for a model, if configured.

    Args:
        model: Django model class.
        export_settings: Export configuration dictionary.

    Returns:
        List of allowed field accessor strings.
    """
    allowed_fields = export_settings.get("allowed_fields") or {}
    if not isinstance(allowed_fields, dict):
        return []

    candidates = {key.lower() for key in model_key_candidates(model)}
    for key, fields in allowed_fields.items():
        if not key:
            continue
        if str(key).strip().lower() in candidates:
            if isinstance(fields, (list, tuple, set)):
                return [str(field).strip() for field in fields if str(field).strip()]
            return []

    return []


def normalize_accessor_value(value: str) -> str:
    """Normalize accessor values to dot-notation lowercase.

    Args:
        value: Accessor string to normalize.

    Returns:
        Normalized accessor string.
    """
    return value.replace("__", ".").strip().lower()


def normalize_filter_value(value: str) -> str:
    """Normalize filter/order values to __ notation lowercase.

    Args:
        value: Filter value string to normalize.

    Returns:
        Normalized filter string.
    """
    return value.replace(".", "__").strip().lower()


def get_model_scoped_list(model: type, config_value: Any) -> Optional[list[str]]:
    """Return a model-scoped list from a dict keyed by model identifiers.

    Args:
        model: Django model class.
        config_value: Configuration value (expected to be a dict).

    Returns:
        List of strings if found, empty list if model found but no values,
        None if model not found in config.
    """
    if not isinstance(config_value, dict):
        return None

    candidates = {key.lower() for key in model_key_candidates(model)}
    for key, values in config_value.items():
        if not key:
            continue
        if str(key).strip().lower() in candidates:
            if isinstance(values, (list, tuple, set)):
                return [str(value).strip() for value in values if str(value).strip()]
            return []

    return []


def get_model_scoped_dict(model: type, config_value: Any) -> Optional[dict[str, Any]]:
    """Return a model-scoped dict from a dict keyed by model identifiers.

    Args:
        model: Django model class.
        config_value: Configuration value (expected to be a dict of dicts).

    Returns:
        Dictionary if found for the model, None otherwise.
    """
    if not isinstance(config_value, dict):
        return None

    candidates = {key.lower() for key in model_key_candidates(model)}
    for key, values in config_value.items():
        if not key:
            continue
        if str(key).strip().lower() in candidates and isinstance(values, dict):
            return values

    return None


def get_export_fields(model: type, export_settings: dict[str, Any]) -> list[str]:
    """Return explicit export field allowlist (full-path).

    Args:
        model: Django model class.
        export_settings: Export configuration dictionary.

    Returns:
        List of normalized field accessor strings.
    """
    export_fields = export_settings.get("export_fields")
    if export_fields is None:
        export_fields = export_settings.get("allowed_fields")
    scoped = get_model_scoped_list(model, export_fields)
    if scoped is None:
        return []
    return [normalize_accessor_value(value) for value in scoped]


def get_export_exclude(model: type, export_settings: dict[str, Any]) -> list[str]:
    """Return explicit export field denylist (full-path).

    Args:
        model: Django model class.
        export_settings: Export configuration dictionary.

    Returns:
        List of normalized field accessor strings to exclude.
    """
    scoped = get_model_scoped_list(model, export_settings.get("export_exclude"))
    if scoped is None:
        return []
    return [normalize_accessor_value(value) for value in scoped]


def get_filterable_fields(
    model: type, export_settings: dict[str, Any], export_fields: list[str]
) -> list[str]:
    """Return filterable fields (full-path) in __ notation.

    Args:
        model: Django model class.
        export_settings: Export configuration dictionary.
        export_fields: Default fields to use if filterable_fields not configured.

    Returns:
        List of filterable field strings in __ notation.
    """
    scoped = get_model_scoped_list(model, export_settings.get("filterable_fields"))
    if scoped is None or not scoped:
        scoped = export_fields
    return [normalize_filter_value(value) for value in scoped]


def get_orderable_fields(
    model: type, export_settings: dict[str, Any], export_fields: list[str]
) -> list[str]:
    """Return orderable fields (full-path) in __ notation.

    Args:
        model: Django model class.
        export_settings: Export configuration dictionary.
        export_fields: Default fields to use if orderable_fields not configured.

    Returns:
        List of orderable field strings in __ notation.
    """
    scoped = get_model_scoped_list(model, export_settings.get("orderable_fields"))
    if scoped is None or not scoped:
        scoped = export_fields
    return [normalize_filter_value(value) for value in scoped]


def get_field_formatters(
    model: type, export_settings: dict[str, Any]
) -> dict[str, Any]:
    """Return field formatter mappings for a model.

    Args:
        model: Django model class.
        export_settings: Export configuration dictionary.

    Returns:
        Dictionary mapping normalized accessors to formatter configurations.
    """
    formatters = export_settings.get("field_formatters") or {}
    scoped = get_model_scoped_dict(model, formatters)
    if scoped is not None:
        return {
            normalize_accessor_value(key): value
            for key, value in scoped.items()
            if isinstance(key, str)
        }
    if isinstance(formatters, dict):
        return {
            normalize_accessor_value(key): value
            for key, value in formatters.items()
            if isinstance(key, str)
        }
    return {}


def get_export_templates(export_settings: dict[str, Any]) -> dict[str, Any]:
    """Return configured export templates.

    Args:
        export_settings: Export configuration dictionary.

    Returns:
        Dictionary of export template configurations.
    """
    templates = export_settings.get("export_templates") or {}
    if not isinstance(templates, dict):
        return {}
    return templates


def sanitize_filename(filename: str) -> str:
    """Sanitize filenames for safe Content-Disposition and filesystem usage.

    Removes any characters that are not alphanumeric, period, underscore,
    or hyphen. Also strips leading/trailing periods and underscores.

    Args:
        filename: The filename to sanitize.

    Returns:
        Sanitized filename, or 'export' if result would be empty.
    """
    return sanitize_filename_basic(filename, default="export")

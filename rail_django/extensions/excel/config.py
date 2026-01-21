"""
Excel export configuration, constants, and settings helpers.

This module provides default styling configurations, type aliases, and
settings helpers for the Excel export functionality.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union

from django.conf import settings
from django.db import models

# Type aliases for data formats
ExcelRowData = List[Any]
ExcelSheetData = List[ExcelRowData]
ExcelMultiSheetData = Dict[str, ExcelSheetData]
ExcelData = Union[ExcelSheetData, ExcelMultiSheetData]

# Rate limiting defaults
EXCEL_RATE_LIMIT_DEFAULTS: Dict[str, Any] = {
    "enable": True,
    "window_seconds": 60,
    "max_requests": 30,
    "trusted_proxies": [],
}

# Caching defaults
EXCEL_CACHE_DEFAULTS: Dict[str, Any] = {
    "enable": False,
    "timeout_seconds": 300,
    "vary_on_user": True,
    "key_prefix": "rail:excel_cache",
}

# Async job defaults
EXCEL_ASYNC_DEFAULTS: Dict[str, Any] = {
    "enable": False,
    "backend": "thread",
    "expires_seconds": 3600,
    "storage_dir": None,
    "queue": "default",
    "track_progress": False,
    "webhook_url": None,
    "webhook_headers": {},
    "webhook_timeout_seconds": 10,
}

# Catalog endpoint defaults
EXCEL_CATALOG_DEFAULTS: Dict[str, Any] = {
    "enable": True,
    "require_authentication": True,
    "filter_by_access": True,
    "include_config": False,
    "include_permissions": True,
}

# Default header cell style
DEFAULT_HEADER_STYLE: Dict[str, Any] = {
    "bold": True,
    "fill_color": "4472C4",
    "font_color": "FFFFFF",
    "font_size": 11,
    "alignment": "center",
}

# Default data cell style
DEFAULT_CELL_STYLE: Dict[str, Any] = {
    "font_size": 11,
    "alignment": "left",
    "wrap_text": False,
}

# Default alternating row style
DEFAULT_ALTERNATING_ROW_STYLE: Dict[str, Any] = {
    "enable": True,
    "even_fill_color": "F2F2F2",
    "odd_fill_color": "FFFFFF",
}

# Default border style
DEFAULT_BORDER_STYLE: Dict[str, Any] = {
    "enable": True,
    "color": "D4D4D4",
    "style": "thin",
}


def _merge_dict(defaults: Dict[str, Any], overrides: Any) -> Dict[str, Any]:
    """
    Shallow-merge dict settings with safe fallbacks.

    Args:
        defaults: The default dictionary values.
        overrides: Values to override defaults with.

    Returns:
        Merged dictionary.
    """
    merged = dict(defaults)
    if isinstance(overrides, dict):
        merged.update(overrides)
    return merged


def _excel_export_settings() -> Dict[str, Any]:
    """
    Safely read the Excel export defaults from settings.

    Returns:
        A dictionary with style defaults and configuration.
    """
    return getattr(settings, "RAIL_DJANGO_GRAPHQL_EXCEL_EXPORT", {})


def _excel_dict(key: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a specific Excel configuration section with defaults.

    Args:
        key: The configuration key to retrieve.
        defaults: Default values to use.

    Returns:
        Merged configuration dictionary.
    """
    return _merge_dict(defaults, _excel_export_settings().get(key))


def _excel_rate_limit() -> Dict[str, Any]:
    """Get rate limiting configuration."""
    return _excel_dict("rate_limit", EXCEL_RATE_LIMIT_DEFAULTS)


def _excel_cache() -> Dict[str, Any]:
    """Get cache configuration."""
    return _excel_dict("cache", EXCEL_CACHE_DEFAULTS)


def _excel_async() -> Dict[str, Any]:
    """Get async job configuration."""
    return _excel_dict("async_jobs", EXCEL_ASYNC_DEFAULTS)


def _excel_catalog() -> Dict[str, Any]:
    """Get catalog endpoint configuration."""
    return _excel_dict("catalog", EXCEL_CATALOG_DEFAULTS)


def _excel_expose_errors() -> bool:
    """Check if errors should be exposed in responses."""
    return bool(_excel_export_settings().get("expose_errors", settings.DEBUG))


def _url_prefix() -> str:
    """Return URL prefix under /api/ where Excel templates are exposed."""
    return _excel_export_settings().get("url_prefix", "excel")


def _default_excel_config() -> Dict[str, Any]:
    """
    Provide default styling that can be overridden per template.

    Returns:
        Dict of Excel configuration values.
    """
    defaults = {
        "sheet_name": "Sheet1",
        "freeze_panes": True,
        "column_widths": "auto",
        "header_style": DEFAULT_HEADER_STYLE.copy(),
        "cell_style": DEFAULT_CELL_STYLE.copy(),
        "alternating_rows": DEFAULT_ALTERNATING_ROW_STYLE.copy(),
        "borders": DEFAULT_BORDER_STYLE.copy(),
        "number_formats": {},
        "date_format": "YYYY-MM-DD",
        "datetime_format": "YYYY-MM-DD HH:MM:SS",
        "decimal_format": "#,##0.00",
        "auto_filter": True,
    }
    settings_overrides = _excel_export_settings().get("default_config", {})
    return {**defaults, **settings_overrides}


@dataclass
class ExcelTemplateMeta:
    """Raw decorator metadata attached to a model method."""

    url_path: Optional[str]
    config: Dict[str, Any] = field(default_factory=dict)
    roles: Sequence[str] = field(default_factory=tuple)
    permissions: Sequence[str] = field(default_factory=tuple)
    guard: Optional[str] = None
    require_authentication: bool = True
    title: Optional[str] = None
    allow_client_data: bool = False
    client_data_fields: Sequence[str] = field(default_factory=tuple)


@dataclass
class ExcelTemplateDefinition:
    """Runtime representation of a registered Excel template."""

    model: Optional[Type[models.Model]]
    method_name: Optional[str]
    handler: Optional[Callable[..., Any]]
    source: str
    url_path: str
    config: Dict[str, Any]
    roles: Sequence[str]
    permissions: Sequence[str]
    guard: Optional[str]
    require_authentication: bool
    title: str
    allow_client_data: bool
    client_data_fields: Sequence[str]


@dataclass
class ExcelTemplateAccessDecision:
    """Represents whether a user can access an Excel template."""

    allowed: bool
    reason: Optional[str] = None
    status_code: int = 200


def _derive_excel_template_title(model: models.Model, method_name: str) -> str:
    """
    Compute a readable fallback title when none is provided.

    Args:
        model: Django model class owning the template.
        method_name: Name of the decorated method.

    Returns:
        Human-readable title.
    """
    base = method_name.replace("_", " ").strip() or "Export"
    base = base[:1].upper() + base[1:]
    verbose_name = getattr(getattr(model, "_meta", None), "verbose_name", None)
    if verbose_name:
        return f"{base} ({verbose_name})"
    return base


def _derive_function_title(func: Callable) -> str:
    """
    Compute a readable fallback title for function templates.

    Args:
        func: The function to derive a title from.

    Returns:
        Human-readable title.
    """
    base = getattr(func, "__name__", "").replace("_", " ").strip() or "Excel Export"
    return base[:1].upper() + base[1:]


__all__ = [
    # Type aliases
    "ExcelRowData",
    "ExcelSheetData",
    "ExcelMultiSheetData",
    "ExcelData",
    # Default constants
    "EXCEL_RATE_LIMIT_DEFAULTS",
    "EXCEL_CACHE_DEFAULTS",
    "EXCEL_ASYNC_DEFAULTS",
    "EXCEL_CATALOG_DEFAULTS",
    "DEFAULT_HEADER_STYLE",
    "DEFAULT_CELL_STYLE",
    "DEFAULT_ALTERNATING_ROW_STYLE",
    "DEFAULT_BORDER_STYLE",
    # Settings helpers
    "_merge_dict",
    "_excel_export_settings",
    "_excel_dict",
    "_excel_rate_limit",
    "_excel_cache",
    "_excel_async",
    "_excel_catalog",
    "_excel_expose_errors",
    "_url_prefix",
    "_default_excel_config",
    # Dataclasses
    "ExcelTemplateMeta",
    "ExcelTemplateDefinition",
    "ExcelTemplateAccessDecision",
    # Title helpers
    "_derive_excel_template_title",
    "_derive_function_title",
]

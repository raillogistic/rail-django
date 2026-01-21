"""Django Model Export Functionality

This package provides functionality to export Django model data to Excel, CSV,
or JSON files through HTTP endpoints. It supports dynamic model loading, field
selection, filtering, and ordering with GraphQL filter integration.

Features:
    - HTTP endpoint for generating downloadable files (JWT protected)
    - Support for Excel (.xlsx), CSV (.csv), and JSON formats
    - Dynamic model loading by app_name and model_name
    - Flexible field selection with nested field access and custom titles
    - Advanced filtering using GraphQL filter classes
    - Custom ordering support
    - Proper error handling and validation
    - Default-deny export schema with allowlists and sensitive field blocking
    - Formula injection sanitization for CSV/Excel
    - Filter/order allowlists with query guardrails
    - Optional async exports with job tracking and downloads
    - Optional export templates and field formatters

Field Format:
    - String format: "field_name" (uses field name as accessor and verbose_name as title)
    - Dict format: {"accessor": "field_name", "title": "Custom Title"}

Usage:
    POST /api/v1/export/
    Headers: Authorization: Bearer <jwt_token>
    {
        "app_name": "myapp",
        "model_name": "MyModel",
        "file_extension": "xlsx",
        "filename": "export_data",
        "fields": [
            "title",
            "author.username",
            {"accessor": "slug", "title": "MySlug"}
        ],
        "ordering": ["-created_at"],
        "variables": {
            "status": "active",
            "quick": "search term"
        }
    }
"""

from typing import Any, Optional, Union

# Import configuration
from .config import (
    DEFAULT_ALLOWED_FILTER_LOOKUPS,
    DEFAULT_ALLOWED_FILTER_TRANSFORMS,
    DEFAULT_SENSITIVE_FIELDS,
    EXPORT_DEFAULTS,
    FORMULA_PREFIXES,
    get_export_settings,
    get_export_templates,
    sanitize_filename,
)

# Import exceptions
from .exceptions import ExportError

# Import model exporter
from .exporter import ModelExporter, EXCEL_AVAILABLE

# Import job management
from .jobs import (
    cleanup_export_job_files,
    delete_export_job,
    export_job_task,
    get_export_job,
    get_export_storage_dir,
    run_export_job,
    set_export_job,
    update_export_job,
)

# Import security
from .security import (
    JWT_REQUIRED_AVAILABLE,
    check_rate_limit,
    check_template_access,
    enforce_model_permissions,
    job_access_allowed,
    log_export_event,
)

# Import URL helpers
from .urls import get_export_urls

# Import views
from .views import ExportJobDownloadView, ExportJobStatusView, ExportView


def export_model_to_csv(
    app_name: str,
    model_name: str,
    fields: list[Union[str, dict[str, str]]],
    variables: Optional[dict[str, Any]] = None,
    ordering: Optional[Union[str, list[str]]] = None,
    *,
    export_settings: Optional[dict[str, Any]] = None,
) -> str:
    """Programmatically export model data to CSV format.

    Args:
        app_name: Name of the Django app.
        model_name: Name of the model.
        fields: List of field definitions (string or dict format).
        variables: Filter variables.
        ordering: Ordering expression.
        export_settings: Optional export configuration override.

    Returns:
        CSV content as string.

    Example:
        >>> csv_content = export_model_to_csv(
        ...     "blog", "Post",
        ...     ["title", "author.username"],
        ...     variables={"where": {"status": "published"}},
        ...     ordering=["-created_at"],
        ... )
    """
    exporter = ModelExporter(app_name, model_name, export_settings=export_settings)
    return exporter.export_to_csv(fields, variables, ordering)


def export_model_to_excel(
    app_name: str,
    model_name: str,
    fields: list[Union[str, dict[str, str]]],
    variables: Optional[dict[str, Any]] = None,
    ordering: Optional[Union[str, list[str]]] = None,
    *,
    export_settings: Optional[dict[str, Any]] = None,
) -> bytes:
    """Programmatically export model data to Excel format.

    Args:
        app_name: Name of the Django app.
        model_name: Name of the model.
        fields: List of field definitions (string or dict format).
        variables: Filter variables.
        ordering: Ordering expression.
        export_settings: Optional export configuration override.

    Returns:
        Excel file content as bytes.

    Example:
        >>> excel_bytes = export_model_to_excel(
        ...     "blog", "Post",
        ...     ["title", "author.username"],
        ...     variables={"where": {"status": "published"}},
        ... )
        >>> with open("export.xlsx", "wb") as f:
        ...     f.write(excel_bytes)
    """
    exporter = ModelExporter(app_name, model_name, export_settings=export_settings)
    return exporter.export_to_excel(fields, variables, ordering)


def export_model_to_json(
    app_name: str,
    model_name: str,
    fields: list[Union[str, dict[str, str]]],
    variables: Optional[dict[str, Any]] = None,
    ordering: Optional[Union[str, list[str]]] = None,
    *,
    export_settings: Optional[dict[str, Any]] = None,
    indent: Optional[int] = 2,
) -> str:
    """Programmatically export model data to JSON format.

    Args:
        app_name: Name of the Django app.
        model_name: Name of the model.
        fields: List of field definitions (string or dict format).
        variables: Filter variables.
        ordering: Ordering expression.
        export_settings: Optional export configuration override.
        indent: JSON indentation level (None for compact).

    Returns:
        JSON content as string.

    Example:
        >>> json_content = export_model_to_json(
        ...     "blog", "Post",
        ...     ["title", "author.username"],
        ...     variables={"where": {"status": "published"}},
        ... )
    """
    exporter = ModelExporter(app_name, model_name, export_settings=export_settings)
    return exporter.export_to_json(fields, variables, ordering, indent=indent)


# Legacy aliases for backward compatibility
_get_export_settings = get_export_settings
_sanitize_filename = sanitize_filename
_get_export_job = get_export_job
_set_export_job = set_export_job
_update_export_job = update_export_job
_delete_export_job = delete_export_job
_run_export_job = run_export_job
_job_access_allowed = job_access_allowed
_get_export_storage_dir = get_export_storage_dir
_parse_iso_datetime = None  # Only used internally
_cleanup_export_job_files = cleanup_export_job_files
_export_job_cache_key = None  # Only used internally
_export_job_payload_key = None  # Only used internally


__all__ = [
    # Main classes
    "ModelExporter",
    "ExportError",
    "ExportView",
    "ExportJobStatusView",
    "ExportJobDownloadView",
    "EXCEL_AVAILABLE",
    # Utility functions
    "export_model_to_csv",
    "export_model_to_excel",
    "export_model_to_json",
    "get_export_urls",
    # Configuration
    "get_export_settings",
    "get_export_templates",
    "sanitize_filename",
    "EXPORT_DEFAULTS",
    "DEFAULT_SENSITIVE_FIELDS",
    "DEFAULT_ALLOWED_FILTER_LOOKUPS",
    "DEFAULT_ALLOWED_FILTER_TRANSFORMS",
    "FORMULA_PREFIXES",
    # Job management
    "get_export_job",
    "set_export_job",
    "update_export_job",
    "delete_export_job",
    "run_export_job",
    "export_job_task",
    "get_export_storage_dir",
    "cleanup_export_job_files",
    # Security
    "job_access_allowed",
    "check_rate_limit",
    "check_template_access",
    "enforce_model_permissions",
    "log_export_event",
    "JWT_REQUIRED_AVAILABLE",
]

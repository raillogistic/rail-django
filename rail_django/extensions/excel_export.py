"""
Excel export functionality for Rail Django.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.extensions.excel` package.

DEPRECATION NOTICE:
    Importing from `rail_django.extensions.excel_export` is deprecated.
    Please update your imports to use `rail_django.extensions.excel` instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.extensions.excel_export' is deprecated. "
    "Use 'rail_django.extensions.excel' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new package
from .excel import (
    # Views
    ExcelTemplateView,
    ExcelTemplateCatalogView,
    ExcelTemplateJobStatusView,
    ExcelTemplateJobDownloadView,
    # Decorators
    model_excel_template,
    excel_template,
    # Registry
    excel_template_registry,
    ExcelTemplateRegistry,
    ExcelTemplateDefinition,
    ExcelTemplateMeta,
    # Access control
    evaluate_excel_template_access,
    authorize_excel_template_access,
    ExcelTemplateAccessDecision,
    # Rendering
    render_excel,
    render_excel_sheet,
    # URL patterns
    excel_urlpatterns,
    # Async
    generate_excel_async,
    excel_job_task,
    # Constants
    OPENPYXL_AVAILABLE,
    OPENPYXL_STYLES_AVAILABLE,
    OPENPYXL_UTILS_AVAILABLE,
    OPENPYXL_CHARTS_AVAILABLE,
    # Type aliases
    ExcelRowData,
    ExcelSheetData,
    ExcelMultiSheetData,
    ExcelData,
    # Default style constants
    DEFAULT_HEADER_STYLE,
    DEFAULT_CELL_STYLE,
    DEFAULT_ALTERNATING_ROW_STYLE,
    DEFAULT_BORDER_STYLE,
    # Default config constants
    EXCEL_RATE_LIMIT_DEFAULTS,
    EXCEL_CACHE_DEFAULTS,
    EXCEL_ASYNC_DEFAULTS,
    EXCEL_CATALOG_DEFAULTS,
    # Chart utilities
    add_bar_chart,
    add_line_chart,
    add_pie_chart,
)

__all__ = [
    "ExcelTemplateView",
    "ExcelTemplateCatalogView",
    "ExcelTemplateJobStatusView",
    "ExcelTemplateJobDownloadView",
    "model_excel_template",
    "excel_template",
    "excel_template_registry",
    "ExcelTemplateRegistry",
    "ExcelTemplateDefinition",
    "ExcelTemplateMeta",
    "evaluate_excel_template_access",
    "authorize_excel_template_access",
    "ExcelTemplateAccessDecision",
    "render_excel",
    "render_excel_sheet",
    "excel_urlpatterns",
    "generate_excel_async",
    "excel_job_task",
    "OPENPYXL_AVAILABLE",
    "OPENPYXL_STYLES_AVAILABLE",
    "OPENPYXL_UTILS_AVAILABLE",
    "OPENPYXL_CHARTS_AVAILABLE",
    "ExcelRowData",
    "ExcelSheetData",
    "ExcelMultiSheetData",
    "ExcelData",
    "DEFAULT_HEADER_STYLE",
    "DEFAULT_CELL_STYLE",
    "DEFAULT_ALTERNATING_ROW_STYLE",
    "DEFAULT_BORDER_STYLE",
    "EXCEL_RATE_LIMIT_DEFAULTS",
    "EXCEL_CACHE_DEFAULTS",
    "EXCEL_ASYNC_DEFAULTS",
    "EXCEL_CATALOG_DEFAULTS",
    "add_bar_chart",
    "add_line_chart",
    "add_pie_chart",
]
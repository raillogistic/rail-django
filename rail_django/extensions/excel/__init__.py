"""
Excel export package for Rail Django.

This package provides comprehensive Excel export functionality with:
- Model method decorators for exposing Excel endpoints
- Pluggable styling configuration
- Access control (RBAC, permissions, guards)
- Async job support (thread, Celery, RQ)
- Response caching
- Rate limiting

Example usage:
    from rail_django.extensions.excel import model_excel_template

    class Product(models.Model):
        name = models.CharField(max_length=100)
        price = models.DecimalField(max_digits=10, decimal_places=2)

        @model_excel_template(
            url="products/export",
            title="Product Export",
            config={
                "header_style": {"bold": True, "fill_color": "4472C4"},
                "freeze_panes": True,
            }
        )
        def export_products(self):
            products = Product.objects.all()
            return [
                ["Name", "Price"],
                *[[p.name, p.price] for p in products]
            ]
"""

# Builder exports
from .builder import (
    OPENPYXL_AVAILABLE,
    OPENPYXL_CHARTS_AVAILABLE,
    OPENPYXL_STYLES_AVAILABLE,
    OPENPYXL_UTILS_AVAILABLE,
    add_bar_chart,
    add_line_chart,
    add_pie_chart,
    render_excel,
    render_excel_sheet,
)

# Config exports
from .config import (
    DEFAULT_ALTERNATING_ROW_STYLE,
    DEFAULT_BORDER_STYLE,
    DEFAULT_CELL_STYLE,
    DEFAULT_HEADER_STYLE,
    EXCEL_ASYNC_DEFAULTS,
    EXCEL_CACHE_DEFAULTS,
    EXCEL_CATALOG_DEFAULTS,
    EXCEL_RATE_LIMIT_DEFAULTS,
    ExcelData,
    ExcelMultiSheetData,
    ExcelRowData,
    ExcelSheetData,
    ExcelTemplateAccessDecision,
    ExcelTemplateDefinition,
    ExcelTemplateMeta,
)

# Access control exports
from .access import (
    _resolve_request_user,
    authorize_excel_template_access,
    evaluate_excel_template_access,
)

# Exporter exports
from .exporter import (
    ExcelTemplateRegistry,
    excel_template,
    excel_template_registry,
    model_excel_template,
)

# Jobs exports
from .jobs import (
    excel_job_task,
    generate_excel_async,
)

# URL exports
from .urls import excel_urlpatterns

# View exports
from .views import (
    ExcelTemplateCatalogView,
    ExcelTemplateJobDownloadView,
    ExcelTemplateJobStatusView,
    ExcelTemplateView,
)

__all__ = [
    # Views
    "ExcelTemplateView",
    "ExcelTemplateCatalogView",
    "ExcelTemplateJobStatusView",
    "ExcelTemplateJobDownloadView",
    # Decorators
    "model_excel_template",
    "excel_template",
    # Registry
    "excel_template_registry",
    "ExcelTemplateRegistry",
    "ExcelTemplateDefinition",
    "ExcelTemplateMeta",
    # Access control
    "evaluate_excel_template_access",
    "authorize_excel_template_access",
    "ExcelTemplateAccessDecision",
    # Rendering
    "render_excel",
    "render_excel_sheet",
    # URL patterns
    "excel_urlpatterns",
    # Async
    "generate_excel_async",
    "excel_job_task",
    # Constants
    "OPENPYXL_AVAILABLE",
    "OPENPYXL_STYLES_AVAILABLE",
    "OPENPYXL_UTILS_AVAILABLE",
    "OPENPYXL_CHARTS_AVAILABLE",
    # Type aliases
    "ExcelRowData",
    "ExcelSheetData",
    "ExcelMultiSheetData",
    "ExcelData",
    # Default style constants
    "DEFAULT_HEADER_STYLE",
    "DEFAULT_CELL_STYLE",
    "DEFAULT_ALTERNATING_ROW_STYLE",
    "DEFAULT_BORDER_STYLE",
    # Default config constants
    "EXCEL_RATE_LIMIT_DEFAULTS",
    "EXCEL_CACHE_DEFAULTS",
    "EXCEL_ASYNC_DEFAULTS",
    "EXCEL_CATALOG_DEFAULTS",
    # Chart utilities
    "add_bar_chart",
    "add_line_chart",
    "add_pie_chart",
]

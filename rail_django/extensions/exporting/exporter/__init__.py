"""Model Exporter Package

This package provides the ModelExporter class for exporting Django model data
to various formats (CSV, Excel, JSON).
"""

from .base import ModelExporterBase
from .csv_export import CSVExportMixin
from .excel_export import ExcelExportMixin, EXCEL_AVAILABLE
from .json_export import JSONExportMixin
from .queryset import QuerysetMixin
from .validation import ValidationMixin


class ModelExporter(
    QuerysetMixin,
    ValidationMixin,
    CSVExportMixin,
    ExcelExportMixin,
    JSONExportMixin,
    ModelExporterBase,
):
    """Handles the export of Django model data to various formats.

    This class provides methods to dynamically load models, apply GraphQL filters,
    extract field data with flexible field format support, and generate export files.

    Features:
        - Dynamic model loading from app and model names
        - GraphQL filter integration for advanced filtering
        - Flexible field format support (string or dict with accessor/title)
        - Nested field access with proper error handling
        - Property access on model instances (explicit allowlist)
        - Many-to-many field handling
        - CSV, Excel, and JSON export formats

    Example:
        >>> exporter = ModelExporter("blog", "Post")
        >>> csv_content = exporter.export_to_csv(
        ...     ["title", "author.username"],
        ...     variables={"where": {"status": "published"}},
        ...     ordering=["-created_at"],
        ... )
    """

    pass


__all__ = [
    "ModelExporter",
    "ModelExporterBase",
    "CSVExportMixin",
    "ExcelExportMixin",
    "EXCEL_AVAILABLE",
    "JSONExportMixin",
    "QuerysetMixin",
    "ValidationMixin",
]

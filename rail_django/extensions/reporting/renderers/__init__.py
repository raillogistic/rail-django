"""
Export renderers for the BI reporting module.

This package provides a pluggable renderer system for exporting reporting
data to various file formats (CSV, JSON, XLSX, PDF). Renderers are registered
in a global registry and resolved by format name.

Usage::

    from rail_django.extensions.reporting.renderers import get_renderer

    renderer = get_renderer("csv")
    file_bytes = renderer.render(payload, options={"delimiter": ";"})
"""

from .base import ExportRenderer, RendererRegistry, get_renderer, register_renderer
from .csv_renderer import CsvRenderer
from .json_renderer import JsonRenderer


# Auto-register built-in renderers
register_renderer(CsvRenderer())
register_renderer(JsonRenderer())

# Optional renderers (registered only if dependencies are available)
try:
    from .xlsx_renderer import XlsxRenderer
    register_renderer(XlsxRenderer())
except ImportError:
    pass

try:
    from .pdf_renderer import PdfRenderer
    register_renderer(PdfRenderer())
except ImportError:
    pass


__all__ = [
    "ExportRenderer",
    "RendererRegistry",
    "get_renderer",
    "register_renderer",
    "CsvRenderer",
    "JsonRenderer",
]

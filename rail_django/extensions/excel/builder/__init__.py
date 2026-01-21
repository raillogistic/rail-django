"""
Excel builder subpackage.

This package provides utilities for building Excel workbooks,
including styles, worksheets, and charts.
"""

from .charts import (
    OPENPYXL_CHARTS_AVAILABLE,
    add_bar_chart,
    add_line_chart,
    add_pie_chart,
)
from .styles import (
    OPENPYXL_STYLES_AVAILABLE,
    _apply_cell_style,
    _apply_header_style,
    _apply_number_format,
    _format_cell_value,
    _get_column_width,
)
from .workbook import OPENPYXL_AVAILABLE, render_excel
from .worksheet import (
    OPENPYXL_UTILS_AVAILABLE,
    _calculate_column_widths,
    render_excel_sheet,
)

__all__ = [
    # Workbook
    "OPENPYXL_AVAILABLE",
    "render_excel",
    # Worksheet
    "OPENPYXL_UTILS_AVAILABLE",
    "_calculate_column_widths",
    "render_excel_sheet",
    # Styles
    "OPENPYXL_STYLES_AVAILABLE",
    "_format_cell_value",
    "_get_column_width",
    "_apply_header_style",
    "_apply_cell_style",
    "_apply_number_format",
    # Charts
    "OPENPYXL_CHARTS_AVAILABLE",
    "add_bar_chart",
    "add_line_chart",
    "add_pie_chart",
]

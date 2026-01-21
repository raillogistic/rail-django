"""
Excel workbook creation utilities.

This module provides the main render_excel function for creating
complete Excel workbooks from data.
"""

import io
from typing import Any, Dict, Optional

# Optional openpyxl support
try:
    from openpyxl import Workbook

    OPENPYXL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    Workbook = None  # type: ignore
    OPENPYXL_AVAILABLE = False

from ..config import ExcelData, _default_excel_config
from .worksheet import render_excel_sheet


def render_excel(
    data: ExcelData,
    config: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Render data to an Excel file.

    Args:
        data: Single sheet data (list[list]) or multi-sheet data (dict[str, list[list]]).
        config: Optional style configuration.

    Returns:
        Excel file as bytes.

    Raises:
        RuntimeError: If openpyxl is not installed.
    """
    if not OPENPYXL_AVAILABLE:
        raise RuntimeError("openpyxl is required for Excel export")

    config = {**_default_excel_config(), **(config or {})}

    workbook = Workbook()

    # Determine if single-sheet or multi-sheet
    if isinstance(data, dict):
        # Multi-sheet format
        # Remove the default sheet
        workbook.remove(workbook.active)

        for sheet_name, sheet_data in data.items():
            worksheet = workbook.create_sheet(title=str(sheet_name)[:31])  # Excel limit
            render_excel_sheet(worksheet, sheet_data, config)
    else:
        # Single-sheet format
        worksheet = workbook.active
        worksheet.title = str(config.get("sheet_name", "Sheet1"))[:31]
        render_excel_sheet(worksheet, data, config)

    # Save to bytes
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output.getvalue()


__all__ = [
    "OPENPYXL_AVAILABLE",
    "render_excel",
]

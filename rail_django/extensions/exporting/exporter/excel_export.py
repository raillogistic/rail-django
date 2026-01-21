"""Excel Export Functionality

This module provides Excel export functionality as a mixin class.
"""

import io
from typing import Any, Callable, List, Optional, Union

from ..exceptions import ExportError

# Optional Excel support
try:
    import openpyxl
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


class ExcelExportMixin:
    """Mixin providing Excel export functionality."""

    def export_to_excel(
        self,
        fields: list[Union[str, dict[str, str]]],
        variables: Optional[dict[str, Any]] = None,
        ordering: Optional[Union[str, list[str]]] = None,
        max_rows: Optional[int] = None,
        parsed_fields: Optional[list[dict[str, str]]] = None,
        output: Optional[io.BytesIO] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        *,
        presets: Optional[List[str]] = None,
        distinct_on: Optional[List[str]] = None,
    ) -> bytes:
        """Export model data to Excel format with professional styling.

        Args:
            fields: List of field definitions (string or dict format).
            variables: Filter variables.
            ordering: Ordering expression(s).
            max_rows: Optional max rows cap.
            parsed_fields: Pre-validated field configurations.
            output: Optional output BytesIO.
            progress_callback: Callback for progress updates.
            presets: Optional list of preset names.
            distinct_on: Optional list of field names for DISTINCT ON.

        Returns:
            Excel file content as bytes.

        Raises:
            ExportError: If openpyxl is not available.
        """
        if not EXCEL_AVAILABLE:
            raise ExportError(
                "Excel export requires openpyxl package. "
                "Install with: pip install openpyxl"
            )

        # Use non-write-only mode for better styling support
        write_only = bool(self.export_settings.get("excel_write_only", False))
        workbook = openpyxl.Workbook(write_only=write_only)
        worksheet = workbook.active if not write_only else workbook.create_sheet()
        worksheet.title = f"{self.model_name} Export"

        # Hide gridlines (only works in non-write-only mode)
        if not write_only:
            worksheet.sheet_view.showGridLines = False

        # Professional style definitions - headers have fill only, no borders
        header_font = Font(bold=True, color="FFFFFF", size=11, name="Calibri")
        header_fill = PatternFill(
            start_color="2F5496", end_color="2F5496", fill_type="solid"
        )
        header_alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )

        # Data row styles (no borders)
        data_font = Font(size=10, name="Calibri")
        data_alignment = Alignment(vertical="center", wrap_text=False)

        # Row number column style
        row_num_font = Font(size=10, name="Calibri", color="666666")
        row_num_alignment = Alignment(horizontal="center", vertical="center")

        # Alternating row colors
        even_row_fill = PatternFill(
            start_color="F2F2F2", end_color="F2F2F2", fill_type="solid"
        )
        odd_row_fill = PatternFill(
            start_color="FFFFFF", end_color="FFFFFF", fill_type="solid"
        )

        # Parse field configurations
        if parsed_fields is None:
            parsed_fields = self.validate_fields(
                fields, export_settings=self.export_settings
            )

        # Write headers - first column is "#" for row numbers
        headers = ["#"] + [parsed_field["title"] for parsed_field in parsed_fields]
        if write_only:
            header_row = []
            for header in headers:
                cell = WriteOnlyCell(worksheet, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                header_row.append(cell)
            worksheet.append(header_row)
        else:
            for col_num, header in enumerate(headers, 1):
                cell = worksheet.cell(row=1, column=col_num, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment

        # Write data rows
        queryset = self.get_queryset(
            variables,
            ordering,
            fields=[field["accessor"] for field in parsed_fields],
            max_rows=max_rows,
            presets=presets,
            skip_validation=True,  # Already validated at view level
            distinct_on=distinct_on,
        )

        processed = 0
        progress_every = int(
            (self.export_settings.get("async_jobs") or {}).get(
                "progress_update_rows", 500
            )
        )
        if progress_every <= 0:
            progress_every = 500

        # Track max width per column for auto-sizing (including # column)
        column_widths = [3] + [len(str(h)) for h in headers[1:]]

        row_counter = 0  # Sequential row number for # column
        for row_num, instance in enumerate(queryset.iterator(), 2):
            row_counter += 1
            is_even_row = (row_num % 2) == 0
            row_fill = even_row_fill if is_even_row else odd_row_fill

            if write_only:
                row = []
                # First cell: row number
                num_cell = WriteOnlyCell(worksheet, value=row_counter)
                num_cell.font = row_num_font
                num_cell.fill = row_fill
                num_cell.alignment = row_num_alignment
                row.append(num_cell)
                # Data cells
                for col_idx, parsed_field in enumerate(parsed_fields):
                    accessor = parsed_field["accessor"]
                    value = self.get_field_value(instance, accessor)
                    cell = WriteOnlyCell(worksheet, value=value)
                    cell.font = data_font
                    cell.fill = row_fill
                    cell.alignment = data_alignment
                    row.append(cell)
                    # Track width (offset by 1 for # column)
                    val_len = len(str(value)) if value else 0
                    if val_len > column_widths[col_idx + 1]:
                        column_widths[col_idx + 1] = min(val_len, 50)
                worksheet.append(row)
            else:
                # First cell: row number
                num_cell = worksheet.cell(row=row_num, column=1, value=row_counter)
                num_cell.font = row_num_font
                num_cell.fill = row_fill
                num_cell.alignment = row_num_alignment
                # Data cells (start at column 2)
                for col_num, parsed_field in enumerate(parsed_fields, 2):
                    accessor = parsed_field["accessor"]
                    value = self.get_field_value(instance, accessor)
                    cell = worksheet.cell(row=row_num, column=col_num, value=value)
                    cell.font = data_font
                    cell.fill = row_fill
                    cell.alignment = data_alignment
                    # Track width (col_num - 1 maps to index in column_widths)
                    val_len = len(str(value)) if value else 0
                    if val_len > column_widths[col_num - 1]:
                        column_widths[col_num - 1] = min(val_len, 50)

            processed += 1
            if progress_callback and processed % progress_every == 0:
                progress_callback(processed)

        # Apply column widths and additional formatting (non write-only only)
        if not write_only:
            # Set column widths with padding
            for col_idx, width in enumerate(column_widths, 1):
                column_letter = get_column_letter(col_idx)
                if col_idx == 1:  # # column - fixed narrow width
                    worksheet.column_dimensions[column_letter].width = 6
                else:
                    worksheet.column_dimensions[column_letter].width = min(
                        width + 3, 50
                    )

            # Set row height for header
            worksheet.row_dimensions[1].height = 25

        # Save to bytes
        output = output or io.BytesIO()
        workbook.save(output)
        return output.getvalue() if isinstance(output, io.BytesIO) else b""

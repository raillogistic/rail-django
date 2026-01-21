"""CSV Export Functionality

This module provides CSV export functionality as a mixin class.
"""

import csv
import io
from typing import Any, Callable, List, Optional, Union


class CSVExportMixin:
    """Mixin providing CSV export functionality."""

    def export_to_csv(
        self,
        fields: list[Union[str, dict[str, str]]],
        variables: Optional[dict[str, Any]] = None,
        ordering: Optional[Union[str, list[str]]] = None,
        max_rows: Optional[int] = None,
        parsed_fields: Optional[list[dict[str, str]]] = None,
        output: Optional[io.StringIO] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: Optional[int] = None,
        *,
        presets: Optional[List[str]] = None,
        distinct_on: Optional[List[str]] = None,
    ) -> str:
        """Export model data to CSV format.

        Args:
            fields: List of field definitions (string or dict format).
            variables: Filter variables.
            ordering: Ordering expression(s).
            max_rows: Optional max rows cap.
            parsed_fields: Pre-validated field configurations.
            output: Optional output StringIO.
            progress_callback: Callback for progress updates.
            chunk_size: Number of rows per chunk for iteration.
            presets: Optional list of preset names.
            distinct_on: Optional list of field names for DISTINCT ON.

        Returns:
            CSV content as string.
        """
        output = output or io.StringIO()
        writer = csv.writer(output)

        # Parse field configurations
        if parsed_fields is None:
            parsed_fields = self.validate_fields(
                fields, export_settings=self.export_settings
            )

        # Write headers
        headers = [parsed_field["title"] for parsed_field in parsed_fields]
        writer.writerow(headers)

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

        if chunk_size is None:
            chunk_size = int(self.export_settings.get("csv_chunk_size", 1000))
        if chunk_size <= 0:
            chunk_size = 1000

        processed = 0
        for instance in queryset.iterator(chunk_size=chunk_size):
            row = []
            for parsed_field in parsed_fields:
                accessor = parsed_field["accessor"]
                value = self.get_field_value(instance, accessor)
                row.append(value)
            writer.writerow(row)
            processed += 1
            if progress_callback and processed % chunk_size == 0:
                progress_callback(processed)

        return output.getvalue() if isinstance(output, io.StringIO) else ""

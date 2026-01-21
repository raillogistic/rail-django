"""JSON Export Functionality

This module provides JSON export functionality as a mixin class.
"""

import json
from typing import Any, Callable, List, Optional, Union


class JSONExportMixin:
    """Mixin providing JSON export functionality."""

    def export_to_json(
        self,
        fields: list[Union[str, dict[str, str]]],
        variables: Optional[dict[str, Any]] = None,
        ordering: Optional[Union[str, list[str]]] = None,
        max_rows: Optional[int] = None,
        parsed_fields: Optional[list[dict[str, str]]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        *,
        presets: Optional[List[str]] = None,
        distinct_on: Optional[List[str]] = None,
        indent: Optional[int] = 2,
    ) -> str:
        """Export model data to JSON format.

        Args:
            fields: List of field definitions (string or dict format).
            variables: Filter variables.
            ordering: Ordering expression(s).
            max_rows: Optional max rows cap.
            parsed_fields: Pre-validated field configurations.
            progress_callback: Callback for progress updates.
            presets: Optional list of preset names.
            distinct_on: Optional list of field names for DISTINCT ON.
            indent: JSON indentation level (None for compact).

        Returns:
            JSON content as string.
        """
        # Parse field configurations
        if parsed_fields is None:
            parsed_fields = self.validate_fields(
                fields, export_settings=self.export_settings
            )

        # Get queryset
        queryset = self.get_queryset(
            variables,
            ordering,
            fields=[field["accessor"] for field in parsed_fields],
            max_rows=max_rows,
            presets=presets,
            skip_validation=True,
            distinct_on=distinct_on,
        )

        chunk_size = int(self.export_settings.get("csv_chunk_size", 1000))
        if chunk_size <= 0:
            chunk_size = 1000

        records = []
        processed = 0
        for instance in queryset.iterator(chunk_size=chunk_size):
            record = {}
            for parsed_field in parsed_fields:
                accessor = parsed_field["accessor"]
                title = parsed_field["title"]
                value = self.get_field_value(instance, accessor)
                record[title] = value
            records.append(record)
            processed += 1
            if progress_callback and processed % chunk_size == 0:
                progress_callback(processed)

        return json.dumps(records, indent=indent, ensure_ascii=False, default=str)

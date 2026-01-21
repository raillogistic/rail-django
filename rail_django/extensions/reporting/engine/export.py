"""
Export and pivot functionality for DatasetExecutionEngine.

This module contains the _pivot_rows method and any export-related
utility methods used by the execution engine.
"""

from __future__ import annotations

from typing import Any

from ..utils import _json_sanitize


class ExportMixin:
    """
    Mixin providing export and pivot functionality for the execution engine.

    These methods handle data transformation for export formats and pivot tables.
    """

    def _pivot_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        index: str,
        columns: str,
        values: list[str],
    ) -> dict[str, Any]:
        """
        Pivot an aggregated result into a matrix-like payload.

        Returns a dictionary containing:
        - `index_values`, `column_values`
        - `rows`: list of row dicts with dynamic value keys
        """

        index_values: list[Any] = []
        column_values: list[Any] = []
        table: dict[Any, dict[str, Any]] = {}

        def ensure_list_add(target: list[Any], value: Any) -> None:
            if value not in target:
                target.append(value)

        for row in rows:
            idx = row.get(index)
            col = row.get(columns)
            ensure_list_add(index_values, idx)
            ensure_list_add(column_values, col)
            table.setdefault(idx, {index: idx})
            for metric in values:
                table[idx][f"{col}:{metric}"] = row.get(metric)

        return _json_sanitize(
            {
                "index": index,
                "columns": columns,
                "values": values,
                "index_values": index_values,
                "column_values": column_values,
                "rows": [table[idx] for idx in index_values],
            }
        )


__all__ = ["ExportMixin"]

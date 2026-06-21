"""
CSV export renderer.

Renders reporting payloads as CSV files with configurable delimiter,
encoding, and column ordering.

Attributes:
    CsvRenderer: Renderer producing CSV output.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Optional

from .base import ExportRenderer


class CsvRenderer(ExportRenderer):
    """
    Renderer CSV pour les exports de données reporting.

    Supporte la configuration du délimiteur, de l'encodage, et de
    l'inclusion/exclusion des en-têtes.

    Options disponibles:
        - ``delimiter`` (str): Séparateur de colonnes (défaut: ``,``).
        - ``encoding`` (str): Encodage du fichier (défaut: ``utf-8-sig`` pour
          compatibilité Excel).
        - ``include_header`` (bool): Inclure la ligne d'en-tête (défaut: ``True``).
        - ``columns`` (list[str]): Colonnes à inclure et leur ordre. Si absent,
          toutes les colonnes des résultats sont utilisées.
    """

    format_name = "csv"
    content_type = "text/csv; charset=utf-8"
    file_extension = "csv"

    def render(
        self,
        payload: dict[str, Any],
        *,
        options: Optional[dict[str, Any]] = None,
    ) -> bytes:
        """
        Transforme un payload reporting en contenu CSV.

        Args:
            payload: Dictionnaire contenant ``rows`` (list[dict]) et
                     optionnellement ``columns`` (list[dict] avec ``name``).
            options: Options CSV (delimiter, encoding, include_header, columns).

        Returns:
            Contenu CSV encodé en bytes.
        """
        options = options or {}
        delimiter = str(options.get("delimiter", ","))
        encoding = str(options.get("encoding", "utf-8-sig"))
        include_header = bool(options.get("include_header", True))

        rows = payload.get("rows") or []
        if not rows:
            return b""

        # Determine column order
        column_names = options.get("columns")
        if not column_names:
            columns_meta = payload.get("columns") or []
            if columns_meta:
                column_names = [col.get("name", "") for col in columns_meta if col.get("name")]
            else:
                column_names = list(rows[0].keys()) if rows else []

        # Column labels for header
        columns_meta = payload.get("columns") or []
        label_map = {
            col.get("name", ""): col.get("label", col.get("name", ""))
            for col in columns_meta
        }

        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter)

        if include_header:
            header = [label_map.get(name, name) for name in column_names]
            writer.writerow(header)

        for row in rows:
            writer.writerow([
                self._format_value(row.get(name))
                for name in column_names
            ])

        return output.getvalue().encode(encoding)

    @staticmethod
    def _format_value(value: Any) -> str:
        """
        Formatte une valeur pour l'export CSV.

        Args:
            value: Valeur brute.

        Returns:
            Représentation chaîne de la valeur.
        """
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Oui" if value else "Non"
        if isinstance(value, (list, dict)):
            import json
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)


__all__ = ["CsvRenderer"]

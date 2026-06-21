"""
JSON export renderer.

Renders reporting payloads as formatted JSON files with configurable
indentation and encoding.

Attributes:
    JsonRenderer: Renderer producing JSON output.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from .base import ExportRenderer


class _ReportingJsonEncoder(json.JSONEncoder):
    """
    Encodeur JSON étendu pour les types courants du reporting.

    Gère les types ``datetime``, ``date``, ``Decimal``, ``UUID``, et ``set``.
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, set):
            return sorted(o)
        return super().default(o)


class JsonRenderer(ExportRenderer):
    """
    Renderer JSON pour les exports de données reporting.

    Produit un fichier JSON formaté et lisible avec les métadonnées
    du dataset et les résultats.

    Options disponibles:
        - ``indent`` (int): Indentation (défaut: ``2``).
        - ``encoding`` (str): Encodage du fichier (défaut: ``utf-8``).
        - ``include_metadata`` (bool): Inclure les métadonnées dans l'export
          (défaut: ``True``).
        - ``rows_only`` (bool): N'exporter que les lignes (défaut: ``False``).
    """

    format_name = "json"
    content_type = "application/json; charset=utf-8"
    file_extension = "json"

    def render(
        self,
        payload: dict[str, Any],
        *,
        options: Optional[dict[str, Any]] = None,
    ) -> bytes:
        """
        Transforme un payload reporting en contenu JSON.

        Args:
            payload: Dictionnaire de résultats complet.
            options: Options JSON (indent, encoding, include_metadata, rows_only).

        Returns:
            Contenu JSON encodé en bytes.
        """
        options = options or {}
        indent = int(options.get("indent", 2))
        encoding = str(options.get("encoding", "utf-8"))
        rows_only = bool(options.get("rows_only", False))
        include_metadata = bool(options.get("include_metadata", True))

        if rows_only:
            output = payload.get("rows", [])
        elif not include_metadata:
            output = {
                "rows": payload.get("rows", []),
                "columns": payload.get("columns", []),
            }
        else:
            output = payload

        content = json.dumps(
            output,
            indent=indent,
            ensure_ascii=False,
            cls=_ReportingJsonEncoder,
        )
        return content.encode(encoding)


__all__ = ["JsonRenderer"]

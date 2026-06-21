"""
Raw SQL data source adapter.

This adapter executes raw SQL queries against the Django database connection,
returning results as lists of dictionaries. ORM operations (F, Q, annotate)
are **not** supported — filtering and ordering happen in the SQL itself.

Attributes:
    SqlDataSourceAdapter: Adapter for raw SQL-backed data sources.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import connection

from ...types import ReportingError
from .base import DataSourceAdapter

logger = logging.getLogger(__name__)


class SqlDataSourceAdapter(DataSourceAdapter):
    """
    Adapter pour les sources de type ``sql`` (requête SQL brute).

    Exécute une requête SQL paramétrée et retourne les résultats sous forme
    de liste de dictionnaires. Les filtres runtime sont injectés via des
    paramètres nommés dans la requête.

    Attributes:
        sql: Requête SQL configurée.
        params: Paramètres par défaut pour la requête.
    """

    def __init__(self, source_config: dict[str, Any]) -> None:
        """
        Initialise l'adapter SQL.

        Args:
            source_config: Doit contenir ``sql`` (requête) et optionnellement
                           ``params`` (dict de paramètres par défaut).

        Raises:
            ReportingError: Si aucune requête SQL n'est fournie.
        """
        super().__init__(source_config)
        self.sql = source_config.get("sql", "")
        self.params = source_config.get("params") or {}
        if not self.sql:
            raise ReportingError(
                "Source SQL configuree sans requete. Renseignez 'metadata.sql'."
            )

    def get_base_queryset(self) -> list[dict[str, Any]]:
        """
        Exécute la requête SQL et retourne les résultats.

        Returns:
            Liste de dictionnaires (une entrée par ligne).

        Raises:
            ReportingError: En cas d'erreur d'exécution SQL.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(self.sql, self.params)
                columns = [col[0] for col in cursor.description or []]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error("Erreur d'execution SQL reporting: %s", exc)
            raise ReportingError(
                f"Erreur d'execution de la requete SQL: {exc}"
            ) from exc

    def get_model_class(self) -> None:
        """
        Les sources SQL n'ont pas de modèle Django associé.

        Returns:
            Toujours ``None``.
        """
        return None

    def validate_field_path(self, field_path: str) -> bool:
        """
        Valide un chemin de champ par rapport aux colonnes retournées.

        Pour les sources SQL, on accepte tout identifiant simple (sans ``__``
        traversal) car on ne connaît pas le schéma a priori. L'exécution
        échouera naturellement si la colonne n'existe pas.

        Args:
            field_path: Nom de colonne à valider.

        Returns:
            ``True`` si le champ est un identifiant simple valide.
        """
        if not field_path or not isinstance(field_path, str):
            return False
        if field_path.startswith("_"):
            return False
        # SQL sources don't support __ traversal
        if "__" in field_path:
            return False
        return field_path.isidentifier()

    def get_pk_field_name(self) -> str:
        """
        Retourne ``id`` comme champ PK par défaut pour les sources SQL.

        Returns:
            ``"id"``.
        """
        return "id"

    def supports_orm_operations(self) -> bool:
        """
        Les sources SQL ne supportent pas les opérations ORM.

        Returns:
            Toujours ``False``.
        """
        return False


__all__ = ["SqlDataSourceAdapter"]

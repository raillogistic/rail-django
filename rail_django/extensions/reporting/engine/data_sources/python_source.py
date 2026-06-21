"""
Python callable data source adapter.

This adapter invokes a Python callable (function or method) that returns
a list of dictionaries. The callable is resolved from a dotted import path
stored in the dataset metadata.

Attributes:
    PythonDataSourceAdapter: Adapter for Python callable-backed data sources.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Optional

from ...types import ReportingError
from .base import DataSourceAdapter

logger = logging.getLogger(__name__)


class PythonDataSourceAdapter(DataSourceAdapter):
    """
    Adapter pour les sources de type ``python`` (callable Python).

    Résout un chemin d'import pointé (ex: ``myapp.reports.get_revenue_data``)
    et invoque le callable pour obtenir les données.

    Attributes:
        callable_path: Chemin d'import du callable.
        callable_fn: Référence au callable résolu.
        callable_kwargs: Arguments supplémentaires passés au callable.
    """

    def __init__(self, source_config: dict[str, Any]) -> None:
        """
        Initialise l'adapter Python.

        Args:
            source_config: Doit contenir ``callable`` (chemin d'import pointé)
                           et optionnellement ``callable_kwargs`` (dict d'arguments).

        Raises:
            ReportingError: Si le callable est introuvable ou non invocable.
        """
        super().__init__(source_config)
        self.callable_path = source_config.get("callable", "")
        self.callable_kwargs = source_config.get("callable_kwargs") or {}
        if not self.callable_path:
            raise ReportingError(
                "Source Python configuree sans callable. "
                "Renseignez 'metadata.callable' (ex: 'myapp.reports.get_data')."
            )
        self.callable_fn = self._resolve_callable()

    def _resolve_callable(self) -> Callable[..., list[dict[str, Any]]]:
        """
        Résout le chemin d'import vers un callable Python.

        Returns:
            Le callable résolu.

        Raises:
            ReportingError: Si le module ou l'attribut est introuvable.
        """
        try:
            parts = self.callable_path.rsplit(".", 1)
            if len(parts) != 2:
                raise ReportingError(
                    f"Chemin callable invalide: '{self.callable_path}'. "
                    f"Format attendu: 'module.path.function_name'."
                )
            module_path, func_name = parts
            module = importlib.import_module(module_path)
            func = getattr(module, func_name, None)
            if func is None:
                raise ReportingError(
                    f"Callable '{func_name}' introuvable dans '{module_path}'."
                )
            if not callable(func):
                raise ReportingError(
                    f"'{self.callable_path}' n'est pas un callable."
                )
            return func
        except ImportError as exc:
            raise ReportingError(
                f"Module introuvable pour callable '{self.callable_path}': {exc}"
            ) from exc

    def get_base_queryset(self) -> list[dict[str, Any]]:
        """
        Invoque le callable Python et retourne les résultats.

        Returns:
            Liste de dictionnaires retournée par le callable.

        Raises:
            ReportingError: Si le callable échoue ou retourne un format invalide.
        """
        try:
            result = self.callable_fn(**self.callable_kwargs)
        except Exception as exc:
            logger.error(
                "Erreur d'execution du callable '%s': %s",
                self.callable_path, exc,
            )
            raise ReportingError(
                f"Erreur d'execution du callable '{self.callable_path}': {exc}"
            ) from exc

        if not isinstance(result, list):
            raise ReportingError(
                f"Le callable '{self.callable_path}' doit retourner une list[dict], "
                f"type recu: {type(result).__name__}."
            )
        return result

    def get_model_class(self) -> None:
        """
        Les sources Python n'ont pas de modèle Django associé.

        Returns:
            Toujours ``None``.
        """
        return None

    def validate_field_path(self, field_path: str) -> bool:
        """
        Valide un nom de champ pour une source Python.

        Accepte tout identifiant simple. Les traversées ``__`` ne sont pas
        supportées pour les sources non-ORM.

        Args:
            field_path: Nom de champ à valider.

        Returns:
            ``True`` si le nom est un identifiant Python valide.
        """
        if not field_path or not isinstance(field_path, str):
            return False
        if field_path.startswith("_"):
            return False
        if "__" in field_path:
            return False
        return field_path.isidentifier()

    def get_pk_field_name(self) -> str:
        """
        Retourne ``id`` comme champ PK par défaut.

        Returns:
            ``"id"``.
        """
        return "id"

    def supports_orm_operations(self) -> bool:
        """
        Les sources Python ne supportent pas les opérations ORM.

        Returns:
            Toujours ``False``.
        """
        return False


__all__ = ["PythonDataSourceAdapter"]

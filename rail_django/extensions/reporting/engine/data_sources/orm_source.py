"""
Django ORM data source adapter.

This adapter wraps the standard Django ORM model access pattern, providing
queryset creation, field validation, and full ORM operation support.

Attributes:
    OrmDataSourceAdapter: Adapter for Django model-backed data sources.
"""

from __future__ import annotations

from typing import Any, Optional

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models

from ...types import ReportingError
from .base import DataSourceAdapter


class OrmDataSourceAdapter(DataSourceAdapter):
    """
    Adapter pour les sources de type ``model`` (Django ORM).

    Résout un modèle Django à partir de ``source_app_label`` et ``source_model``,
    puis fournit un queryset standard et la validation de champs.

    Attributes:
        model: Classe du modèle Django résolu.
    """

    def __init__(self, source_config: dict[str, Any]) -> None:
        """
        Initialise l'adapter ORM.

        Args:
            source_config: Doit contenir ``app_label`` et ``model_name``.

        Raises:
            ReportingError: Si le modèle n'est pas trouvé.
        """
        super().__init__(source_config)
        app_label = source_config.get("app_label", "")
        model_name = source_config.get("model_name", "")
        try:
            self.model = apps.get_model(app_label, model_name)
        except LookupError as exc:
            raise ReportingError(
                f"Impossible de trouver le modele {app_label}.{model_name}"
            ) from exc

    def get_base_queryset(self) -> models.QuerySet:
        """
        Retourne le queryset de base ``Model.objects.all()``.

        Returns:
            QuerySet non filtré du modèle.
        """
        return self.model.objects.all()

    def get_model_class(self) -> Optional[type[models.Model]]:
        """
        Retourne la classe du modèle Django.

        Returns:
            Classe ``models.Model``.
        """
        return self.model

    def validate_field_path(self, field_path: str) -> bool:
        """
        Valide un chemin de champ ORM (incluant les relations via ``__``).

        Args:
            field_path: Chemin du champ (ex: ``order__customer__name``).

        Returns:
            ``True`` si le chemin est valide et traversable.
        """
        if not field_path or not isinstance(field_path, str):
            return False
        if field_path.startswith("_"):
            return False
        parts = [part for part in field_path.split("__") if part]
        if not parts:
            return False

        current_model = self.model
        for part in parts:
            try:
                field = current_model._meta.get_field(part)
            except FieldDoesNotExist:
                return False
            if field.is_relation and getattr(field, "related_model", None):
                current_model = field.related_model
        return True

    def get_pk_field_name(self) -> str:
        """
        Retourne le nom du champ PK du modèle.

        Returns:
            Nom du champ PK (ex: ``id``).
        """
        pk = getattr(self.model._meta, "pk", None)
        name = getattr(pk, "name", None)
        return name or "id"

    def supports_orm_operations(self) -> bool:
        """
        L'adapter ORM supporte toutes les opérations Django ORM.

        Returns:
            Toujours ``True``.
        """
        return True


__all__ = ["OrmDataSourceAdapter"]

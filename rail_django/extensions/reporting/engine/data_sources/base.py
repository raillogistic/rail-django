"""
Abstract base class for data source adapters.

Defines the contract that all data source implementations must fulfill
to be usable by the ``DatasetExecutionEngine``.

Attributes:
    DataSourceAdapter: Abstract base class defining the adapter interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING

from django.db.models import QuerySet

if TYPE_CHECKING:
    from ...types import FilterSpec


class DataSourceAdapter(ABC):
    """
    Interface pour les sources de données du reporting engine.

    Chaque adapter encapsule la logique d'accès aux données pour un
    type de source spécifique (ORM, SQL brut, callable Python, etc.).

    Attributes:
        source_config: Configuration brute de la source (app_label, model, sql, etc.).
    """

    def __init__(self, source_config: dict[str, Any]) -> None:
        """
        Initialise l'adapter avec la configuration de source.

        Args:
            source_config: Dictionnaire contenant la configuration de la source
                           de données (app_label, model, sql, callable, etc.).
        """
        self.source_config = source_config

    @abstractmethod
    def get_base_queryset(self) -> QuerySet | list[dict[str, Any]]:
        """
        Retourne le jeu de données initial brut.

        Returns:
            QuerySet Django ou liste de dictionnaires.
        """

    @abstractmethod
    def get_model_class(self) -> Optional[Any]:
        """
        Retourne la classe de modèle Django sous-jacente, si applicable.

        Returns:
            La classe ``models.Model`` ou ``None`` pour les sources non-ORM.
        """

    @abstractmethod
    def validate_field_path(self, field_path: str) -> bool:
        """
        Valide qu'un chemin de champ est accessible sur cette source.

        Args:
            field_path: Chemin du champ (ex: ``order__customer__name``).

        Returns:
            ``True`` si le champ existe et est accessible.
        """

    @abstractmethod
    def get_pk_field_name(self) -> str:
        """
        Retourne le nom du champ clé primaire.

        Returns:
            Nom du champ PK (ex: ``id``).
        """

    @abstractmethod
    def supports_orm_operations(self) -> bool:
        """
        Indique si l'adapter supporte les opérations ORM avancées.

        Les opérations ORM incluent ``F()``, ``Q()``, ``annotate()``,
        ``values()``, etc. Les sources SQL/Python ne les supportent pas.

        Returns:
            ``True`` si les opérations ORM sont disponibles.
        """


__all__ = ["DataSourceAdapter"]

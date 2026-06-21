"""
Service layer for the BI reporting module.

Provides a standalone API for executing reporting operations without depending
on Django model instances. Useful for programmatic access, testing, and
integration with external systems.

Attributes:
    ReportingService: Static methods for executing datasets, rendering
                      visualizations, and exporting data.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import ReportingError


class ReportingService:
    """
    Service layer pour le reporting — utilisable sans instances de modèles.

    Fournit des méthodes statiques pour exécuter des datasets, construire
    des payloads de visualisation, exporter vers différents formats, et
    décrire le semantic layer.

    Toutes les méthodes acceptent des identifiants (code, ID) ou des
    instances de modèles pour une flexibilité maximale.
    """

    @staticmethod
    def execute_dataset(
        dataset_code: str,
        *,
        spec: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Exécute un dataset par son code avec une spec de requête optionnelle.

        Args:
            dataset_code: Code unique du dataset.
            spec: Spécification de requête (mode, dimensions, metrics, filters, etc.).

        Returns:
            Résultats de la requête.

        Raises:
            ReportingError: Si le dataset n'existe pas.
        """
        from .models import ReportingDataset

        try:
            dataset = ReportingDataset.objects.get(code=dataset_code)
        except ReportingDataset.DoesNotExist as exc:
            raise ReportingError(
                f"Dataset introuvable: '{dataset_code}'."
            ) from exc

        engine = dataset.build_engine()
        return engine.run_query(spec or {})

    @staticmethod
    def preview_dataset(
        dataset_code: str,
        *,
        quick: str = "",
        limit: int = 50,
        ordering: str = "",
        filters: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Exécute un aperçu simplifié d'un dataset.

        Args:
            dataset_code: Code unique du dataset.
            quick: Recherche rapide.
            limit: Nombre maximum de lignes.
            ordering: Expression de tri.
            filters: Filtres additionnels.

        Returns:
            Résultats de l'aperçu.

        Raises:
            ReportingError: Si le dataset n'existe pas.
        """
        from .models import ReportingDataset

        try:
            dataset = ReportingDataset.objects.get(code=dataset_code)
        except ReportingDataset.DoesNotExist as exc:
            raise ReportingError(
                f"Dataset introuvable: '{dataset_code}'."
            ) from exc

        return dataset.preview(
            quick=quick,
            limit=limit,
            ordering=ordering,
            filters=filters,
        )

    @staticmethod
    def describe_dataset(
        dataset_code: str,
        *,
        include_model_fields: bool = True,
    ) -> dict[str, Any]:
        """
        Retourne la description du semantic layer d'un dataset.

        Args:
            dataset_code: Code unique du dataset.
            include_model_fields: Inclure les champs du modèle Django.

        Returns:
            Description du dataset incluant dimensions, métriques, et champs.

        Raises:
            ReportingError: Si le dataset n'existe pas.
        """
        from .models import ReportingDataset

        try:
            dataset = ReportingDataset.objects.get(code=dataset_code)
        except ReportingDataset.DoesNotExist as exc:
            raise ReportingError(
                f"Dataset introuvable: '{dataset_code}'."
            ) from exc

        engine = dataset.build_engine()
        return engine.describe_dataset(include_model_fields=include_model_fields)

    @staticmethod
    def render_visualization(
        visualization_code: str,
        dataset_code: str,
        *,
        quick: str = "",
        limit: int = 200,
        filters: Optional[dict] = None,
        spec: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Exécute une visualisation par ses codes dataset + visualization.

        Args:
            visualization_code: Code de la visualisation.
            dataset_code: Code du dataset parent.
            quick: Recherche rapide.
            limit: Limite de lignes.
            filters: Filtres runtime.
            spec: Spec BI additionnelle.

        Returns:
            Payload de visualisation avec données et configuration.

        Raises:
            ReportingError: Si la visualisation ou le dataset n'existe pas.
        """
        from .models import ReportingVisualization

        try:
            viz = ReportingVisualization.objects.select_related("dataset").get(
                code=visualization_code,
                dataset__code=dataset_code,
            )
        except ReportingVisualization.DoesNotExist as exc:
            raise ReportingError(
                f"Visualisation introuvable: '{visualization_code}' "
                f"dans le dataset '{dataset_code}'."
            ) from exc

        return viz.render(
            quick=quick,
            limit=limit,
            filters=filters,
            spec=spec,
        )

    @staticmethod
    def export_to_format(
        payload: dict[str, Any],
        *,
        format_name: str,
        options: Optional[dict[str, Any]] = None,
    ) -> bytes:
        """
        Exporte un payload vers le format demandé.

        Args:
            payload: Données de reporting (résultat de ``run_query`` ou ``preview``).
            format_name: Identifiant du format (csv, json, xlsx, pdf).
            options: Options spécifiques au renderer.

        Returns:
            Contenu du fichier en bytes.

        Raises:
            ValueError: Si le format n'est pas disponible.
        """
        from .renderers import get_renderer

        renderer = get_renderer(format_name)
        return renderer.render(payload, options=options)

    @staticmethod
    def get_available_export_formats() -> list[str]:
        """
        Liste les formats d'export disponibles.

        Returns:
            Liste des identifiants de format enregistrés.
        """
        from .renderers.base import _registry

        return _registry.available_formats()

    @staticmethod
    def get_available_visualization_types() -> list[dict[str, Any]]:
        """
        Liste les types de visualisation disponibles.

        Returns:
            Liste de dictionnaires décrivant chaque type.
        """
        from .visualization_registry import get_available_types

        return [
            {
                "name": t.name,
                "label": t.label,
                "icon": t.icon,
                "description": t.description,
                "category": t.category,
                "required_dimensions": t.required_dimensions,
                "required_metrics": t.required_metrics,
                "supports_pivot": t.supports_pivot,
            }
            for t in get_available_types()
        ]

    @staticmethod
    def build_report_payload(
        report_code: str,
        *,
        quick: str = "",
        limit: int = 200,
        filters: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Construit le payload complet d'un rapport par son code.

        Args:
            report_code: Code unique du rapport.
            quick: Recherche rapide appliquée à toutes les visualisations.
            limit: Limite par visualisation.
            filters: Filtres globaux.

        Returns:
            Payload complet du rapport.

        Raises:
            ReportingError: Si le rapport n'existe pas.
        """
        from .models import ReportingReport

        try:
            report = ReportingReport.objects.get(code=report_code)
        except ReportingReport.DoesNotExist as exc:
            raise ReportingError(
                f"Rapport introuvable: '{report_code}'."
            ) from exc

        return report.build_payload(
            quick=quick,
            limit=limit,
            filters=filters,
        )


__all__ = ["ReportingService"]

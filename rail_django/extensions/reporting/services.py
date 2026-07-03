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

from typing import Any, Iterable, Optional

from django.db import transaction

from .types import ReportingError, ReportingExecutionContext


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
    def list_reports(context: ReportingExecutionContext) -> list[dict[str, Any]]:
        """Return reports visible to the current user."""
        from .models import ReportingReport
        from .security import report_is_visible_to_user

        user = getattr(context, "user", None)
        reports = ReportingReport.objects.prefetch_related(
            "blocks__visualization__dataset"
        )
        return [
            {
                "id": str(report.pk),
                "code": report.code,
                "title": report.title,
                "description": report.description,
                "theme": report.theme,
                "updated_at": str(report.updated_at),
                "export_formats": ReportingService.get_available_export_formats(),
            }
            for report in reports
            if report_is_visible_to_user(report, user)
        ]

    @staticmethod
    def execute_dataset(
        context: ReportingExecutionContext,
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

        engine = dataset.build_engine(context=context)
        return engine.run_query(spec or {})

    @staticmethod
    def preview_dataset(
        context: ReportingExecutionContext,
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
            context=context,
            quick=quick,
            limit=limit,
            ordering=ordering,
            filters=filters,
        )

    @staticmethod
    def describe_dataset(
        context: ReportingExecutionContext,
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

        engine = dataset.build_engine(context=context)
        return engine.describe_dataset(include_model_fields=include_model_fields)

    @staticmethod
    def render_visualization(
        context: ReportingExecutionContext,
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
            context=context,
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
        context: ReportingExecutionContext,
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
            report = ReportingReport.objects.prefetch_related(
                "blocks__visualization__dataset"
            ).get(code=report_code)
        except ReportingReport.DoesNotExist as exc:
            raise ReportingError(
                f"Rapport introuvable: '{report_code}'."
            ) from exc

        from .security import report_is_visible_to_user

        if not report_is_visible_to_user(report, getattr(context, "user", None)):
            raise ReportingError("Vous n'etes pas autorise a consulter ce rapport.")
        payload = report.build_payload(
            context=context,
            quick=quick,
            limit=limit,
            filters=filters,
        )
        payload["export_formats"] = ReportingService.get_available_export_formats()
        return payload

    @staticmethod
    def create_report_export(
        context: ReportingExecutionContext,
        report_code: str,
        *,
        format_name: str,
        filters: Optional[dict] = None,
    ):
        """Create and synchronously execute an owner-scoped report export."""
        from .models import ReportingExportJob, ReportingReport
        from .security import report_is_visible_to_user

        user = getattr(context, "user", None)
        try:
            report = ReportingReport.objects.prefetch_related(
                "blocks__visualization__dataset"
            ).get(code=report_code)
        except ReportingReport.DoesNotExist as exc:
            raise ReportingError(f"Rapport introuvable: '{report_code}'.") from exc
        if not report_is_visible_to_user(report, user):
            raise ReportingError("Vous n'etes pas autorise a exporter ce rapport.")
        if format_name not in ReportingService.get_available_export_formats():
            raise ReportingError(f"Format d'export indisponible: '{format_name}'.")
        job = ReportingExportJob.objects.create(
            title=report.title,
            report=report,
            format=format_name,
            filters=filters or {},
            requested_by=user,
        )
        job.run_export(context=context)
        return job

    @staticmethod
    @transaction.atomic
    def sync_catalog(
        datasets: Iterable[dict],
        visualizations: Iterable[dict],
        reports: Iterable[dict],
        *,
        overwrite: bool = False,
    ) -> dict[str, dict[str, int]]:
        """Create or deliberately overwrite a declarative reporting catalog."""
        from .models import (
            ReportingDataset,
            ReportingReport,
            ReportingReportBlock,
            ReportingVisualization,
        )

        result = {
            name: {"created": 0, "updated": 0, "skipped": 0}
            for name in ("datasets", "visualizations", "reports")
        }

        def persist(model, lookup, defaults, bucket):
            instance = model.objects.filter(**lookup).first()
            if instance and not overwrite:
                result[bucket]["skipped"] += 1
                return instance, False
            instance, created = model.objects.update_or_create(
                **lookup, defaults=defaults
            )
            result[bucket]["created" if created else "updated"] += 1
            return instance, created

        for item in datasets:
            defaults = {
                key: item.get(key, default)
                for key, default in {
                    "title": "",
                    "description": "",
                    "source_kind": "model",
                    "source_app_label": "",
                    "source_model": "",
                    "default_filters": [],
                    "dimensions": [],
                    "metrics": [],
                    "computed_fields": [],
                    "ordering": [],
                    "preview_limit": 50,
                    "metadata": {},
                    "allowed_roles": [],
                }.items()
            }
            defaults["allowed_roles"] = item.get(
                "allowed_roles",
                (item.get("metadata") or {}).get("allowed_roles", []),
            )
            defaults["origin"] = ReportingDataset.Origin.CATALOG
            persist(
                ReportingDataset,
                {"code": item["code"]},
                defaults,
                "datasets",
            )

        for item in visualizations:
            dataset = ReportingDataset.objects.get(code=item["dataset_code"])
            defaults = {
                key: item.get(key, default)
                for key, default in {
                    "title": "",
                    "description": "",
                    "kind": "table",
                    "config": {},
                    "default_filters": [],
                    "options": {},
                    "is_default": False,
                }.items()
            }
            defaults.update(
                dataset=dataset, origin=ReportingVisualization.Origin.CATALOG
            )
            persist(
                ReportingVisualization,
                {"dataset": dataset, "code": item["code"]},
                defaults,
                "visualizations",
            )

        for item in reports:
            defaults = {
                key: item.get(key, default)
                for key, default in {
                    "title": "",
                    "description": "",
                    "layout": {},
                    "filters": [],
                    "theme": "light",
                    "allowed_roles": [],
                }.items()
            }
            defaults["origin"] = ReportingReport.Origin.CATALOG
            report, created = persist(
                ReportingReport,
                {"code": item["code"]},
                defaults,
                "reports",
            )
            if created or overwrite:
                report.blocks.all().delete()
                ReportingReportBlock.objects.bulk_create(
                    [
                        ReportingReportBlock(
                            report=report,
                            visualization=ReportingVisualization.objects.get(
                                code=block["visualization_code"]
                            ),
                            position=block["position"],
                            layout=block.get("layout", {}),
                            title_override=block.get("title_override", ""),
                        )
                        for block in item.get("blocks", [])
                    ]
                )
        return result


__all__ = ["ReportingService"]

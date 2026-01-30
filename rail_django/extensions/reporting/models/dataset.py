"""
ReportingDataset model for the BI reporting module.

This module contains the ReportingDataset model which stores reusable
dataset definitions for BI rendering.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.core.decorators import action_form, confirm_action

from ..types import FilterSpec
from ..utils import _coerce_int, _to_filter_list, _to_ordering
from ..security import _reporting_roles, _reporting_operations

if TYPE_CHECKING:
    from ..engine import DatasetExecutionEngine


class ReportingDataset(models.Model):
    """Stores reusable dataset definitions for BI rendering."""

    class SourceKind(models.TextChoices):
        MODEL = "model", "Modele Django"
        SQL = "sql", "SQL"
        GRAPHQL = "graphql", "GraphQL"
        PYTHON = "python", "Python"

    code = models.SlugField(unique=True, max_length=80, verbose_name="Code")
    title = models.CharField(max_length=120, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description detaillee")
    source_app_label = models.CharField(
        max_length=120, verbose_name="Application source"
    )
    source_model = models.CharField(max_length=120, verbose_name="Modele source")
    source_kind = models.CharField(
        max_length=30,
        choices=SourceKind.choices,
        default=SourceKind.MODEL,
        verbose_name="Type de source",
    )
    default_filters = models.JSONField(
        default=list,
        verbose_name="Filtres par defaut",
        help_text="Liste de filtres {field, lookup, value}.",
    )
    dimensions = models.JSONField(
        default=list,
        verbose_name="Dimensions",
        help_text="Colonnes pour regroupements/axes.",
    )
    metrics = models.JSONField(
        default=list,
        verbose_name="Mesures",
        help_text="Agregations (sum, avg, count...).",
    )
    computed_fields = models.JSONField(
        default=list,
        verbose_name="Champs calcules",
        help_text="Formules basees sur dimensions/mesures.",
    )
    ordering = models.JSONField(
        default=list,
        verbose_name="Tri par defaut",
        help_text="Expressions order_by appliquees lors des executions.",
    )
    preview_limit = models.PositiveIntegerField(
        default=50, verbose_name="Limite apercu"
    )
    metadata = models.JSONField(
        default=dict,
        verbose_name="Metadonnees UI",
        help_text="Sections, quick fields, champs favorises.",
    )
    last_materialized_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Derniere materialisation"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mise a jour")

    class Meta:
        app_label = "rail_django"
        verbose_name = "Jeu de donnees BI"
        verbose_name_plural = "Jeux de donnees BI"
        ordering = ["title", "code"]
        permissions = [
            ("run_dataset_preview", "Peut executer un apercu de dataset"),
            ("materialize_dataset", "Peut materialiser un dataset"),
        ]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["code", "title", "description"],
            fields={
                "code": GraphQLMetaBase.FilterField(lookups=["icontains", "exact"]),
                "title": GraphQLMetaBase.FilterField(lookups=["icontains"]),
                "source_app_label": GraphQLMetaBase.FilterField(lookups=["exact"]),
                "source_model": GraphQLMetaBase.FilterField(lookups=["exact"]),
            },
        )
        fields = GraphQLMetaBase.Fields(
            read_only=[
                "created_at",
                "updated_at",
                "last_materialized_at",
            ]
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "code", "title", "created_at", "updated_at"],
            default=["title"],
        )
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.code})"

    def clean(self) -> None:
        if not self.source_app_label or not self.source_model:
            raise ValidationError(
                "L application et le modele source sont obligatoires."
            )
        try:
            apps.get_model(self.source_app_label, self.source_model)
        except LookupError:
            raise ValidationError(
                f"Impossible de resoudre {self.source_app_label}.{self.source_model}"
            )

    def build_engine(self) -> "DatasetExecutionEngine":
        from django.db import connection
        from ..engine import DatasetExecutionEngine

        if connection.vendor == "postgresql":
            try:
                from ..engine import PostgresDatasetExecutionEngine

                return PostgresDatasetExecutionEngine(self)
            except ImportError:
                pass
        return DatasetExecutionEngine(self)

    def _runtime_filters(self, filters: Optional[dict]) -> list[FilterSpec]:
        if not filters:
            return []
        if isinstance(filters, dict):
            items = filters.get("items") or filters.get("filters") or []
        else:
            items = filters
        return _to_filter_list(items)

    @action_form(
        title="Previsualiser le dataset",
        description="Execute le dataset avec filtres rapides pour alimenter un tableau ou un graphique.",
        submit_label="Lancer l apercu",
        fields={
            "quick": {"label": "Recherche rapide", "type": "text"},
            "limit": {"label": "Nombre de lignes", "type": "number"},
            "ordering": {
                "label": "Tri",
                "type": "text",
                "help_text": "Expression order_by (ex: -created_at).",
            },
            "filters": {
                "label": "Filtres additionnels",
                "type": "json",
                "help_text": "Liste {field, lookup, value}.",
            },
        },
    )
    def preview(
        self,
        quick: str = "",
        limit: Any = 50,
        ordering: str = "",
        filters: Optional[dict] = None,
    ) -> dict:
        engine = self.build_engine()
        runtime_filters = self._runtime_filters(filters)
        coerced_limit = _coerce_int(limit, default=self.preview_limit)
        result = engine.run(
            runtime_filters=runtime_filters,
            limit=coerced_limit or self.preview_limit,
            ordering=_to_ordering(ordering),
            quick_search=quick,
        )
        return result

    @action_form(
        title="Executer une requete BI",
        description="Moteur dynamique (dimensions, mesures, pivot, having) pour dashboards.",
        submit_label="Executer",
        fields={
            "spec": {
                "label": "Spec JSON",
                "type": "json",
                "help_text": "Spec: {mode, dimensions, metrics, computed_fields, filters, having, ordering, limit, offset, pivot, cache}.",
            }
        },
    )
    def run_query(self, spec: Optional[dict] = None) -> dict:
        engine = self.build_engine()
        return engine.run_query(spec or {})

    @action_form(
        title="Decrire le dataset",
        description="Retourne le semantic layer et (optionnellement) les champs du modele source.",
        submit_label="Decrire",
        fields={
            "include_model_fields": {
                "label": "Inclure champs modele",
                "type": "boolean",
                "help_text": "Active pour builder des filtres/dimensions ad-hoc.",
            }
        },
    )
    def describe(self, include_model_fields: bool = True) -> dict:
        engine = self.build_engine()
        return engine.describe_dataset(include_model_fields=bool(include_model_fields))

    @confirm_action(
        title="Materialiser l apercu",
        message="Capture un snapshot pour reutiliser le dataset hors ligne.",
        confirm_label="Materialiser",
        severity="primary",
    )
    def materialize(self) -> bool:
        engine = self.build_engine()
        snapshot = engine.run(limit=self.preview_limit)
        meta = dict(self.metadata or {})
        meta["materialized_snapshot"] = snapshot
        self.metadata = meta
        self.last_materialized_at = timezone.now()
        self.save(update_fields=["metadata", "last_materialized_at", "updated_at"])
        return True


__all__ = ["ReportingDataset"]

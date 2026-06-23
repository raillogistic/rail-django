"""
ReportingVisualization model for the BI reporting module.

This module contains the ReportingVisualization model which represents
visualizations attached to a dataset. Supported visualization types are
defined in the visualization registry.
"""

from __future__ import annotations

from typing import Any, Optional

from django.db import models

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.core.decorators import action_form

from ..types import FilterSpec
from ..utils import _coerce_int, _to_filter_list
from ..security import (
    _reporting_roles,
    _reporting_operations,
    dataset_is_visible_to_user,
)
from ..visualization_registry import get_type_choices


class ReportingVisualization(models.Model):
    """Visualization attached to a dataset. Types are defined in the registry."""

    dataset = models.ForeignKey(
        "ReportingDataset",
        related_name="visualizations",
        on_delete=models.CASCADE,
        verbose_name="Jeu de donnees",
    )
    code = models.SlugField(max_length=80, verbose_name="Code")
    title = models.CharField(max_length=120, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    kind = models.CharField(
        max_length=30,
        choices=get_type_choices(),
        default="table",
        verbose_name="Type",
    )
    config = models.JSONField(
        default=dict,
        verbose_name="Configuration",
        help_text="Axes, colonnes, legende, couleurs.",
    )
    default_filters = models.JSONField(
        default=list,
        verbose_name="Filtres par defaut",
        help_text="Filtres appliques avant l execution.",
    )
    options = models.JSONField(
        default=dict,
        verbose_name="Options UI",
        help_text="Preferences de rendu (theme, animations).",
    )
    is_default = models.BooleanField(
        default=False, verbose_name="Visualisation par defaut"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mise a jour")

    class Meta:
        app_label = "rail_django"
        verbose_name = "Visualisation BI"
        verbose_name_plural = "Visualisations BI"
        ordering = ["dataset__title", "title"]
        unique_together = (("dataset", "code"),)

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["code", "title", "description"],
            fields={
                "dataset_id": GraphQLMetaBase.FilterField(lookups=["exact"]),
                "kind": GraphQLMetaBase.FilterField(lookups=["exact"]),
            },
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "title", "code", "created_at"],
            default=["title"],
        )
        fields = GraphQLMetaBase.Fields(
            read_only=["created_at", "updated_at"],
        )
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )
        resolvers = GraphQLMetaBase.Resolvers(
            queries={
                "list": "resolve_visible_queryset",
                "retrieve": "resolve_visible_queryset",
            }
        )

    @staticmethod
    def resolve_visible_queryset(queryset, info, **kwargs):
        user = getattr(getattr(info, "context", None), "user", None)
        visible_ids = [
            visualization.pk
            for visualization in queryset.select_related("dataset")
            if dataset_is_visible_to_user(visualization.dataset, user)
        ]
        return queryset.filter(pk__in=visible_ids)

    def __str__(self) -> str:
        return f"{self.title} ({self.kind})"

    def _merge_filters(self, runtime_filters: Optional[dict]) -> list[FilterSpec]:
        base = _to_filter_list(self.default_filters)
        merged = base + _to_filter_list(
            runtime_filters.get("filters", runtime_filters) if runtime_filters else []
        )
        return merged

    @action_form(
        title="Rendre la visualisation",
        description="Prepare les donnees et la configuration pour le frontend.",
        submit_label="Executer",
        fields={
            "quick": {"label": "Recherche rapide", "type": "text"},
            "limit": {"label": "Limite", "type": "number"},
            "filters": {"label": "Filtres runtime", "type": "json"},
            "spec": {
                "label": "Spec BI (optionnel)",
                "type": "json",
                "help_text": "Permet de surcharger dimensions/mesures/pivot/having sans modifier la visualisation.",
            },
        },
    )
    def render(
        self,
        context: Any = None,
        quick: str = "",
        limit: Any = 200,
        filters: Optional[dict] = None,
        spec: Optional[dict] = None,
    ) -> dict:
        engine = self.dataset.build_engine(context=context)
        merged_filters = self._merge_filters(filters)
        coerced_limit = _coerce_int(limit, default=self.dataset.preview_limit)
        base_spec = {}
        if isinstance(self.config, dict) and isinstance(self.config.get("query"), dict):
            base_spec = dict(self.config.get("query") or {})
        if isinstance(spec, dict):
            base_spec.update(spec)

        runtime_filters_payload = [item.__dict__ for item in merged_filters]
        existing_where = (
            base_spec.get("filters")
            if "filters" in base_spec
            else base_spec.get("where")
        )
        if existing_where and runtime_filters_payload:
            base_spec["filters"] = {
                "op": "and",
                "items": [existing_where, runtime_filters_payload],
            }
        elif runtime_filters_payload:
            base_spec["filters"] = runtime_filters_payload

        base_spec["quick"] = quick
        base_spec["limit"] = coerced_limit or self.dataset.preview_limit
        payload = engine.run_query(base_spec)
        return {
            "visualization": {
                "id": self.id,
                "code": self.code,
                "title": self.title,
                "kind": self.kind,
                "config": self.config,
                "options": self.options,
                "dataset_id": self.dataset_id,
            },
            "dataset": payload,
        }


__all__ = ["ReportingVisualization"]

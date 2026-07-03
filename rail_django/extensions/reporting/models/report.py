"""
ReportingReport and ReportingReportBlock models for the BI reporting module.

This module contains the report container model that aggregates multiple
visualizations and the through table for layout management.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from django.conf import settings
from django.db import models
from graphql import GraphQLError

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.core.decorators import action_form

from ..security import (
    _reporting_roles,
    _reporting_operations,
    report_is_visible_to_user,
)

if TYPE_CHECKING:
    from .visualization import ReportingVisualization


class ReportingReport(models.Model):
    """Report container aggregating multiple visualizations."""

    class Origin(models.TextChoices):
        CATALOG = "catalog", "Catalogue"
        STUDIO = "studio", "Studio"

    code = models.SlugField(unique=True, max_length=80, verbose_name="Code")
    title = models.CharField(max_length=140, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    layout = models.JSONField(
        default=list,
        verbose_name="Layout",
        help_text="Disposition des visualisations {visualization_id, position}.",
    )
    filters = models.JSONField(
        default=list,
        verbose_name="Filtres applicables",
        help_text="Filtres globaux appliques a toutes les visualisations.",
    )
    theme = models.CharField(
        max_length=60, default="light", verbose_name="Theme", blank=True
    )
    allowed_roles = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Roles autorises",
        help_text="Roles autorises a consulter ce rapport.",
    )
    origin = models.CharField(
        max_length=20,
        choices=Origin.choices,
        default=Origin.CATALOG,
        verbose_name="Origine",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_reporting_reports",
        verbose_name="Cree par",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_reporting_reports",
        verbose_name="Modifie par",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mise a jour")
    visualizations = models.ManyToManyField(
        "ReportingVisualization",
        through="ReportingReportBlock",
        related_name="reports",
        verbose_name="Visualisations",
    )

    class Meta:
        app_label = "rail_django"
        verbose_name = "Rapport BI"
        verbose_name_plural = "Rapports BI"
        ordering = ["title"]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["code", "title", "description"],
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "title", "code", "created_at"],
            default=["title"],
        )
        fields = GraphQLMetaBase.Fields(
            read_only=["created_at", "updated_at", "origin", "created_by", "updated_by"]
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
        method_mutations = ["build_payload"]

    @staticmethod
    def resolve_visible_queryset(queryset, info, **kwargs):
        user = getattr(getattr(info, "context", None), "user", None)
        reports = queryset.prefetch_related("blocks__visualization__dataset")
        visible_ids = [report.pk for report in reports if report_is_visible_to_user(report, user)]
        return queryset.filter(pk__in=visible_ids)

    def __str__(self) -> str:
        return f"{self.title} ({self.code})"

    def _resolved_blocks(self) -> list["ReportingReportBlock"]:
        return list(
            self.blocks.select_related("visualization", "visualization__dataset")
        )

    def _render_visualizations(
        self, context: Any, quick: str, limit: int, filters: Optional[dict]
    ) -> list[dict]:
        rendered: list[dict] = []
        for block in self._resolved_blocks():
            dataset_code = block.visualization.dataset.code
            payload = block.visualization.render(
                context=context,
                quick=quick,
                limit=limit,
                filters={"filters": self.normalize_filters(filters, dataset_code)},
            )
            if block.title_override:
                payload["visualization"]["title"] = block.title_override
            rendered.append(
                {
                    "block_id": block.id,
                    "visualization": payload["visualization"],
                    "dataset": payload["dataset"],
                    "layout": block.layout,
                }
            )
        return rendered

    def normalize_filters(
        self, values: Optional[dict], dataset_code: str
    ) -> list[dict[str, Any]]:
        """Map allowlisted report values to one dataset's field contract."""
        if not values:
            return []
        if not isinstance(values, dict):
            raise GraphQLError("Les filtres du rapport doivent etre un objet.")
        definitions = {
            item.get("name"): item
            for item in (self.filters or [])
            if isinstance(item, dict) and item.get("name")
        }
        unknown = set(values) - set(definitions)
        if unknown:
            raise GraphQLError(
                f"Filtres inconnus: {', '.join(sorted(unknown))}."
            )
        normalized = []
        for name, value in values.items():
            if value in (None, "", []):
                continue
            definition = definitions[name]
            targets = definition.get("targets") or []
            target = next(
                (
                    item
                    for item in targets
                    if item.get("datasetCode", item.get("dataset_code"))
                    == dataset_code
                ),
                None,
            )
            if targets and not target:
                continue
            field = (target or {}).get("field") or definition.get("field")
            if not field:
                raise GraphQLError(f"Le filtre {name} ne declare aucun champ.")
            normalized.append(
                {
                    "field": field,
                    "lookup": (target or {}).get("lookup")
                    or definition.get("lookup", "exact"),
                    "value": value,
                }
            )
        return normalized

    @action_form(
        title="Assembler le rapport",
        description="Retourne toutes les visualisations et le layout pour un rendu unique.",
        submit_label="Construire",
        fields={
            "quick": {"label": "Recherche rapide", "type": "text"},
            "limit": {"label": "Limite par visualisation", "type": "number"},
            "filters": {"label": "Filtres globaux", "type": "json"},
        },
    )
    def build_payload(
        self,
        context: Any = None,
        quick: str = "",
        limit: int = 200,
        filters: Optional[dict] = None,
    ) -> dict:
        visualizations = self._render_visualizations(
            context=context, quick=quick, limit=limit, filters=filters
        )
        return {
            "report": {
                "code": self.code,
                "title": self.title,
                "description": self.description,
                "layout": self.layout,
                "theme": self.theme,
            },
            "visualizations": visualizations,
            "filters": self.filters,
        }


class ReportingReportBlock(models.Model):
    """Through table used to assign visualizations to a report with layout hints."""

    report = models.ForeignKey(
        ReportingReport,
        related_name="blocks",
        on_delete=models.CASCADE,
        verbose_name="Rapport",
    )
    visualization = models.ForeignKey(
        "ReportingVisualization",
        related_name="blocks",
        on_delete=models.CASCADE,
        verbose_name="Visualisation",
    )
    position = models.PositiveIntegerField(default=1, verbose_name="Position")
    layout = models.JSONField(
        default=dict,
        verbose_name="Layout",
        help_text="Coordonnees (x,y,width,height) pour le frontend.",
    )
    title_override = models.CharField(
        max_length=140, blank=True, verbose_name="Titre alternatif"
    )

    class Meta:
        app_label = "rail_django"
        verbose_name = "Bloc de rapport"
        verbose_name_plural = "Blocs de rapport"
        ordering = ["position"]
        unique_together = (("report", "visualization"),)

    class GraphQLMeta(GraphQLMetaBase):
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "position"],
            default=["position"],
        )

    def __str__(self) -> str:
        return f"{self.report.code} -> {self.visualization.code}"


__all__ = ["ReportingReport", "ReportingReportBlock"]

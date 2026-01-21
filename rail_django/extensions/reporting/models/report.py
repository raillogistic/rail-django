"""
ReportingReport and ReportingReportBlock models for the BI reporting module.

This module contains the report container model that aggregates multiple
visualizations and the through table for layout management.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from django.db import models

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.decorators import action_form

from ..security import _reporting_roles, _reporting_operations

if TYPE_CHECKING:
    from .visualization import ReportingVisualization


class ReportingReport(models.Model):
    """Report container aggregating multiple visualizations."""

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
        fields = GraphQLMetaBase.Fields(read_only=["created_at", "updated_at"])
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.code})"

    def _resolved_blocks(self) -> list["ReportingReportBlock"]:
        return list(
            self.blocks.select_related("visualization", "visualization__dataset")
        )

    def _render_visualizations(
        self, quick: str, limit: int, filters: Optional[dict]
    ) -> list[dict]:
        rendered: list[dict] = []
        for block in self._resolved_blocks():
            payload = block.visualization.render(
                quick=quick,
                limit=limit,
                filters=filters,
            )
            rendered.append(
                {
                    "block_id": block.id,
                    "visualization": payload["visualization"],
                    "dataset": payload["dataset"],
                    "layout": block.layout,
                }
            )
        return rendered

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
        quick: str = "",
        limit: int = 200,
        filters: Optional[dict] = None,
    ) -> dict:
        visualizations = self._render_visualizations(
            quick=quick, limit=limit, filters=filters
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

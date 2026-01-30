"""
ReportingExportJob model for the BI reporting module.

This module contains the export job model which tracks export runs
(PDF/CSV/JSON) for datasets, visualizations or full reports.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.core.decorators import confirm_action

from ..types import ReportingError
from ..security import _reporting_roles, _reporting_operations


class ReportingExportJob(models.Model):
    """Tracks export runs (PDF/CSV/JSON) for datasets, visualizations or full reports."""

    class ExportStatus(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        COMPLETED = "completed", "Termine"
        FAILED = "failed", "Echec"

    class ExportFormat(models.TextChoices):
        PDF = "pdf", "PDF"
        CSV = "csv", "CSV"
        JSON = "json", "JSON"
        XLSX = "xlsx", "Excel"

    title = models.CharField(max_length=140, verbose_name="Titre")
    dataset = models.ForeignKey(
        "ReportingDataset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="export_jobs",
        verbose_name="Dataset",
    )
    visualization = models.ForeignKey(
        "ReportingVisualization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="export_jobs",
        verbose_name="Visualisation",
    )
    report = models.ForeignKey(
        "ReportingReport",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="export_jobs",
        verbose_name="Rapport",
    )
    format = models.CharField(
        max_length=10,
        choices=ExportFormat.choices,
        default=ExportFormat.PDF,
        verbose_name="Format",
    )
    status = models.CharField(
        max_length=20,
        choices=ExportStatus.choices,
        default=ExportStatus.PENDING,
        verbose_name="Statut",
    )
    filters = models.JSONField(
        default=dict,
        verbose_name="Filtres",
        help_text="Filtres appliques lors de l export.",
    )
    payload = models.JSONField(
        default=dict,
        verbose_name="Payload",
        help_text="Snapshot utilise par le frontend (donnees et layout).",
    )
    error_message = models.TextField(blank=True, verbose_name="Erreur")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Debut")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Fin")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")

    class Meta:
        app_label = "rail_django"
        verbose_name = "Export BI"
        verbose_name_plural = "Exports BI"
        ordering = ["-created_at"]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["title", "status", "format"],
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "created_at", "status", "title"],
            default=["-created_at"],
        )
        fields = GraphQLMetaBase.Fields(read_only=["started_at", "finished_at"])
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.format})"

    def _build_payload(self) -> dict:
        if self.report:
            return self.report.build_payload(quick="", limit=500, filters=self.filters)
        if self.visualization:
            return self.visualization.render(quick="", limit=500, filters=self.filters)
        if self.dataset:
            return self.dataset.preview(
                quick="",
                limit=self.dataset.preview_limit,
                ordering="",
                filters=self.filters,
            )
        raise ReportingError("Aucune cible d export n est renseignee.")

    @confirm_action(
        title="Lancer l export",
        message="Prepare un payload pour PDF/CSV/JSON.",
        confirm_label="Lancer",
        severity="primary",
    )
    def run_export(self) -> bool:
        self.status = self.ExportStatus.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])
        try:
            self.payload = self._build_payload()
            self.status = self.ExportStatus.COMPLETED
            self.finished_at = timezone.now()
            self.save(update_fields=["payload", "status", "finished_at"])
            return True
        except Exception as exc:  # pragma: no cover - defensive
            self.status = self.ExportStatus.FAILED
            self.error_message = str(exc)
            self.finished_at = timezone.now()
            self.save(
                update_fields=["status", "error_message", "finished_at", "payload"]
            )
            return False


__all__ = ["ReportingExportJob"]

"""
ReportingExportJob model for the BI reporting module.

This module contains the export job model which tracks export runs
(PDF/CSV/JSON/XLSX) for datasets, visualizations or full reports.
Uses the pluggable renderer system for real file generation.

Attributes:
    ReportingExportJob: Model tracking export runs with file generation.
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.core.decorators import confirm_action

from ..types import ReportingError, ReportingExecutionContext
from ..security import _reporting_export_operations, _reporting_roles


class ReportingExportJob(models.Model):
    """
    Tracks export runs (PDF/CSV/JSON/XLSX) for datasets, visualizations or reports.

    Uses the pluggable renderer registry to generate real files instead of
    just storing JSON snapshots.

    Attributes:
        title: Titre descriptif de l'export.
        dataset: Référence optionnelle au dataset source.
        visualization: Référence optionnelle à la visualisation source.
        report: Référence optionnelle au rapport source.
        format: Format d'export (pdf, csv, json, xlsx).
        status: Statut de l'export (pending, running, completed, failed).
        filters: Filtres appliqués lors de l'export.
        payload: Snapshot des données brutes (JSON).
        file: Fichier généré par le renderer.
        file_size: Taille du fichier en octets.
        render_options: Options passées au renderer.
        error_message: Message d'erreur en cas d'échec.
        started_at: Horodatage de début d'exécution.
        finished_at: Horodatage de fin d'exécution.
        created_at: Horodatage de création.
    """

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
    file = models.FileField(
        upload_to="reporting/exports/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Fichier exporte",
        help_text="Fichier genere par le renderer (CSV, XLSX, PDF, JSON).",
    )
    file_size = models.PositiveIntegerField(
        default=0,
        verbose_name="Taille du fichier",
        help_text="Taille du fichier en octets.",
    )
    render_options = models.JSONField(
        default=dict,
        verbose_name="Options de rendu",
        help_text="Options passees au renderer (delimiter, encoding, orientation...).",
    )
    error_message = models.TextField(blank=True, verbose_name="Erreur")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reporting_export_jobs",
        verbose_name="Demandeur",
    )
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
        fields = GraphQLMetaBase.Fields(
            read_only=[
                "status",
                "payload",
                "file",
                "file_size",
                "error_message",
                "requested_by",
                "started_at",
                "finished_at",
            ],
        )
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_export_operations(),
        )
        resolvers = GraphQLMetaBase.Resolvers(
            queries={
                "list": "resolve_visible_queryset",
                "retrieve": "resolve_visible_queryset",
            }
        )
        method_mutations = ["run_export"]

    def __str__(self) -> str:
        return f"{self.title} ({self.format})"

    @staticmethod
    def resolve_visible_queryset(queryset, info, **kwargs):
        user = getattr(getattr(info, "context", None), "user", None)
        if getattr(user, "is_superuser", False):
            return queryset
        if not user or not getattr(user, "is_authenticated", False):
            return queryset.none()
        return queryset.filter(requested_by=user)

    def _build_payload(self) -> dict:
        """
        Build the data payload from the linked source (report, visualization, or dataset).

        Returns:
            Dictionary containing rows and metadata.

        Raises:
            ReportingError: If no export target is configured.
        """
        context = ReportingExecutionContext(user=self.requested_by) if self.requested_by else None

        if self.report:
            if self.format in {self.ExportFormat.CSV, self.ExportFormat.XLSX}:
                blocks = list(
                    self.report.blocks.select_related(
                        "visualization", "visualization__dataset"
                    )
                )
                if not blocks:
                    raise ReportingError("Ce rapport ne contient aucune visualisation.")
                block = next(
                    (
                        item
                        for item in blocks
                        if item.visualization.kind in {"table", "records"}
                    ),
                    blocks[0],
                )
                return block.visualization.render(
                    context=context,
                    filters={
                        "filters": self.report.normalize_filters(
                            self.filters, block.visualization.dataset.code
                        )
                    },
                    limit=10_000,
                )["dataset"]
            return self.report.build_payload(context=context, quick="", limit=500, filters=self.filters)
        if self.visualization:
            return self.visualization.render(context=context, quick="", limit=500, filters=self.filters)
        if self.dataset:
            return self.dataset.preview(
                context=context,
                quick="",
                limit=self.dataset.preview_limit,
                ordering="",
                filters=self.filters,
            )
        raise ReportingError("Aucune cible d export n est renseignee.")

    def _render_file(self, payload: dict) -> tuple[bytes, str]:
        """
        Render the payload to a file using the appropriate renderer.

        Args:
            payload: Data payload to render.

        Returns:
            Tuple of (file_bytes, filename).

        Raises:
            ReportingError: If the format is not supported.
        """
        from ..renderers import get_renderer

        try:
            renderer = get_renderer(self.format)
        except ValueError as exc:
            raise ReportingError(str(exc)) from exc

        options = dict(self.render_options or {})
        # Inject metadata into options for renderers that support it
        if "title" not in options:
            options["title"] = self.title

        file_bytes = renderer.render(payload, options=options)
        base_name = f"export_{self.pk or 'draft'}"
        filename = renderer.get_filename(base_name)
        return file_bytes, filename

    @confirm_action(
        title="Lancer l export",
        message="Prepare et genere un fichier pour PDF/CSV/JSON/XLSX.",
        confirm_label="Lancer",
        severity="primary",
    )
    def run_export(self, context=None) -> bool:
        """
        Execute the export: build payload, render file, and save results.

        Returns:
            ``True`` if export succeeded, ``False`` otherwise.
        """
        if not self.requested_by_id:
            raise ReportingError("Le demandeur de l export est obligatoire.")
        user = getattr(context, "user", None)
        if not getattr(user, "is_superuser", False) and self.requested_by_id != getattr(
            user, "pk", None
        ):
            raise ReportingError("Vous n etes pas autorise a executer cet export.")

        self.status = self.ExportStatus.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])
        try:
            # Build the data payload
            self.payload = self._build_payload()

            # Render to file using the appropriate renderer
            file_bytes, filename = self._render_file(self.payload)

            # Save the generated file
            self.file.save(filename, ContentFile(file_bytes), save=False)
            self.file_size = len(file_bytes)

            self.status = self.ExportStatus.COMPLETED
            self.finished_at = timezone.now()
            self.save(update_fields=[
                "payload", "status", "finished_at",
                "file", "file_size",
            ])
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

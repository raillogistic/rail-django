"""
ReportingSchedule model for the BI reporting module.

Provides scheduled materialization, export, and conditional alerting
for reporting datasets. Designed to be driven by a management command
or Celery beat.

Attributes:
    ReportingSchedule: Model for scheduled reporting actions.
"""

from __future__ import annotations

from typing import Any, Optional

from django.db import models
from django.utils import timezone

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.core.decorators import action_form, confirm_action

from ..types import ReportingError
from ..security import _reporting_roles, _reporting_operations


class ReportingSchedule(models.Model):
    """
    Planification de matérialisation, d'export ou d'alerte sur un dataset.

    Chaque schedule est associé à un dataset et déclenché selon une expression
    cron. Les actions possibles sont:
    - ``materialize``: Capture un snapshot du dataset.
    - ``export``: Génère un fichier d'export automatique.
    - ``alert``: Vérifie une condition sur une métrique et notifie si déclenchée.

    Attributes:
        dataset: Référence au dataset cible.
        title: Titre descriptif du schedule.
        cron_expression: Expression cron à 5 champs.
        action: Type d'action à exécuter.
        export_format: Format d'export (si action=export).
        alert_condition: Condition d'alerte JSON.
        notification_targets: Cibles de notification (emails, webhooks).
        query_spec: Spec de requête utilisée pour l'exécution.
        is_active: Indique si le schedule est actif.
        last_run_at: Horodatage de la dernière exécution.
        last_run_status: Statut de la dernière exécution.
        last_run_message: Message de la dernière exécution.
        run_count: Nombre total d'exécutions.
        created_at: Horodatage de création.
        updated_at: Horodatage de mise à jour.
    """

    class ScheduleAction(models.TextChoices):
        MATERIALIZE = "materialize", "Materialiser"
        EXPORT = "export", "Exporter"
        ALERT = "alert", "Alerte conditionnelle"

    class RunStatus(models.TextChoices):
        SUCCESS = "success", "Succes"
        FAILED = "failed", "Echec"
        SKIPPED = "skipped", "Ignore (condition non remplie)"
        NEVER = "never", "Jamais execute"

    dataset = models.ForeignKey(
        "ReportingDataset",
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name="Dataset",
    )
    title = models.CharField(
        max_length=140,
        verbose_name="Titre",
    )
    cron_expression = models.CharField(
        max_length=60,
        verbose_name="Expression cron",
        help_text="Expression cron a 5 champs (ex: '0 8 * * *' pour tous les jours a 8h).",
    )
    action = models.CharField(
        max_length=20,
        choices=ScheduleAction.choices,
        default=ScheduleAction.MATERIALIZE,
        verbose_name="Action",
    )
    export_format = models.CharField(
        max_length=10,
        blank=True,
        default="csv",
        verbose_name="Format d export",
        help_text="Format de fichier si action=export (csv, json, xlsx, pdf).",
    )
    alert_condition = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Condition d alerte",
        help_text="Condition JSON: {metric, op, threshold}. Ex: {\"metric\": \"total\", \"op\": \">\", \"threshold\": 1000}.",
    )
    notification_targets = models.JSONField(
        default=list,
        verbose_name="Cibles de notification",
        help_text="Liste d'emails ou webhooks pour les alertes.",
    )
    query_spec = models.JSONField(
        default=dict,
        verbose_name="Spec de requete",
        help_text="Spec JSON passee a run_query() lors de l execution.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Actif",
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Derniere execution",
    )
    last_run_status = models.CharField(
        max_length=20,
        choices=RunStatus.choices,
        default=RunStatus.NEVER,
        verbose_name="Statut derniere execution",
    )
    last_run_message = models.TextField(
        blank=True,
        verbose_name="Message derniere execution",
    )
    run_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre d executions",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creation",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Mise a jour",
    )

    class Meta:
        app_label = "rail_django"
        verbose_name = "Planification BI"
        verbose_name_plural = "Planifications BI"
        ordering = ["dataset__title", "title"]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["title", "action"],
            fields={
                "dataset_id": GraphQLMetaBase.FilterField(lookups=["exact"]),
                "action": GraphQLMetaBase.FilterField(lookups=["exact"]),
                "is_active": GraphQLMetaBase.FilterField(lookups=["exact"]),
            },
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "title", "last_run_at", "created_at"],
            default=["title"],
        )
        fields = GraphQLMetaBase.Fields(
            read_only=["last_run_at", "last_run_status", "last_run_message", "run_count"],
        )
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.action} - {self.cron_expression})"

    def _evaluate_alert_condition(self, result: dict) -> bool:
        """
        Evaluate the alert condition against the query result.

        Args:
            result: Query result dictionary containing ``rows``.

        Returns:
            ``True`` if the condition is met and alert should fire.
        """
        condition = self.alert_condition
        if not condition or not isinstance(condition, dict):
            return False

        metric_name = condition.get("metric", "")
        op = condition.get("op", ">")
        threshold = condition.get("threshold", 0)

        rows = result.get("rows") or []
        if not rows:
            return False

        # Aggregate the metric across all rows
        values = [row.get(metric_name) for row in rows if row.get(metric_name) is not None]
        if not values:
            return False

        # Use the first row's value for single-row results, sum for multi-row
        actual = values[0] if len(values) == 1 else sum(v for v in values if isinstance(v, (int, float)))

        ops = {
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        comparator = ops.get(op)
        if not comparator:
            return False

        try:
            return comparator(float(actual), float(threshold))
        except (TypeError, ValueError):
            return False

    @confirm_action(
        title="Executer maintenant",
        message="Execute le schedule immediatement sans attendre le cron.",
        confirm_label="Executer",
        severity="primary",
    )
    def run_now(self) -> dict:
        """
        Execute the schedule action immediately.

        Returns:
            Dictionary with execution result details.
        """
        try:
            if self.action == self.ScheduleAction.MATERIALIZE:
                result = self._run_materialize()
            elif self.action == self.ScheduleAction.EXPORT:
                result = self._run_export()
            elif self.action == self.ScheduleAction.ALERT:
                result = self._run_alert()
            else:
                raise ReportingError(f"Action inconnue: {self.action}")

            self.last_run_at = timezone.now()
            self.last_run_status = self.RunStatus.SUCCESS
            self.last_run_message = result.get("message", "OK")
            self.run_count += 1
            self.save(update_fields=[
                "last_run_at", "last_run_status", "last_run_message",
                "run_count", "updated_at",
            ])
            return result
        except Exception as exc:
            self.last_run_at = timezone.now()
            self.last_run_status = self.RunStatus.FAILED
            self.last_run_message = str(exc)
            self.run_count += 1
            self.save(update_fields=[
                "last_run_at", "last_run_status", "last_run_message",
                "run_count", "updated_at",
            ])
            return {"success": False, "message": str(exc)}

    def _run_materialize(self) -> dict:
        """Execute the materialize action on the dataset."""
        self.dataset.materialize()
        return {
            "success": True,
            "message": f"Dataset '{self.dataset.code}' materialise.",
            "action": "materialize",
        }

    def _run_export(self) -> dict:
        """Create and execute an export job for the dataset."""
        from .export_job import ReportingExportJob

        job = ReportingExportJob.objects.create(
            title=f"Export planifie - {self.title}",
            dataset=self.dataset,
            format=self.export_format or "csv",
            filters=self.query_spec.get("filters", {}),
        )
        job.run_export()
        return {
            "success": job.status == ReportingExportJob.ExportStatus.COMPLETED,
            "message": f"Export {job.format} cree (job #{job.pk}).",
            "action": "export",
            "export_job_id": job.pk,
        }

    def _run_alert(self) -> dict:
        """Evaluate the alert condition and return the result."""
        engine = self.dataset.build_engine()
        result = engine.run_query(self.query_spec or {})

        triggered = self._evaluate_alert_condition(result)
        if not triggered:
            self.last_run_status = self.RunStatus.SKIPPED
            return {
                "success": True,
                "triggered": False,
                "message": "Condition non remplie, alerte non declenchee.",
                "action": "alert",
            }

        return {
            "success": True,
            "triggered": True,
            "message": f"Alerte declenchee pour '{self.dataset.code}'.",
            "action": "alert",
            "condition": self.alert_condition,
            "notification_targets": self.notification_targets,
        }


__all__ = ["ReportingSchedule"]

"""Staging models for template-driven import lifecycle."""

from __future__ import annotations

import uuid

from django.db import models


class ImportFileFormat(models.TextChoices):
    CSV = "CSV", "CSV"
    XLSX = "XLSX", "XLSX"


class ImportIssueSeverity(models.TextChoices):
    ERROR = "ERROR", "Error"
    WARNING = "WARNING", "Warning"


class ImportBatchStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded"
    PARSED = "PARSED", "Parsed"
    REVIEWING = "REVIEWING", "Reviewing"
    VALIDATION_FAILED = "VALIDATION_FAILED", "Validation Failed"
    VALIDATED = "VALIDATED", "Validated"
    SIMULATION_FAILED = "SIMULATION_FAILED", "Simulation Failed"
    SIMULATED = "SIMULATED", "Simulated"
    COMMITTED = "COMMITTED", "Committed"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"
    EXPIRED = "EXPIRED", "Expired"


class ImportRowAction(models.TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"


class ImportRowStatus(models.TextChoices):
    VALID = "VALID", "Valid"
    INVALID = "INVALID", "Invalid"
    READY = "READY", "Ready"
    LOCKED = "LOCKED", "Locked"
    COMMITTED = "COMMITTED", "Committed"


class ImportIssueStage(models.TextChoices):
    PARSE = "PARSE", "Parse"
    EDIT = "EDIT", "Edit"
    VALIDATE = "VALIDATE", "Validate"
    SIMULATE = "SIMULATE", "Simulate"
    COMMIT = "COMMIT", "Commit"


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app_label = models.CharField(max_length=100)
    model_name = models.CharField(max_length=120)
    template_id = models.CharField(max_length=120)
    template_version = models.CharField(max_length=64)
    status = models.CharField(
        max_length=32,
        choices=ImportBatchStatus.choices,
        default=ImportBatchStatus.UPLOADED,
    )
    uploaded_by_user_id = models.CharField(max_length=128)
    file_name = models.CharField(max_length=255)
    file_format = models.CharField(max_length=10, choices=ImportFileFormat.choices)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    create_rows = models.PositiveIntegerField(default=0)
    update_rows = models.PositiveIntegerField(default=0)
    committed_rows = models.PositiveIntegerField(default=0)
    error_report_path = models.CharField(max_length=1024, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "rail_django"
        db_table = "rail_django_import_batch"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["app_label", "model_name"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["uploaded_by_user_id", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.app_label}.{self.model_name} [{self.id}]"


class ImportRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_number = models.PositiveIntegerField()
    source_values = models.JSONField(default=dict)
    edited_values = models.JSONField(default=dict)
    normalized_values = models.JSONField(null=True, blank=True)
    matching_key = models.CharField(max_length=255, null=True, blank=True)
    action = models.CharField(max_length=10, choices=ImportRowAction.choices)
    target_record_id = models.CharField(max_length=128, null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=ImportRowStatus.choices,
        default=ImportRowStatus.INVALID,
    )
    issue_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "rail_django"
        db_table = "rail_django_import_row"
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"],
                name="rail_django_import_row_unique_batch_row",
            )
        ]
        indexes = [
            models.Index(fields=["batch", "status"]),
            models.Index(fields=["batch", "matching_key"]),
        ]

    def __str__(self) -> str:
        return f"Batch {self.batch_id} Row {self.row_number}"


class ImportIssue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="issues",
    )
    row = models.ForeignKey(
        ImportRow,
        on_delete=models.CASCADE,
        related_name="issues",
        null=True,
        blank=True,
    )
    row_number = models.PositiveIntegerField(null=True, blank=True)
    field_path = models.CharField(max_length=255, null=True, blank=True)
    code = models.CharField(max_length=100)
    severity = models.CharField(
        max_length=10,
        choices=ImportIssueSeverity.choices,
        default=ImportIssueSeverity.ERROR,
    )
    message = models.TextField()
    suggested_fix = models.TextField(null=True, blank=True)
    stage = models.CharField(max_length=16, choices=ImportIssueStage.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "rail_django"
        db_table = "rail_django_import_issue"
        ordering = ["row_number", "created_at"]
        indexes = [
            models.Index(fields=["batch", "severity"]),
            models.Index(fields=["batch", "stage"]),
            models.Index(fields=["batch", "row_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.severity})"


class ImportSimulationSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="simulation_snapshots",
    )
    can_commit = models.BooleanField(default=False)
    would_create = models.PositiveIntegerField(default=0)
    would_update = models.PositiveIntegerField(default=0)
    blocking_errors = models.PositiveIntegerField(default=0)
    warnings = models.PositiveIntegerField(default=0)
    executed_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "rail_django"
        db_table = "rail_django_import_simulation_snapshot"
        ordering = ["-executed_at"]
        indexes = [
            models.Index(fields=["batch", "executed_at"]),
        ]

    def __str__(self) -> str:
        return f"Simulation {self.id} for batch {self.batch_id}"


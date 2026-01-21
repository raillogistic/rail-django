"""
Task execution models.
"""

import uuid
from django.db import models


class TaskStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    RETRYING = "RETRYING", "Retrying"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    CANCELED = "CANCELED", "Canceled"


class TaskExecution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING
    )
    progress = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    result_reference = models.CharField(max_length=255, null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    owner_id = models.CharField(max_length=64, null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_retries = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "rail_django"
        verbose_name = "Task Execution"
        verbose_name_plural = "Task Executions"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"

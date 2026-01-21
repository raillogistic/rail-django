"""
Audit event database models.
"""

from django.db import models


class AuditEventModel(models.Model):
    """Persisted audit event for database storage."""

    event_type = models.CharField(max_length=64, db_index=True)
    severity = models.CharField(max_length=32)
    user_id = models.IntegerField(null=True, blank=True)
    username = models.CharField(max_length=150, null=True, blank=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    request_path = models.TextField(null=True, blank=True)
    request_method = models.CharField(max_length=16, null=True, blank=True)
    additional_data = models.JSONField(null=True, blank=True, default=dict)
    session_id = models.CharField(max_length=128, null=True, blank=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        app_label = "rail_django"
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.timestamp.isoformat()}"


def get_audit_event_model():
    """Return the audit model used for database storage."""
    return AuditEventModel

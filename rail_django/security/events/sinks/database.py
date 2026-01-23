import logging
from typing import TYPE_CHECKING
from .base import EventSink

if TYPE_CHECKING:
    from ..types import SecurityEvent

logger = logging.getLogger(__name__)


class DatabaseSink(EventSink):
    """Writes events to the AuditEventModel."""

    def __init__(self, batch_size: int = 1):
        self.batch_size = batch_size
        self._buffer: list = []

    def write(self, event: "SecurityEvent") -> None:
        from rail_django.extensions.audit.models import get_audit_event_model

        try:
            AuditEvent = get_audit_event_model()
            AuditEvent.objects.create(
                event_type=event.event_type.value,
                severity=event.severity.value,
                user_id=event.user_id,
                username=event.username,
                client_ip=event.client_ip,
                user_agent=event.user_agent[:500] if event.user_agent else None,
                timestamp=event.timestamp,
                request_path=event.request_path,
                request_method=event.request_method,
                additional_data={
                    "correlation_id": event.correlation_id,
                    "outcome": event.outcome.value,
                    "action": event.action,
                    "resource": event.resource.to_dict() if event.resource else None,
                    "operation_name": event.operation_name,
                    "operation_type": event.operation_type,
                    "schema_name": event.schema_name,
                    "context": event.context,
                    "risk_score": event.risk_score,
                },
                session_id=event.session_id,
                success=event.outcome.value == "success",
                error_message=event.error_message,
            )
        except Exception as e:
            logger.error(f"Failed to write event to database: {e}")

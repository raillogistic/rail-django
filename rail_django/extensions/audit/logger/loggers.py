"""
Global logger instance and convenience logging functions.
"""

from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from django.http import HttpRequest

from .base import AuditLogger
from ..types import AuditEvent, AuditEventType, AuditSeverity

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

# Global audit logger instance
audit_logger = AuditLogger()


def log_audit_event(
    request: Optional[HttpRequest],
    event_type: AuditEventType,
    *,
    severity: Optional[AuditSeverity] = None,
    user: Optional["AbstractUser"] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    additional_data: Optional[dict[str, Any]] = None,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
) -> None:
    """Log a generic audit event with standard request metadata."""
    if not audit_logger.enabled:
        return

    resolved_event_type = event_type
    if isinstance(event_type, str):
        try:
            resolved_event_type = AuditEventType(event_type)
        except ValueError:
            resolved_event_type = AuditEventType.DATA_ACCESS

    if severity is None:
        if resolved_event_type in (
            AuditEventType.CREATE,
            AuditEventType.UPDATE,
            AuditEventType.DELETE,
        ):
            severity = AuditSeverity.MEDIUM
        else:
            severity = AuditSeverity.LOW

    if user is None and request is not None:
        user = getattr(request, "user", None)

    user_id = None
    username = None
    if user and getattr(user, "is_authenticated", False):
        user_id = getattr(user, "id", None)
        if hasattr(user, "get_username"):
            username = user.get_username()
        else:
            username = getattr(user, "username", None)

    client_ip = audit_logger._get_client_ip(request) if request is not None else "Unknown"
    user_agent = (
        request.META.get("HTTP_USER_AGENT", "Unknown") if request is not None else "Unknown"
    )
    resolved_path = request_path or (request.path if request is not None else "")
    resolved_method = request_method or (request.method if request is not None else "SYSTEM")
    session_id = (
        request.session.session_key
        if request is not None and hasattr(request, "session")
        else None
    )

    event = AuditEvent(
        event_type=resolved_event_type,
        severity=severity,
        user_id=user_id,
        username=username,
        client_ip=client_ip,
        user_agent=user_agent,
        timestamp=datetime.now(timezone.utc),
        request_path=resolved_path,
        request_method=resolved_method,
        additional_data=additional_data,
        session_id=session_id,
        success=success,
        error_message=error_message,
    )

    audit_logger.log_event(event)


def log_authentication_event(
    request: HttpRequest,
    user: Optional["AbstractUser"],
    event_type: str,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """
    Fonction utilitaire pour enregistrer un événement d'authentification.
    """
    if event_type == "login":
        audit_logger.log_login_attempt(request, user, success, error_message)
    elif event_type == "logout":
        if user:
            audit_logger.log_logout(request, user)
    elif event_type in ["token_refresh", "token_invalid"]:
        token_event_type = (
            AuditEventType.TOKEN_REFRESH
            if event_type == "token_refresh"
            else AuditEventType.TOKEN_INVALID
        )
        audit_logger.log_token_event(
            request, user, token_event_type, success, error_message
        )

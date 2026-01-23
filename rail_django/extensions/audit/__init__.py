"""
Audit extension - provides AuditEventModel for storing security events.

For logging events, use the security API:

    from rail_django.security import security, EventType
    security.emit(EventType.AUTH_LOGIN_SUCCESS, request=request)
"""

from .models import AuditEventModel, get_audit_event_model
from .graphql import LogFrontendAuditMutation

__all__ = ["AuditEventModel", "get_audit_event_model", "LogFrontendAuditMutation"]

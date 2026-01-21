"""
Audit package for Django GraphQL Auto-Generation.

This package provides a comprehensive audit system for authentication,
security events, and UI actions.
"""

from .graphql import FrontendAuditEventInput, LogFrontendAuditMutation
from .logger import (
    AuditLogger,
    audit_logger,
    get_security_dashboard_data,
    log_audit_event,
    log_authentication_event,
)
from .models import AuditEventModel, get_audit_event_model
from .types import AuditEvent, AuditEventType, AuditSeverity

__all__ = [
    # Types
    "AuditEvent",
    "AuditEventType",
    "AuditSeverity",
    # Logger
    "AuditLogger",
    "audit_logger",
    "log_audit_event",
    "log_authentication_event",
    "get_security_dashboard_data",
    # Models
    "AuditEventModel",
    "get_audit_event_model",
    # GraphQL
    "FrontendAuditEventInput",
    "LogFrontendAuditMutation",
]

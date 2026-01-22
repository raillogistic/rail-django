"""
Audit Logger package.

This package provides the audit logging functionality for Rail Django.
It is split into multiple modules for better maintainability.
"""

from .base import AuditLogger
from .loggers import (
    log_audit_event,
    log_authentication_event,
    audit_logger,
)
from .utils import get_security_dashboard_data

__all__ = [
    "AuditLogger",
    "log_audit_event",
    "log_authentication_event",
    "audit_logger",
    "get_security_dashboard_data",
]

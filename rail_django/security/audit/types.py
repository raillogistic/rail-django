"""
Type definitions for security audit.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from django.utils import timezone as django_timezone


class AuditEventType(Enum):
    """Types d'Ç¸vÇ¸nements d'audit."""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    MFA_SETUP = "mfa_setup"
    MFA_SUCCESS = "mfa_success"
    MFA_FAILURE = "mfa_failure"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_OPERATION = "bulk_operation"
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    INTROSPECTION_ATTEMPT = "introspection_attempt"
    SYSTEM_ERROR = "system_error"
    CONFIGURATION_CHANGE = "configuration_change"
    SCHEMA_CHANGE = "schema_change"


class AuditSeverity(Enum):
    """Niveaux de gravitÇ¸ des Ç¸vÇ¸nements d'audit."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Çâ€°vÇ¸nement d'audit."""
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    user_id: Optional[int] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    operation_name: Optional[str] = None
    operation_type: Optional[str] = None
    query_hash: Optional[str] = None
    variables: Optional[dict[str, Any]] = None
    model_name: Optional[str] = None
    object_id: Optional[str] = None
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    message: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None
    risk_score: Optional[int] = None
    threat_indicators: Optional[list[str]] = None

    def __post_init__(self):
        if self.timestamp is None: self.timestamp = django_timezone.now()
        if self.tags is None: self.tags = []
        if self.details is None: self.details = {}
        if self.threat_indicators is None: self.threat_indicators = []

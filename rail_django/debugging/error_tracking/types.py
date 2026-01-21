"""
Type definitions for error tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Set


class ErrorCategory(Enum):
    """Categories of errors that can be tracked."""
    VALIDATION_ERROR = "validation_error"
    EXECUTION_ERROR = "execution_error"
    SCHEMA_ERROR = "schema_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TIMEOUT_ERROR = "timeout_error"
    NETWORK_ERROR = "network_error"
    DATABASE_ERROR = "database_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """Context information for an error."""
    operation_name: Optional[str] = None
    query: Optional[str] = None
    variables: Optional[dict[str, Any]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    client_info: Optional[dict[str, Any]] = None
    schema_name: Optional[str] = None
    field_path: Optional[str] = None


@dataclass
class ErrorOccurrence:
    """Represents a single error occurrence."""
    error_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    timestamp: datetime
    context: ErrorContext
    stack_trace: Optional[str] = None
    resolved: bool = False
    resolution_notes: Optional[str] = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class ErrorPattern:
    """Represents a pattern of similar errors."""
    pattern_id: str
    category: ErrorCategory
    message_pattern: str
    occurrences: list[ErrorOccurrence] = field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    frequency: int = 0
    affected_operations: set[str] = field(default_factory=set)
    affected_users: set[str] = field(default_factory=set)


@dataclass
class ErrorTrend:
    """Error trend analysis."""
    category: ErrorCategory
    time_period: str
    error_count: int
    unique_errors: int
    trend_direction: str  # 'increasing', 'decreasing', 'stable'
    change_percentage: float
    top_errors: list[str] = field(default_factory=list)


@dataclass
class ErrorAlert:
    """Error alert when thresholds are exceeded."""
    alert_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    threshold_type: str  # 'rate', 'count', 'new_error'
    current_value: float
    threshold_value: float
    time_window: str
    timestamp: datetime
    affected_operations: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

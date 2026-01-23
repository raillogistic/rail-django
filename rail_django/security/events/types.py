from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any


class EventCategory(str, Enum):
    """High-level event categories."""
    AUTHENTICATION = "auth"
    AUTHORIZATION = "authz"
    DATA_ACCESS = "data"
    QUERY_SECURITY = "query"
    RATE_LIMIT = "rate"
    SYSTEM = "system"


class EventType(str, Enum):
    """Specific event types."""
    # Authentication
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_ISSUED = "auth.token.issued"
    AUTH_TOKEN_REFRESHED = "auth.token.refreshed"
    AUTH_TOKEN_REVOKED = "auth.token.revoked"
    AUTH_TOKEN_INVALID = "auth.token.invalid"
    AUTH_MFA_SUCCESS = "auth.mfa.success"
    AUTH_MFA_FAILURE = "auth.mfa.failure"

    # Authorization
    AUTHZ_PERMISSION_GRANTED = "authz.permission.granted"
    AUTHZ_PERMISSION_DENIED = "authz.permission.denied"
    AUTHZ_ROLE_ASSIGNED = "authz.role.assigned"
    AUTHZ_ROLE_REVOKED = "authz.role.revoked"

    # Data Access
    DATA_READ = "data.read"
    DATA_CREATE = "data.create"
    DATA_UPDATE = "data.update"
    DATA_DELETE = "data.delete"
    DATA_BULK_OPERATION = "data.bulk"
    DATA_SENSITIVE_ACCESS = "data.sensitive.access"
    DATA_EXPORT = "data.export"

    # Query Security
    QUERY_BLOCKED_DEPTH = "query.blocked.depth"
    QUERY_BLOCKED_COMPLEXITY = "query.blocked.complexity"
    QUERY_BLOCKED_INTROSPECTION = "query.blocked.introspection"
    QUERY_VALIDATION_FAILED = "query.validation.failed"
    QUERY_INJECTION_ATTEMPT = "query.injection.attempt"

    # Rate Limiting
    RATE_LIMIT_EXCEEDED = "rate.limit.exceeded"
    RATE_LIMIT_WARNING = "rate.limit.warning"

    # System
    SYSTEM_ERROR = "system.error"
    SYSTEM_CONFIG_CHANGE = "system.config.change"

    # UI
    UI_ACTION = "ui.action"


class Severity(str, Enum):
    """Event severity levels (aligned with syslog)."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def numeric(self) -> int:
        return {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}[self.value]


class Outcome(str, Enum):
    """Result of the action."""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass
class Resource:
    """The resource being accessed/modified."""
    type: str  # "model", "field", "endpoint", "schema"
    name: str  # "User", "email", "/graphql/", "default"
    id: Optional[str] = None  # primary key if applicable

    def to_dict(self) -> dict:
        return {"type": self.type, "name": self.name, "id": self.id}


@dataclass
class SecurityEvent:
    """Unified security event for all audit logging."""
    # Identity
    event_type: EventType
    correlation_id: str

    # Actor
    user_id: Optional[int] = None
    username: Optional[str] = None
    client_ip: str = "unknown"
    user_agent: str = "unknown"
    session_id: Optional[str] = None

    # Action
    action: str = ""  # human-readable action description
    outcome: Outcome = Outcome.SUCCESS

    # Resource
    resource: Optional[Resource] = None

    # Severity & Risk
    severity: Severity = Severity.INFO
    risk_score: int = 0

    # Context
    request_path: str = ""
    request_method: str = ""
    operation_name: Optional[str] = None
    operation_type: Optional[str] = None
    schema_name: Optional[str] = None

    # Data (will be redacted before storage)
    context: dict = field(default_factory=dict)
    error_message: Optional[str] = None

    # Metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def category(self) -> EventCategory:
        """Derive category from event type."""
        prefix = self.event_type.value.split(".")[0]
        return {
            "auth": EventCategory.AUTHENTICATION,
            "authz": EventCategory.AUTHORIZATION,
            "data": EventCategory.DATA_ACCESS,
            "query": EventCategory.QUERY_SECURITY,
            "rate": EventCategory.RATE_LIMIT,
            "system": EventCategory.SYSTEM,
        }.get(prefix, EventCategory.SYSTEM)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["severity"] = self.severity.value
        data["outcome"] = self.outcome.value
        data["category"] = self.category.value
        data["timestamp"] = self.timestamp.isoformat()
        if self.resource:
            data["resource"] = self.resource.to_dict()
        return data

    @classmethod
    def from_context(
        cls,
        ctx: "SecurityContext",
        event_type: EventType,
        **kwargs
    ) -> "SecurityEvent":
        """Create event from security context."""
        return cls(
            event_type=event_type,
            correlation_id=ctx.correlation_id,
            user_id=ctx.actor.user_id,
            username=ctx.actor.username,
            client_ip=ctx.actor.client_ip,
            user_agent=ctx.actor.user_agent,
            session_id=ctx.actor.session_id,
            request_path=ctx.request_path,
            request_method=ctx.request_method,
            operation_name=ctx.operation_name,
            operation_type=ctx.operation_type,
            schema_name=ctx.schema_name,
            **kwargs
        )


# Severity mapping for automatic assignment
DEFAULT_SEVERITY: dict[EventType, Severity] = {
    EventType.AUTH_LOGIN_SUCCESS: Severity.INFO,
    EventType.AUTH_LOGIN_FAILURE: Severity.WARNING,
    EventType.AUTH_LOGOUT: Severity.INFO,
    EventType.AUTHZ_PERMISSION_DENIED: Severity.WARNING,
    EventType.DATA_SENSITIVE_ACCESS: Severity.WARNING,
    EventType.DATA_DELETE: Severity.WARNING,
    EventType.DATA_BULK_OPERATION: Severity.WARNING,
    EventType.QUERY_BLOCKED_DEPTH: Severity.WARNING,
    EventType.QUERY_BLOCKED_COMPLEXITY: Severity.WARNING,
    EventType.QUERY_INJECTION_ATTEMPT: Severity.CRITICAL,
    EventType.RATE_LIMIT_EXCEEDED: Severity.WARNING,
    EventType.SYSTEM_ERROR: Severity.ERROR,
}

# Risk score base values
DEFAULT_RISK_SCORES: dict[EventType, int] = {
    EventType.AUTH_LOGIN_FAILURE: 15,
    EventType.AUTHZ_PERMISSION_DENIED: 20,
    EventType.DATA_SENSITIVE_ACCESS: 30,
    EventType.DATA_DELETE: 25,
    EventType.DATA_BULK_OPERATION: 20,
    EventType.QUERY_BLOCKED_DEPTH: 25,
    EventType.QUERY_BLOCKED_COMPLEXITY: 25,
    EventType.QUERY_INJECTION_ATTEMPT: 80,
    EventType.RATE_LIMIT_EXCEEDED: 30,
}

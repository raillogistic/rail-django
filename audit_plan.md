# Unified Security & Observability Architecture Plan

## Overview

This plan consolidates the fragmented audit, logging, and security systems into a unified architecture with async event processing, distributed anomaly detection, and extensible sinks.

**Goals:**
- Single `SecurityEvent` type replacing multiple audit event classes
- Async event bus for non-blocking logging
- Redis-backed distributed rate limiting and anomaly detection
- Correlation IDs for request tracing
- Extensible sink architecture (DB, file, webhook, metrics)

---

## Phase 1: Security Context Foundation

**Objective:** Create a request-scoped security context that flows through the entire request lifecycle.

### 1.1 Create SecurityContext

**File:** `rail_django/security/context.py`

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import uuid4
from django.http import HttpRequest


@dataclass
class Actor:
    """Represents the entity performing an action."""
    user_id: Optional[int] = None
    username: Optional[str] = None
    client_ip: str = "unknown"
    user_agent: str = "unknown"
    session_id: Optional[str] = None

    @classmethod
    def from_request(cls, request: HttpRequest) -> "Actor":
        user = getattr(request, "user", None)
        return cls(
            user_id=user.id if user and user.is_authenticated else None,
            username=user.username if user and user.is_authenticated else None,
            client_ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "unknown")[:500],
            session_id=request.session.session_key if hasattr(request, "session") else None,
        )


@dataclass
class SecurityContext:
    """Request-scoped security context."""
    correlation_id: str
    actor: Actor
    request_path: str
    request_method: str
    timestamp: datetime
    schema_name: Optional[str] = None
    operation_name: Optional[str] = None
    operation_type: Optional[str] = None  # query, mutation, subscription
    risk_score: float = 0.0
    flags: set = field(default_factory=set)  # e.g., {"rate_limited", "suspicious"}
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: HttpRequest) -> "SecurityContext":
        return cls(
            correlation_id=request.META.get("HTTP_X_CORRELATION_ID") or str(uuid4()),
            actor=Actor.from_request(request),
            request_path=request.path,
            request_method=request.method,
            timestamp=datetime.now(timezone.utc),
        )

    def add_risk(self, score: float, reason: str):
        """Accumulate risk score during request processing."""
        self.risk_score = min(100.0, self.risk_score + score)
        self.metadata.setdefault("risk_reasons", []).append(reason)


def get_client_ip(request: HttpRequest) -> str:
    """Extract client IP from request headers."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip:
        return real_ip
    return request.META.get("REMOTE_ADDR", "unknown")
```

### 1.2 Create Context Middleware

**File:** `rail_django/security/middleware/context.py`

```python
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin
from ..context import SecurityContext

SECURITY_CONTEXT_ATTR = "_security_context"


class SecurityContextMiddleware(MiddlewareMixin):
    """Injects SecurityContext into every request."""

    def process_request(self, request: HttpRequest) -> None:
        context = SecurityContext.from_request(request)
        setattr(request, SECURITY_CONTEXT_ATTR, context)
        # Add correlation ID to response headers
        request._security_correlation_id = context.correlation_id

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        correlation_id = getattr(request, "_security_correlation_id", None)
        if correlation_id:
            response["X-Correlation-ID"] = correlation_id
        return response


def get_security_context(request: HttpRequest) -> SecurityContext:
    """Retrieve security context from request."""
    ctx = getattr(request, SECURITY_CONTEXT_ATTR, None)
    if ctx is None:
        # Fallback: create context if middleware wasn't applied
        ctx = SecurityContext.from_request(request)
        setattr(request, SECURITY_CONTEXT_ATTR, ctx)
    return ctx
```

### 1.3 Update Django Settings Template

**File:** `rail_django/conf/project_template/project_name/settings.py` (update MIDDLEWARE)

Add to middleware list:
```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "rail_django.security.middleware.context.SecurityContextMiddleware",  # ADD THIS
    # ... rest of middleware
]
```

### 1.4 Tests

**File:** `rail_django/tests/unit/security/test_context.py`

```python
import pytest
from django.test import RequestFactory
from rail_django.security.context import SecurityContext, Actor, get_client_ip
from rail_django.security.middleware.context import SecurityContextMiddleware, get_security_context


@pytest.mark.unit
class TestSecurityContext:
    def test_from_request_anonymous(self):
        factory = RequestFactory()
        request = factory.get("/graphql/")
        ctx = SecurityContext.from_request(request)

        assert ctx.correlation_id is not None
        assert len(ctx.correlation_id) == 36  # UUID format
        assert ctx.actor.user_id is None
        assert ctx.request_path == "/graphql/"
        assert ctx.risk_score == 0.0

    def test_correlation_id_from_header(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_CORRELATION_ID="test-123")
        ctx = SecurityContext.from_request(request)
        assert ctx.correlation_id == "test-123"

    def test_add_risk_accumulates(self):
        factory = RequestFactory()
        request = factory.get("/")
        ctx = SecurityContext.from_request(request)

        ctx.add_risk(20.0, "suspicious_pattern")
        ctx.add_risk(30.0, "sensitive_field_access")

        assert ctx.risk_score == 50.0
        assert len(ctx.metadata["risk_reasons"]) == 2

    def test_risk_score_capped_at_100(self):
        factory = RequestFactory()
        request = factory.get("/")
        ctx = SecurityContext.from_request(request)

        ctx.add_risk(60.0, "reason1")
        ctx.add_risk(60.0, "reason2")

        assert ctx.risk_score == 100.0


@pytest.mark.unit
class TestGetClientIp:
    def test_x_forwarded_for(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
        assert get_client_ip(request) == "1.2.3.4"

    def test_x_real_ip(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REAL_IP="9.8.7.6")
        assert get_client_ip(request) == "9.8.7.6"

    def test_remote_addr_fallback(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        assert get_client_ip(request) == "127.0.0.1"
```

---

## Phase 2: Unified Event Types

**Objective:** Define a single `SecurityEvent` dataclass that replaces all existing audit event types.

### 2.1 Event Type Definitions

**File:** `rail_django/security/events/types.py`

```python
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
```

### 2.2 Event Builder Helper

**File:** `rail_django/security/events/builder.py`

```python
from typing import Optional
from django.http import HttpRequest
from .types import (
    SecurityEvent, EventType, Severity, Outcome, Resource,
    DEFAULT_SEVERITY, DEFAULT_RISK_SCORES
)
from ..context import SecurityContext, get_security_context


class EventBuilder:
    """Fluent builder for SecurityEvent."""

    def __init__(self, event_type: EventType):
        self._event_type = event_type
        self._kwargs: dict = {
            "severity": DEFAULT_SEVERITY.get(event_type, Severity.INFO),
            "risk_score": DEFAULT_RISK_SCORES.get(event_type, 0),
        }

    def from_request(self, request: HttpRequest) -> "EventBuilder":
        ctx = get_security_context(request)
        self._kwargs.update({
            "correlation_id": ctx.correlation_id,
            "user_id": ctx.actor.user_id,
            "username": ctx.actor.username,
            "client_ip": ctx.actor.client_ip,
            "user_agent": ctx.actor.user_agent,
            "session_id": ctx.actor.session_id,
            "request_path": ctx.request_path,
            "request_method": ctx.request_method,
            "operation_name": ctx.operation_name,
            "schema_name": ctx.schema_name,
        })
        return self

    def from_context(self, ctx: SecurityContext) -> "EventBuilder":
        self._kwargs.update({
            "correlation_id": ctx.correlation_id,
            "user_id": ctx.actor.user_id,
            "username": ctx.actor.username,
            "client_ip": ctx.actor.client_ip,
            "user_agent": ctx.actor.user_agent,
            "session_id": ctx.actor.session_id,
            "request_path": ctx.request_path,
            "request_method": ctx.request_method,
            "operation_name": ctx.operation_name,
            "schema_name": ctx.schema_name,
        })
        return self

    def outcome(self, outcome: Outcome) -> "EventBuilder":
        self._kwargs["outcome"] = outcome
        return self

    def severity(self, severity: Severity) -> "EventBuilder":
        self._kwargs["severity"] = severity
        return self

    def risk(self, score: int) -> "EventBuilder":
        self._kwargs["risk_score"] = score
        return self

    def action(self, description: str) -> "EventBuilder":
        self._kwargs["action"] = description
        return self

    def resource(self, type: str, name: str, id: Optional[str] = None) -> "EventBuilder":
        self._kwargs["resource"] = Resource(type=type, name=name, id=id)
        return self

    def context(self, **data) -> "EventBuilder":
        self._kwargs.setdefault("context", {}).update(data)
        return self

    def error(self, message: str) -> "EventBuilder":
        self._kwargs["error_message"] = message
        return self

    def operation(self, name: str, type: str = "query") -> "EventBuilder":
        self._kwargs["operation_name"] = name
        self._kwargs["operation_type"] = type
        return self

    def build(self) -> SecurityEvent:
        if "correlation_id" not in self._kwargs:
            from uuid import uuid4
            self._kwargs["correlation_id"] = str(uuid4())
        return SecurityEvent(event_type=self._event_type, **self._kwargs)


def event(event_type: EventType) -> EventBuilder:
    """Shortcut to create an EventBuilder."""
    return EventBuilder(event_type)
```

### 2.3 Tests

**File:** `rail_django/tests/unit/security/test_events.py`

```python
import pytest
from rail_django.security.events.types import (
    SecurityEvent, EventType, Severity, Outcome, Resource, EventCategory
)
from rail_django.security.events.builder import event, EventBuilder


@pytest.mark.unit
class TestSecurityEvent:
    def test_category_derived_from_type(self):
        evt = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        assert evt.category == EventCategory.AUTHENTICATION

    def test_to_dict_serialization(self):
        evt = SecurityEvent(
            event_type=EventType.DATA_READ,
            correlation_id="test-123",
            user_id=1,
            resource=Resource(type="model", name="User", id="42")
        )
        data = evt.to_dict()

        assert data["event_type"] == "data.read"
        assert data["category"] == "data"
        assert data["resource"]["name"] == "User"
        assert "timestamp" in data


@pytest.mark.unit
class TestEventBuilder:
    def test_fluent_building(self):
        evt = (
            event(EventType.AUTH_LOGIN_FAILURE)
            .action("Failed login attempt")
            .outcome(Outcome.FAILURE)
            .context(username_attempted="admin")
            .error("Invalid credentials")
            .build()
        )

        assert evt.event_type == EventType.AUTH_LOGIN_FAILURE
        assert evt.outcome == Outcome.FAILURE
        assert evt.context["username_attempted"] == "admin"
        assert evt.error_message == "Invalid credentials"
        assert evt.severity == Severity.WARNING  # default for login failure

    def test_resource_builder(self):
        evt = (
            event(EventType.DATA_DELETE)
            .resource("model", "User", "123")
            .build()
        )

        assert evt.resource.type == "model"
        assert evt.resource.name == "User"
        assert evt.resource.id == "123"
```

---

## Phase 3: Event Bus & Sinks

**Objective:** Create async event processing with pluggable sinks.

### 3.1 Sink Interface

**File:** `rail_django/security/events/sinks/base.py`

```python
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..types import SecurityEvent


class EventSink(ABC):
    """Base class for event sinks."""

    @abstractmethod
    def write(self, event: "SecurityEvent") -> None:
        """Write event to the sink."""
        pass

    def flush(self) -> None:
        """Flush any buffered events."""
        pass

    def close(self) -> None:
        """Clean up resources."""
        pass
```

### 3.2 Database Sink

**File:** `rail_django/security/events/sinks/database.py`

```python
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
```

### 3.3 File Sink (Structured JSON)

**File:** `rail_django/security/events/sinks/file.py`

```python
import json
import logging
from typing import TYPE_CHECKING
from django.core.serializers.json import DjangoJSONEncoder
from .base import EventSink

if TYPE_CHECKING:
    from ..types import SecurityEvent


class FileSink(EventSink):
    """Writes events to Python logging (structured JSON)."""

    def __init__(self, logger_name: str = "security.audit"):
        self.logger = logging.getLogger(logger_name)

    def write(self, event: "SecurityEvent") -> None:
        log_data = event.to_dict()
        message = json.dumps(log_data, cls=DjangoJSONEncoder, ensure_ascii=False)

        level = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }.get(event.severity.value, logging.INFO)

        self.logger.log(level, message)
```

### 3.4 Webhook Sink

**File:** `rail_django/security/events/sinks/webhook.py`

```python
import json
import logging
from typing import TYPE_CHECKING, Optional
from django.core.serializers.json import DjangoJSONEncoder
from .base import EventSink

if TYPE_CHECKING:
    from ..types import SecurityEvent

logger = logging.getLogger(__name__)


class WebhookSink(EventSink):
    """Sends events to external webhook."""

    def __init__(
        self,
        url: str,
        timeout: int = 5,
        headers: Optional[dict] = None,
        min_severity: str = "warning"
    ):
        self.url = url
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}
        self.min_severity = min_severity
        self._severity_order = ["debug", "info", "warning", "error", "critical"]

    def _should_send(self, event: "SecurityEvent") -> bool:
        event_level = self._severity_order.index(event.severity.value)
        min_level = self._severity_order.index(self.min_severity)
        return event_level >= min_level

    def write(self, event: "SecurityEvent") -> None:
        if not self._should_send(event):
            return

        try:
            import requests
            response = requests.post(
                self.url,
                data=json.dumps(event.to_dict(), cls=DjangoJSONEncoder),
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to send event to webhook: {e}")
```

### 3.5 Metrics Sink (Prometheus/StatsD)

**File:** `rail_django/security/events/sinks/metrics.py`

```python
import logging
from typing import TYPE_CHECKING, Optional
from .base import EventSink

if TYPE_CHECKING:
    from ..types import SecurityEvent

logger = logging.getLogger(__name__)


class MetricsSink(EventSink):
    """Exports events as metrics (Prometheus or StatsD)."""

    def __init__(self, backend: str = "prometheus"):
        self.backend = backend
        self._counters: dict = {}
        self._setup_backend()

    def _setup_backend(self):
        if self.backend == "prometheus":
            try:
                from prometheus_client import Counter
                self._event_counter = Counter(
                    "rail_security_events_total",
                    "Total security events",
                    ["event_type", "outcome", "severity"]
                )
                self._risk_counter = Counter(
                    "rail_security_risk_total",
                    "Accumulated risk scores",
                    ["event_type"]
                )
            except ImportError:
                logger.warning("prometheus_client not installed, metrics disabled")
                self._event_counter = None

    def write(self, event: "SecurityEvent") -> None:
        if self.backend == "prometheus" and self._event_counter:
            self._event_counter.labels(
                event_type=event.event_type.value,
                outcome=event.outcome.value,
                severity=event.severity.value,
            ).inc()

            if event.risk_score > 0:
                self._risk_counter.labels(
                    event_type=event.event_type.value
                ).inc(event.risk_score)
```

### 3.6 Event Bus

**File:** `rail_django/security/events/bus.py`

```python
import logging
import queue
import threading
from typing import List, Optional
from django.conf import settings
from .types import SecurityEvent
from .sinks.base import EventSink

logger = logging.getLogger(__name__)


class EventBus:
    """
    Async event dispatcher with pluggable sinks.

    Events are queued and processed by a background thread to avoid
    blocking request handling.
    """

    def __init__(self, async_processing: bool = True, max_queue_size: int = 10000):
        self._sinks: List[EventSink] = []
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._async = async_processing
        self._running = False
        self._worker: Optional[threading.Thread] = None
        self._redactor: Optional["EventRedactor"] = None

    def add_sink(self, sink: EventSink) -> "EventBus":
        """Add a sink to receive events."""
        self._sinks.append(sink)
        return self

    def set_redactor(self, redactor: "EventRedactor") -> "EventBus":
        """Set the redactor for sensitive data."""
        self._redactor = redactor
        return self

    def start(self) -> None:
        """Start the background processing thread."""
        if self._async and not self._running:
            self._running = True
            self._worker = threading.Thread(target=self._process_loop, daemon=True)
            self._worker.start()
            logger.info("EventBus started with async processing")

    def stop(self) -> None:
        """Stop processing and flush remaining events."""
        self._running = False
        if self._worker:
            self._worker.join(timeout=5.0)
        self._flush_queue()
        for sink in self._sinks:
            sink.close()

    def emit(self, event: SecurityEvent) -> None:
        """Emit an event to all sinks."""
        # Redact sensitive data
        if self._redactor:
            event = self._redactor.redact(event)

        if self._async:
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                logger.warning("Event queue full, dropping event")
        else:
            self._dispatch(event)

    def _process_loop(self) -> None:
        """Background thread processing loop."""
        while self._running:
            try:
                event = self._queue.get(timeout=1.0)
                self._dispatch(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")

    def _dispatch(self, event: SecurityEvent) -> None:
        """Send event to all sinks."""
        for sink in self._sinks:
            try:
                sink.write(event)
            except Exception as e:
                logger.error(f"Sink {sink.__class__.__name__} failed: {e}")

    def _flush_queue(self) -> None:
        """Process remaining events in queue."""
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                self._dispatch(event)
            except queue.Empty:
                break


class EventRedactor:
    """Redacts sensitive data from events before storage."""

    def __init__(self, fields: Optional[List[str]] = None, mask: str = "***REDACTED***"):
        self.fields = set(f.lower() for f in (fields or [
            "password", "token", "secret", "key", "credential",
            "authorization", "ssn", "credit_card", "cvv",
        ]))
        self.mask = mask

    def redact(self, event: SecurityEvent) -> SecurityEvent:
        """Return a new event with sensitive data redacted."""
        import copy
        event = copy.deepcopy(event)
        event.context = self._redact_dict(event.context)
        if event.error_message:
            event.error_message = self._redact_string(event.error_message)
        return event

    def _redact_dict(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            if key.lower() in self.fields:
                result[key] = self.mask
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_dict(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _redact_string(self, text: str) -> str:
        lowered = text.lower()
        for field in self.fields:
            if field in lowered:
                return self.mask
        return text


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = _create_event_bus()
    return _event_bus


def _create_event_bus() -> EventBus:
    """Create and configure the event bus from settings."""
    from .sinks.database import DatabaseSink
    from .sinks.file import FileSink
    from .sinks.webhook import WebhookSink

    async_mode = getattr(settings, "SECURITY_EVENT_ASYNC", True)
    bus = EventBus(async_processing=async_mode)

    # Configure redactor
    redaction_fields = getattr(settings, "AUDIT_REDACTION_FIELDS", None)
    bus.set_redactor(EventRedactor(fields=redaction_fields))

    # Add database sink
    if getattr(settings, "AUDIT_STORE_IN_DATABASE", True):
        bus.add_sink(DatabaseSink())

    # Add file sink
    if getattr(settings, "AUDIT_STORE_IN_FILE", True):
        bus.add_sink(FileSink())

    # Add webhook sink
    webhook_url = getattr(settings, "AUDIT_WEBHOOK_URL", None)
    if webhook_url:
        bus.add_sink(WebhookSink(url=webhook_url))

    # Add metrics sink
    if getattr(settings, "SECURITY_METRICS_ENABLED", False):
        from .sinks.metrics import MetricsSink
        bus.add_sink(MetricsSink())

    bus.start()
    return bus
```

### 3.7 Django AppConfig Integration

**File:** `rail_django/security/apps.py`

```python
from django.apps import AppConfig


class SecurityConfig(AppConfig):
    name = "rail_django.security"
    verbose_name = "Rail Django Security"

    def ready(self):
        # Import to register signal handlers
        from . import signals  # noqa

        # Initialize event bus (lazy, only creates when first event emitted)
        # The bus auto-starts in get_event_bus()
```

### 3.8 Tests

**File:** `rail_django/tests/unit/security/test_event_bus.py`

```python
import pytest
from unittest.mock import Mock, patch
from rail_django.security.events.types import SecurityEvent, EventType, Outcome
from rail_django.security.events.bus import EventBus, EventRedactor
from rail_django.security.events.sinks.base import EventSink


class MockSink(EventSink):
    def __init__(self):
        self.events = []

    def write(self, event):
        self.events.append(event)


@pytest.mark.unit
class TestEventBus:
    def test_sync_dispatch(self):
        bus = EventBus(async_processing=False)
        sink = MockSink()
        bus.add_sink(sink)

        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        bus.emit(event)

        assert len(sink.events) == 1
        assert sink.events[0].correlation_id == "test-123"

    def test_multiple_sinks(self):
        bus = EventBus(async_processing=False)
        sink1 = MockSink()
        sink2 = MockSink()
        bus.add_sink(sink1).add_sink(sink2)

        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        bus.emit(event)

        assert len(sink1.events) == 1
        assert len(sink2.events) == 1

    def test_sink_error_isolated(self):
        bus = EventBus(async_processing=False)

        failing_sink = Mock(spec=EventSink)
        failing_sink.write.side_effect = Exception("Sink error")

        working_sink = MockSink()

        bus.add_sink(failing_sink).add_sink(working_sink)

        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_SUCCESS,
            correlation_id="test-123"
        )
        bus.emit(event)  # Should not raise

        assert len(working_sink.events) == 1


@pytest.mark.unit
class TestEventRedactor:
    def test_redacts_password_fields(self):
        redactor = EventRedactor()
        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_FAILURE,
            correlation_id="test-123",
            context={"username": "admin", "password": "secret123"}
        )

        redacted = redactor.redact(event)

        assert redacted.context["username"] == "admin"
        assert redacted.context["password"] == "***REDACTED***"

    def test_redacts_nested_fields(self):
        redactor = EventRedactor()
        event = SecurityEvent(
            event_type=EventType.DATA_CREATE,
            correlation_id="test-123",
            context={
                "input": {
                    "user": {"name": "John", "token": "abc123"}
                }
            }
        )

        redacted = redactor.redact(event)

        assert redacted.context["input"]["user"]["name"] == "John"
        assert redacted.context["input"]["user"]["token"] == "***REDACTED***"

    def test_original_event_unchanged(self):
        redactor = EventRedactor()
        event = SecurityEvent(
            event_type=EventType.AUTH_LOGIN_FAILURE,
            correlation_id="test-123",
            context={"password": "secret123"}
        )

        redactor.redact(event)

        assert event.context["password"] == "secret123"  # Original unchanged
```

---

## Phase 4: Public API & Facade

**Objective:** Create a simple, unified API for emitting security events.

### 4.1 Security Facade

**File:** `rail_django/security/api.py`

```python
from typing import Optional, Any
from django.http import HttpRequest
from .events.types import SecurityEvent, EventType, Severity, Outcome, Resource
from .events.builder import event, EventBuilder
from .events.bus import get_event_bus
from .context import SecurityContext, get_security_context


class SecurityAPI:
    """
    Main API for security operations.

    Usage:
        from rail_django.security import security

        security.emit(
            EventType.AUTH_LOGIN_FAILURE,
            request=request,
            outcome=Outcome.FAILURE,
            context={"username": username}
        )
    """

    def emit(
        self,
        event_type: EventType,
        *,
        request: Optional[HttpRequest] = None,
        ctx: Optional[SecurityContext] = None,
        outcome: Outcome = Outcome.SUCCESS,
        severity: Optional[Severity] = None,
        action: str = "",
        resource: Optional[Resource] = None,
        resource_type: Optional[str] = None,
        resource_name: Optional[str] = None,
        resource_id: Optional[str] = None,
        context: Optional[dict] = None,
        error: Optional[str] = None,
        risk_score: Optional[int] = None,
    ) -> None:
        """
        Emit a security event.

        Args:
            event_type: The type of event
            request: Django request (will extract context automatically)
            ctx: Existing SecurityContext (alternative to request)
            outcome: Result of the action
            severity: Override default severity
            action: Human-readable action description
            resource: Resource being accessed (or use resource_type/name/id)
            context: Additional context data (will be redacted)
            error: Error message if applicable
            risk_score: Override default risk score
        """
        builder = event(event_type)

        # Set context from request or SecurityContext
        if request:
            builder.from_request(request)
        elif ctx:
            builder.from_context(ctx)

        # Set outcome
        builder.outcome(outcome)

        # Set optional fields
        if severity:
            builder.severity(severity)
        if action:
            builder.action(action)
        if resource:
            builder._kwargs["resource"] = resource
        elif resource_type and resource_name:
            builder.resource(resource_type, resource_name, resource_id)
        if context:
            builder.context(**context)
        if error:
            builder.error(error)
        if risk_score is not None:
            builder.risk(risk_score)

        # Emit to bus
        get_event_bus().emit(builder.build())

    def auth_success(self, request: HttpRequest, user_id: int, username: str) -> None:
        """Log successful authentication."""
        self.emit(
            EventType.AUTH_LOGIN_SUCCESS,
            request=request,
            action=f"User {username} logged in",
            context={"user_id": user_id}
        )

    def auth_failure(
        self,
        request: HttpRequest,
        username: Optional[str] = None,
        reason: str = "Invalid credentials"
    ) -> None:
        """Log failed authentication attempt."""
        self.emit(
            EventType.AUTH_LOGIN_FAILURE,
            request=request,
            outcome=Outcome.FAILURE,
            action="Login attempt failed",
            context={"username_attempted": username},
            error=reason
        )

    def permission_denied(
        self,
        request: HttpRequest,
        resource_type: str,
        resource_name: str,
        action: str = "access"
    ) -> None:
        """Log permission denial."""
        self.emit(
            EventType.AUTHZ_PERMISSION_DENIED,
            request=request,
            outcome=Outcome.DENIED,
            action=f"Permission denied to {action} {resource_name}",
            resource_type=resource_type,
            resource_name=resource_name
        )

    def data_access(
        self,
        request: HttpRequest,
        model: str,
        field: Optional[str] = None,
        record_id: Optional[str] = None,
        sensitive: bool = False
    ) -> None:
        """Log data access."""
        event_type = EventType.DATA_SENSITIVE_ACCESS if sensitive else EventType.DATA_READ
        self.emit(
            event_type,
            request=request,
            resource_type="field" if field else "model",
            resource_name=f"{model}.{field}" if field else model,
            resource_id=record_id
        )

    def query_blocked(
        self,
        request: HttpRequest,
        reason: str,
        query_info: Optional[dict] = None
    ) -> None:
        """Log blocked GraphQL query."""
        event_type = {
            "depth": EventType.QUERY_BLOCKED_DEPTH,
            "complexity": EventType.QUERY_BLOCKED_COMPLEXITY,
            "introspection": EventType.QUERY_BLOCKED_INTROSPECTION,
        }.get(reason, EventType.QUERY_VALIDATION_FAILED)

        self.emit(
            event_type,
            request=request,
            outcome=Outcome.BLOCKED,
            action=f"Query blocked: {reason}",
            context=query_info or {}
        )

    def rate_limited(self, request: HttpRequest, limit_type: str = "global") -> None:
        """Log rate limit exceeded."""
        self.emit(
            EventType.RATE_LIMIT_EXCEEDED,
            request=request,
            outcome=Outcome.BLOCKED,
            action=f"Rate limit exceeded: {limit_type}",
            context={"limit_type": limit_type}
        )


# Global instance
security = SecurityAPI()
```

### 4.2 Update Package Exports

**File:** `rail_django/security/__init__.py`

```python
from .api import security, SecurityAPI
from .context import SecurityContext, get_security_context, Actor
from .events.types import (
    SecurityEvent,
    EventType,
    EventCategory,
    Severity,
    Outcome,
    Resource,
)
from .events.builder import event, EventBuilder
from .events.bus import get_event_bus, EventBus

__all__ = [
    # Main API
    "security",
    "SecurityAPI",
    # Context
    "SecurityContext",
    "get_security_context",
    "Actor",
    # Events
    "SecurityEvent",
    "EventType",
    "EventCategory",
    "Severity",
    "Outcome",
    "Resource",
    # Builder
    "event",
    "EventBuilder",
    # Bus
    "get_event_bus",
    "EventBus",
]
```

### 4.3 Decorator for Automatic Logging

**File:** `rail_django/security/decorators.py`

```python
import functools
from typing import Optional, Callable, Any
from .events.types import EventType, Outcome
from .api import security


def audit(
    event_type: EventType,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    include_args: bool = False
) -> Callable:
    """
    Decorator to automatically log function calls.

    Usage:
        @audit(EventType.DATA_READ, resource_type="model")
        def get_user(self, info, id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Try to find request in args (common patterns)
            request = None
            info = kwargs.get("info") or (args[1] if len(args) > 1 else None)
            if hasattr(info, "context"):
                request = getattr(info.context, "request", None)

            context = {}
            if include_args:
                context["args"] = {k: v for k, v in kwargs.items() if k != "info"}

            try:
                result = func(*args, **kwargs)
                security.emit(
                    event_type,
                    request=request,
                    outcome=Outcome.SUCCESS,
                    action=action or func.__name__,
                    resource_type=resource_type,
                    resource_name=func.__name__,
                    context=context
                )
                return result
            except Exception as e:
                security.emit(
                    event_type,
                    request=request,
                    outcome=Outcome.ERROR,
                    action=action or func.__name__,
                    resource_type=resource_type,
                    resource_name=func.__name__,
                    context=context,
                    error=str(e)
                )
                raise

        return wrapper
    return decorator
```

### 4.4 Tests

**File:** `rail_django/tests/unit/security/test_api.py`

```python
import pytest
from unittest.mock import patch, Mock
from django.test import RequestFactory
from rail_django.security.api import security
from rail_django.security.events.types import EventType, Outcome


@pytest.mark.unit
class TestSecurityAPI:
    @patch("rail_django.security.api.get_event_bus")
    def test_emit_basic_event(self, mock_get_bus):
        mock_bus = Mock()
        mock_get_bus.return_value = mock_bus

        factory = RequestFactory()
        request = factory.post("/graphql/")

        security.emit(
            EventType.AUTH_LOGIN_SUCCESS,
            request=request,
            action="User logged in"
        )

        mock_bus.emit.assert_called_once()
        event = mock_bus.emit.call_args[0][0]
        assert event.event_type == EventType.AUTH_LOGIN_SUCCESS
        assert event.action == "User logged in"

    @patch("rail_django.security.api.get_event_bus")
    def test_auth_failure_helper(self, mock_get_bus):
        mock_bus = Mock()
        mock_get_bus.return_value = mock_bus

        factory = RequestFactory()
        request = factory.post("/graphql/")

        security.auth_failure(request, username="admin", reason="Bad password")

        event = mock_bus.emit.call_args[0][0]
        assert event.event_type == EventType.AUTH_LOGIN_FAILURE
        assert event.outcome == Outcome.FAILURE
        assert event.context["username_attempted"] == "admin"

    @patch("rail_django.security.api.get_event_bus")
    def test_query_blocked_maps_reason_to_type(self, mock_get_bus):
        mock_bus = Mock()
        mock_get_bus.return_value = mock_bus

        factory = RequestFactory()
        request = factory.post("/graphql/")

        security.query_blocked(request, reason="depth", query_info={"depth": 15})

        event = mock_bus.emit.call_args[0][0]
        assert event.event_type == EventType.QUERY_BLOCKED_DEPTH
        assert event.outcome == Outcome.BLOCKED
```

---

## Phase 5: Redis-backed Anomaly Detection

**Objective:** Replace in-memory counters with distributed Redis-based detection.

### 5.1 Redis Backend

**File:** `rail_django/security/anomaly/backends/redis.py`

```python
import time
import logging
from typing import Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisAnomalyBackend:
    """
    Redis-backed sliding window counter for distributed anomaly detection.

    Uses sorted sets with timestamps as scores for efficient sliding window queries.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client or self._get_default_client()
        self.prefix = getattr(settings, "SECURITY_REDIS_PREFIX", "rail:security:")

    def _get_default_client(self):
        try:
            import redis
            url = getattr(settings, "SECURITY_REDIS_URL", None)
            if url:
                return redis.from_url(url)
            return redis.Redis(
                host=getattr(settings, "SECURITY_REDIS_HOST", "localhost"),
                port=getattr(settings, "SECURITY_REDIS_PORT", 6379),
                db=getattr(settings, "SECURITY_REDIS_DB", 0),
            )
        except ImportError:
            logger.warning("redis package not installed, anomaly detection disabled")
            return None

    def increment_counter(
        self,
        key: str,
        window_seconds: int = 300,
        max_entries: int = 1000
    ) -> Tuple[int, bool]:
        """
        Increment a sliding window counter.

        Returns:
            Tuple of (current_count, is_new_window)
        """
        if not self.redis:
            return 0, False

        full_key = f"{self.prefix}{key}"
        now = time.time()
        window_start = now - window_seconds

        pipe = self.redis.pipeline()
        # Remove old entries outside window
        pipe.zremrangebyscore(full_key, 0, window_start)
        # Add current timestamp
        pipe.zadd(full_key, {str(now): now})
        # Count entries in window
        pipe.zcard(full_key)
        # Set expiry
        pipe.expire(full_key, window_seconds + 60)

        results = pipe.execute()
        count = results[2]

        return count, results[0] > 0  # is_new_window if we removed entries

    def get_counter(self, key: str, window_seconds: int = 300) -> int:
        """Get current count in sliding window."""
        if not self.redis:
            return 0

        full_key = f"{self.prefix}{key}"
        now = time.time()
        window_start = now - window_seconds

        return self.redis.zcount(full_key, window_start, now)

    def is_blocked(self, key: str) -> bool:
        """Check if a key is in the blocklist."""
        if not self.redis:
            return False
        return self.redis.exists(f"{self.prefix}blocked:{key}") > 0

    def block(self, key: str, duration_seconds: int = 3600) -> None:
        """Add key to blocklist."""
        if not self.redis:
            return
        self.redis.setex(f"{self.prefix}blocked:{key}", duration_seconds, "1")

    def unblock(self, key: str) -> None:
        """Remove key from blocklist."""
        if not self.redis:
            return
        self.redis.delete(f"{self.prefix}blocked:{key}")
```

### 5.2 Anomaly Detector

**File:** `rail_django/security/anomaly/detector.py`

```python
import logging
from dataclasses import dataclass
from typing import Optional
from django.conf import settings
from .backends.redis import RedisAnomalyBackend

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Result of anomaly detection check."""
    detected: bool
    reason: Optional[str] = None
    count: int = 0
    threshold: int = 0
    should_block: bool = False
    block_duration: int = 0


class AnomalyDetector:
    """
    Detects anomalous patterns like brute force attacks.

    Uses Redis for distributed counting across multiple processes/servers.
    """

    def __init__(self, backend: Optional[RedisAnomalyBackend] = None):
        self.backend = backend or RedisAnomalyBackend()
        self._load_config()

    def _load_config(self):
        thresholds = getattr(settings, "SECURITY_ANOMALY_THRESHOLDS", {})

        # Brute force thresholds
        self.login_failure_ip_threshold = thresholds.get("login_failure_per_ip", 10)
        self.login_failure_user_threshold = thresholds.get("login_failure_per_user", 5)
        self.login_failure_window = thresholds.get("login_failure_window", 300)  # 5 min

        # Rate limit thresholds
        self.rate_limit_threshold = thresholds.get("rate_limit_per_ip", 100)
        self.rate_limit_window = thresholds.get("rate_limit_window", 60)  # 1 min

        # Blocking config
        self.auto_block_enabled = thresholds.get("auto_block_enabled", True)
        self.block_duration = thresholds.get("block_duration", 3600)  # 1 hour

    def check_login_failure(
        self,
        client_ip: str,
        username: Optional[str] = None
    ) -> DetectionResult:
        """
        Check for brute force login attempts.

        Call this after each failed login attempt.
        """
        # Check if already blocked
        if self.backend.is_blocked(f"ip:{client_ip}"):
            return DetectionResult(
                detected=True,
                reason="ip_blocked",
                should_block=False  # Already blocked
            )

        # Check IP-based threshold
        ip_key = f"login_fail:ip:{client_ip}"
        ip_count, _ = self.backend.increment_counter(
            ip_key,
            window_seconds=self.login_failure_window
        )

        if ip_count >= self.login_failure_ip_threshold:
            if self.auto_block_enabled:
                self.backend.block(f"ip:{client_ip}", self.block_duration)
            return DetectionResult(
                detected=True,
                reason="ip_threshold_exceeded",
                count=ip_count,
                threshold=self.login_failure_ip_threshold,
                should_block=self.auto_block_enabled,
                block_duration=self.block_duration
            )

        # Check username-based threshold
        if username:
            if self.backend.is_blocked(f"user:{username}"):
                return DetectionResult(
                    detected=True,
                    reason="user_blocked"
                )

            user_key = f"login_fail:user:{username}"
            user_count, _ = self.backend.increment_counter(
                user_key,
                window_seconds=self.login_failure_window
            )

            if user_count >= self.login_failure_user_threshold:
                return DetectionResult(
                    detected=True,
                    reason="user_threshold_exceeded",
                    count=user_count,
                    threshold=self.login_failure_user_threshold,
                    should_block=False  # Don't auto-block users, just detect
                )

        return DetectionResult(detected=False, count=ip_count)

    def check_rate_limit(self, client_ip: str, endpoint: str = "global") -> DetectionResult:
        """
        Check request rate limit.

        Call this on each request.
        """
        if self.backend.is_blocked(f"ip:{client_ip}"):
            return DetectionResult(detected=True, reason="ip_blocked")

        key = f"rate:{endpoint}:{client_ip}"
        count, _ = self.backend.increment_counter(
            key,
            window_seconds=self.rate_limit_window
        )

        if count >= self.rate_limit_threshold:
            return DetectionResult(
                detected=True,
                reason="rate_limit_exceeded",
                count=count,
                threshold=self.rate_limit_threshold
            )

        return DetectionResult(detected=False, count=count)

    def is_ip_blocked(self, client_ip: str) -> bool:
        """Check if an IP is blocked."""
        return self.backend.is_blocked(f"ip:{client_ip}")

    def block_ip(self, client_ip: str, duration: Optional[int] = None) -> None:
        """Manually block an IP."""
        self.backend.block(f"ip:{client_ip}", duration or self.block_duration)

    def unblock_ip(self, client_ip: str) -> None:
        """Unblock an IP."""
        self.backend.unblock(f"ip:{client_ip}")


# Global detector instance
_detector: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    """Get the global anomaly detector."""
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector
```

### 5.3 Integration with Security API

**Update:** `rail_django/security/api.py`

Add to `SecurityAPI` class:

```python
def auth_failure(
    self,
    request: HttpRequest,
    username: Optional[str] = None,
    reason: str = "Invalid credentials"
) -> DetectionResult:
    """Log failed authentication and check for anomalies."""
    from .anomaly.detector import get_anomaly_detector
    from .context import get_client_ip

    # Check for brute force
    detector = get_anomaly_detector()
    detection = detector.check_login_failure(
        client_ip=get_client_ip(request),
        username=username
    )

    # Emit event
    self.emit(
        EventType.AUTH_LOGIN_FAILURE,
        request=request,
        outcome=Outcome.FAILURE,
        action="Login attempt failed",
        context={
            "username_attempted": username,
            "anomaly_detected": detection.detected,
            "anomaly_reason": detection.reason,
        },
        error=reason,
        risk_score=50 if detection.detected else None  # Boost risk if anomaly
    )

    return detection
```

### 5.4 Tests

**File:** `rail_django/tests/unit/security/test_anomaly.py`

```python
import pytest
from unittest.mock import Mock, patch
from rail_django.security.anomaly.detector import AnomalyDetector, DetectionResult
from rail_django.security.anomaly.backends.redis import RedisAnomalyBackend


class MockRedisBackend:
    def __init__(self):
        self.counters = {}
        self.blocked = set()

    def increment_counter(self, key, window_seconds=300, max_entries=1000):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key], False

    def get_counter(self, key, window_seconds=300):
        return self.counters.get(key, 0)

    def is_blocked(self, key):
        return key in self.blocked

    def block(self, key, duration_seconds=3600):
        self.blocked.add(key)

    def unblock(self, key):
        self.blocked.discard(key)


@pytest.mark.unit
class TestAnomalyDetector:
    def test_login_failure_below_threshold(self):
        backend = MockRedisBackend()
        detector = AnomalyDetector(backend=backend)
        detector.login_failure_ip_threshold = 10

        result = detector.check_login_failure("1.2.3.4")

        assert result.detected is False
        assert result.count == 1

    def test_login_failure_exceeds_threshold(self):
        backend = MockRedisBackend()
        detector = AnomalyDetector(backend=backend)
        detector.login_failure_ip_threshold = 3
        detector.auto_block_enabled = True

        # Simulate multiple failures
        for _ in range(2):
            detector.check_login_failure("1.2.3.4")

        result = detector.check_login_failure("1.2.3.4")

        assert result.detected is True
        assert result.reason == "ip_threshold_exceeded"
        assert result.should_block is True

    def test_blocked_ip_detected(self):
        backend = MockRedisBackend()
        backend.blocked.add("ip:1.2.3.4")
        detector = AnomalyDetector(backend=backend)

        result = detector.check_login_failure("1.2.3.4")

        assert result.detected is True
        assert result.reason == "ip_blocked"

    def test_user_threshold_separate_from_ip(self):
        backend = MockRedisBackend()
        detector = AnomalyDetector(backend=backend)
        detector.login_failure_ip_threshold = 100  # High IP threshold
        detector.login_failure_user_threshold = 3  # Low user threshold

        for _ in range(3):
            detector.check_login_failure("1.2.3.4", username="admin")

        result = detector.check_login_failure("5.6.7.8", username="admin")

        assert result.detected is True
        assert result.reason == "user_threshold_exceeded"
```

---

## Phase 6: Middleware Integration

**Objective:** Update existing middleware to use the new security system.

### 6.1 Update Authentication Middleware

**File:** `rail_django/middleware/auth.py` (update existing)

```python
from rail_django.security import security
from rail_django.security.events.types import EventType, Outcome
from rail_django.security.anomaly.detector import get_anomaly_detector


class GraphQLAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if IP is blocked
        detector = get_anomaly_detector()
        client_ip = request.META.get("REMOTE_ADDR", "unknown")

        if detector.is_ip_blocked(client_ip):
            security.emit(
                EventType.AUTH_TOKEN_INVALID,
                request=request,
                outcome=Outcome.BLOCKED,
                action="Request blocked: IP in blocklist",
            )
            from django.http import JsonResponse
            return JsonResponse(
                {"errors": [{"message": "Access denied"}]},
                status=403
            )

        response = self.get_response(request)
        return response
```

### 6.2 Update GraphQL Security Middleware

**File:** `rail_django/security/graphql/middleware.py` (update existing)

Add at the end of `resolve` method when blocking queries:

```python
from rail_django.security import security
from rail_django.security.events.types import EventType, Outcome

# When blocking a query due to depth/complexity:
security.emit(
    EventType.QUERY_BLOCKED_COMPLEXITY,
    request=info.context.request,
    outcome=Outcome.BLOCKED,
    action=f"Query blocked: complexity {calculated} > {max_allowed}",
    context={
        "query_complexity": calculated,
        "max_allowed": max_allowed,
        "operation_name": info.operation.name.value if info.operation.name else None,
    }
)
```

### 6.3 Update RBAC Evaluation

**File:** `rail_django/security/rbac/evaluation.py` (update existing)

In permission check methods, add:

```python
from rail_django.security import security
from rail_django.security.events.types import EventType, Outcome

# When permission is denied:
security.emit(
    EventType.AUTHZ_PERMISSION_DENIED,
    request=request,
    outcome=Outcome.DENIED,
    action=f"Permission denied: {permission} on {resource}",
    resource_type="permission",
    resource_name=permission,
    context={"required_roles": required_roles, "user_roles": user_roles}
)
```

---

## Phase 7: Delete Old Code & Migration

**Objective:** Remove all deprecated audit/logging code and update all usages to the new security API.

### 7.1 Delete Old Audit Code

**Delete entire directories:**

```bash
# Delete old security/audit module (duplicates extensions/audit)
rm -rf rail_django/security/audit/

# Delete old audit logger package
rm -rf rail_django/extensions/audit/logger/

# Delete deprecated facade
rm -f rail_django/extensions/audit/logger.py
```

**Files to delete:**

| Path | Reason |
|------|--------|
| `rail_django/security/audit/__init__.py` | Duplicate of extensions/audit |
| `rail_django/security/audit/types.py` | Replaced by `security/events/types.py` |
| `rail_django/security/audit/utils.py` | Replaced by `security/events/bus.py` |
| `rail_django/security/audit/logger.py` | Replaced by `security/api.py` |
| `rail_django/security/audit/decorators.py` | Replaced by `security/decorators.py` |
| `rail_django/extensions/audit/logger.py` | Deprecated facade |
| `rail_django/extensions/audit/logger/__init__.py` | Old logger package |
| `rail_django/extensions/audit/logger/base.py` | Replaced by EventBus + sinks |
| `rail_django/extensions/audit/logger/loggers.py` | Replaced by security.emit() |
| `rail_django/extensions/audit/logger/utils.py` | Replaced by EventRedactor |
| `rail_django/extensions/audit/types.py` | Replaced by `security/events/types.py` |

### 7.2 Keep & Update These Files

```
rail_django/extensions/audit/
├── __init__.py     # Update: minimal exports for model access
├── models.py       # KEEP: AuditEventModel (used by DatabaseSink)
├── graphql.py      # Update: use new event types
└── views.py        # Move to rail_django/views/audit_views.py
```

**File:** `rail_django/extensions/audit/__init__.py` (replace contents)

```python
"""
Audit extension - provides AuditEventModel for storing security events.

For logging events, use the security API:

    from rail_django.security import security, EventType
    security.emit(EventType.AUTH_LOGIN_SUCCESS, request=request)
"""

from .models import AuditEventModel, get_audit_event_model

__all__ = ["AuditEventModel", "get_audit_event_model"]
```

### 7.3 Find & Replace All Usages

Run these searches to find all code that needs updating:

```bash
# Find all imports of old audit logger
grep -rn "from rail_django.extensions.audit.logger" rail_django/
grep -rn "from rail_django.security.audit" rail_django/
grep -rn "audit_logger" rail_django/
grep -rn "log_audit_event" rail_django/
grep -rn "log_authentication_event" rail_django/
grep -rn "AuditEvent(" rail_django/
grep -rn "AuditEventType\." rail_django/
grep -rn "AuditSeverity\." rail_django/
```

**Migration mapping:**

| Old Code | New Code |
|----------|----------|
| `from rail_django.extensions.audit.logger import audit_logger` | `from rail_django.security import security` |
| `from rail_django.security.audit import AuditLogger` | `from rail_django.security import security` |
| `audit_logger.log_event(event)` | `security.emit(EventType.X, ...)` |
| `audit_logger.log_login_attempt(req, user, True)` | `security.auth_success(req, user.id, user.username)` |
| `audit_logger.log_login_attempt(req, user, False, err)` | `security.auth_failure(req, username, err)` |
| `audit_logger.log_rate_limit_exceeded(req, type)` | `security.rate_limited(req, type)` |
| `audit_logger.log_suspicious_activity(req, type, details)` | `security.emit(EventType.SYSTEM_ERROR, request=req, context=details)` |
| `AuditEvent(event_type=AuditEventType.X, ...)` | `security.emit(EventType.X, ...)` |
| `AuditEventType.LOGIN_SUCCESS` | `EventType.AUTH_LOGIN_SUCCESS` |
| `AuditEventType.LOGIN_FAILURE` | `EventType.AUTH_LOGIN_FAILURE` |
| `AuditEventType.PERMISSION_DENIED` | `EventType.AUTHZ_PERMISSION_DENIED` |
| `AuditEventType.SENSITIVE_DATA_ACCESS` | `EventType.DATA_SENSITIVE_ACCESS` |
| `AuditEventType.RATE_LIMITED` | `EventType.RATE_LIMIT_EXCEEDED` |
| `AuditSeverity.LOW` | `Severity.INFO` |
| `AuditSeverity.MEDIUM` | `Severity.WARNING` |
| `AuditSeverity.HIGH` | `Severity.ERROR` |
| `AuditSeverity.CRITICAL` | `Severity.CRITICAL` |

### 7.4 Update Specific Files

**File:** `rail_django/middleware/auth.py`

```python
# OLD
from rail_django.extensions.audit.logger import audit_logger
audit_logger.log_login_attempt(request, user, success=True)

# NEW
from rail_django.security import security
security.auth_success(request, user.id, user.username)
```

**File:** `rail_django/security/rbac/evaluation.py`

```python
# OLD
from rail_django.security.audit import AuditLogger
# ... complex logging

# NEW
from rail_django.security import security, EventType, Outcome
security.emit(
    EventType.AUTHZ_PERMISSION_DENIED,
    request=request,
    outcome=Outcome.DENIED,
    resource_type="permission",
    resource_name=permission_name,
)
```

**File:** `rail_django/security/graphql/middleware.py`

```python
# OLD
# No logging when blocking queries

# NEW
from rail_django.security import security, EventType, Outcome

# When blocking a query:
security.emit(
    EventType.QUERY_BLOCKED_COMPLEXITY,
    request=info.context.request,
    outcome=Outcome.BLOCKED,
    context={"complexity": score, "max_allowed": limit}
)
```

### 7.5 Update Dashboard Views

**File:** `rail_django/views/audit_views.py`

```python
"""Audit dashboard views using new security event structure."""

from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views import View
from rail_django.extensions.audit.models import get_audit_event_model
from rail_django.security.events.types import EventType, Severity, Outcome


class AuditDashboardView(TemplateView):
    template_name = "audit_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        AuditEvent = get_audit_event_model()

        # Recent events
        context["recent_events"] = AuditEvent.objects.order_by("-timestamp")[:50]

        # Security summary
        from django.utils import timezone
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=24)

        events = AuditEvent.objects.filter(timestamp__gte=since)
        context["stats"] = {
            "total": events.count(),
            "auth_failures": events.filter(
                event_type=EventType.AUTH_LOGIN_FAILURE.value
            ).count(),
            "blocked_queries": events.filter(
                event_type__startswith="query.blocked"
            ).count(),
            "permission_denied": events.filter(
                event_type=EventType.AUTHZ_PERMISSION_DENIED.value
            ).count(),
        }

        return context


class AuditAPIView(View):
    """REST API for audit event queries."""

    def get(self, request):
        AuditEvent = get_audit_event_model()
        qs = AuditEvent.objects.all()

        # Filter by correlation_id
        correlation_id = request.GET.get("correlation_id")
        if correlation_id:
            qs = qs.filter(additional_data__correlation_id=correlation_id)

        # Filter by event type
        event_type = request.GET.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        # Filter by outcome (in additional_data)
        outcome = request.GET.get("outcome")
        if outcome:
            qs = qs.filter(additional_data__outcome=outcome)

        # Filter by severity
        severity = request.GET.get("severity")
        if severity:
            qs = qs.filter(severity=severity)

        # Filter by user
        user_id = request.GET.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Filter by IP
        client_ip = request.GET.get("client_ip")
        if client_ip:
            qs = qs.filter(client_ip=client_ip)

        # Date range
        from django.utils import timezone
        from datetime import timedelta

        hours = int(request.GET.get("hours", 24))
        since = timezone.now() - timedelta(hours=hours)
        qs = qs.filter(timestamp__gte=since)

        # Pagination
        limit = min(int(request.GET.get("limit", 100)), 1000)
        offset = int(request.GET.get("offset", 0))

        events = qs.order_by("-timestamp")[offset:offset + limit]

        return JsonResponse({
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "timestamp": e.timestamp.isoformat(),
                    "user_id": e.user_id,
                    "username": e.username,
                    "client_ip": e.client_ip,
                    "correlation_id": e.additional_data.get("correlation_id"),
                    "outcome": e.additional_data.get("outcome"),
                    "action": e.additional_data.get("action"),
                    "resource": e.additional_data.get("resource"),
                    "risk_score": e.additional_data.get("risk_score", 0),
                }
                for e in events
            ],
            "total": qs.count(),
            "limit": limit,
            "offset": offset,
        })


class SecurityReportView(View):
    """Generate security reports."""

    def get(self, request):
        from django.db.models import Count
        from django.utils import timezone
        from datetime import timedelta

        AuditEvent = get_audit_event_model()
        hours = int(request.GET.get("hours", 24))
        since = timezone.now() - timedelta(hours=hours)

        events = AuditEvent.objects.filter(timestamp__gte=since)

        # Top IPs with failures
        top_failed_ips = list(
            events.filter(event_type__in=[
                EventType.AUTH_LOGIN_FAILURE.value,
                EventType.RATE_LIMIT_EXCEEDED.value,
            ])
            .values("client_ip")
            .annotate(count=Count("client_ip"))
            .order_by("-count")[:10]
        )

        # Top blocked queries
        blocked_queries = list(
            events.filter(event_type__startswith="query.blocked")
            .values("event_type")
            .annotate(count=Count("event_type"))
            .order_by("-count")
        )

        # High risk events (risk_score in additional_data)
        high_risk_events = events.filter(
            additional_data__risk_score__gte=50
        ).count()

        return JsonResponse({
            "period_hours": hours,
            "total_events": events.count(),
            "summary": {
                "auth_failures": events.filter(
                    event_type=EventType.AUTH_LOGIN_FAILURE.value
                ).count(),
                "auth_successes": events.filter(
                    event_type=EventType.AUTH_LOGIN_SUCCESS.value
                ).count(),
                "permission_denied": events.filter(
                    event_type=EventType.AUTHZ_PERMISSION_DENIED.value
                ).count(),
                "queries_blocked": events.filter(
                    event_type__startswith="query.blocked"
                ).count(),
                "rate_limited": events.filter(
                    event_type=EventType.RATE_LIMIT_EXCEEDED.value
                ).count(),
                "high_risk_events": high_risk_events,
            },
            "top_failed_ips": top_failed_ips,
            "blocked_queries_by_type": blocked_queries,
        })
```

### 7.6 Update Tests

Delete old test files:

```bash
rm -rf rail_django/tests/unit/extensions/audit/
rm -rf rail_django/tests/unit/security/audit/
rm -rf rail_django/tests/integration/audit/
```

Update any tests that import old audit APIs to use new security API.

### 7.7 Verification Script

Create a script to verify all old code is removed:

**File:** `scripts/verify_audit_migration.py`

```python
#!/usr/bin/env python
"""Verify all old audit code has been removed and migrated."""

import subprocess
import sys

PATTERNS_SHOULD_NOT_EXIST = [
    "from rail_django.extensions.audit.logger",
    "from rail_django.security.audit",
    "import AuditLogger",
    "AuditEventType\\.",
    "AuditSeverity\\.",
    "audit_logger\\.",
    "log_audit_event\\(",
    "log_authentication_event\\(",
]

PATHS_SHOULD_NOT_EXIST = [
    "rail_django/security/audit/",
    "rail_django/extensions/audit/logger/",
    "rail_django/extensions/audit/logger.py",
    "rail_django/extensions/audit/types.py",
]

def check_patterns():
    errors = []
    for pattern in PATTERNS_SHOULD_NOT_EXIST:
        result = subprocess.run(
            ["grep", "-rn", pattern, "rail_django/"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            errors.append(f"Found deprecated pattern '{pattern}':\n{result.stdout}")
    return errors

def check_paths():
    import os
    errors = []
    for path in PATHS_SHOULD_NOT_EXIST:
        if os.path.exists(path):
            errors.append(f"Path should be deleted: {path}")
    return errors

def main():
    print("Verifying audit migration...")

    errors = check_patterns() + check_paths()

    if errors:
        print("\n❌ Migration incomplete:\n")
        for error in errors:
            print(f"  - {error}\n")
        sys.exit(1)
    else:
        print("✅ Migration complete - all old code removed")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

### 7.8 Final Directory Structure

After cleanup, the audit-related code should look like:

```
rail_django/
├── security/
│   ├── __init__.py          # Exports: security, EventType, Outcome, etc.
│   ├── api.py                # SecurityAPI facade
│   ├── context.py            # SecurityContext
│   ├── decorators.py         # @audit decorator
│   ├── events/
│   │   ├── __init__.py
│   │   ├── types.py          # SecurityEvent, EventType, Severity, Outcome
│   │   ├── builder.py        # EventBuilder
│   │   ├── bus.py            # EventBus, EventRedactor
│   │   └── sinks/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── database.py
│   │       ├── file.py
│   │       ├── webhook.py
│   │       └── metrics.py
│   ├── anomaly/
│   │   ├── __init__.py
│   │   ├── detector.py
│   │   └── backends/
│   │       ├── __init__.py
│   │       └── redis.py
│   ├── middleware/
│   │   └── context.py
│   ├── rbac/                  # Existing (unchanged)
│   ├── validation/            # Existing (unchanged)
│   ├── field_permissions/     # Existing (unchanged)
│   └── graphql/               # Existing (updated to emit events)
│
├── extensions/
│   └── audit/
│       ├── __init__.py        # Minimal: exports model only
│       ├── models.py          # AuditEventModel (database storage)
│       └── graphql.py         # GraphQL types for querying audit
│
└── views/
    └── audit_views.py         # Dashboard views (updated)
```

**Deleted:**
- `rail_django/security/audit/` (entire directory)
- `rail_django/extensions/audit/logger/` (entire directory)
- `rail_django/extensions/audit/logger.py`
- `rail_django/extensions/audit/types.py`

---

## Phase 8: Configuration & Documentation

### 8.1 Settings Reference

**File:** `rail_django/conf/framework_settings.py` (update)

```python
# Security Event Bus
SECURITY_EVENT_ASYNC = True  # Process events in background thread
SECURITY_METRICS_ENABLED = False  # Enable Prometheus metrics sink

# Audit Storage
AUDIT_STORE_IN_DATABASE = True
AUDIT_STORE_IN_FILE = True
AUDIT_WEBHOOK_URL = None  # e.g., "https://siem.example.com/webhook"
AUDIT_RETENTION_DAYS = 90

# Redaction
AUDIT_REDACTION_FIELDS = [
    "password", "token", "secret", "key", "credential",
    "authorization", "ssn", "credit_card", "cvv",
]
AUDIT_REDACTION_MASK = "***REDACTED***"

# Anomaly Detection (requires Redis)
SECURITY_REDIS_URL = None  # e.g., "redis://localhost:6379/0"
SECURITY_REDIS_PREFIX = "rail:security:"
SECURITY_ANOMALY_THRESHOLDS = {
    "login_failure_per_ip": 10,
    "login_failure_per_user": 5,
    "login_failure_window": 300,  # seconds
    "rate_limit_per_ip": 100,
    "rate_limit_window": 60,
    "auto_block_enabled": True,
    "block_duration": 3600,  # seconds
}
```

### 8.2 Documentation

**File:** `docs/reference/security-events.md` (create)

```markdown
# Security Events System

## Overview

Rail Django provides a unified security event system for audit logging,
anomaly detection, and observability.

## Quick Start

```python
from rail_django.security import security, EventType, Outcome

# Log a custom event
security.emit(
    EventType.DATA_READ,
    request=request,
    resource_type="model",
    resource_name="User",
    resource_id="123"
)

# Use convenience methods
security.auth_failure(request, username="admin", reason="Invalid password")
security.permission_denied(request, "model", "SensitiveData", "read")
security.query_blocked(request, "complexity", {"score": 150, "max": 100})
```

## Event Types

| Category | Event Type | Description |
|----------|------------|-------------|
| auth | AUTH_LOGIN_SUCCESS | Successful login |
| auth | AUTH_LOGIN_FAILURE | Failed login attempt |
| authz | AUTHZ_PERMISSION_DENIED | Access denied |
| data | DATA_SENSITIVE_ACCESS | Sensitive field accessed |
| query | QUERY_BLOCKED_COMPLEXITY | Query rejected |
| rate | RATE_LIMIT_EXCEEDED | Rate limit hit |

## Anomaly Detection

Requires Redis for distributed counting:

```python
SECURITY_REDIS_URL = "redis://localhost:6379/0"
```

Automatically detects:
- Brute force login attempts (per IP and per user)
- Rate limit violations
- Auto-blocks offending IPs

## Custom Sinks

```python
from rail_django.security.events.sinks.base import EventSink
from rail_django.security.events.bus import get_event_bus

class SlackSink(EventSink):
    def write(self, event):
        if event.severity.value in ("error", "critical"):
            send_slack_alert(event.to_dict())

get_event_bus().add_sink(SlackSink())
```
```

---

## Execution Checklist

### Phase 1: Security Context
- [x] Create `rail_django/security/context.py`
- [x] Create `rail_django/security/middleware/context.py`
- [x] Update settings template with middleware
- [x] Write tests for context

### Phase 2: Event Types
- [x] Create `rail_django/security/events/types.py`
- [x] Create `rail_django/security/events/builder.py`
- [x] Write tests for events

### Phase 3: Event Bus & Sinks
- [x] Create `rail_django/security/events/sinks/base.py`
- [x] Create `rail_django/security/events/sinks/database.py`
- [x] Create `rail_django/security/events/sinks/file.py`
- [x] Create `rail_django/security/events/sinks/webhook.py`
- [x] Create `rail_django/security/events/sinks/metrics.py`
- [x] Create `rail_django/security/events/bus.py`
- [x] Write tests for bus and sinks

### Phase 4: Public API
- [x] Create `rail_django/security/api.py`
- [x] Update `rail_django/security/__init__.py`
- [x] Create `rail_django/security/decorators.py`
- [x] Write tests for API

### Phase 5: Anomaly Detection
- [x] Create `rail_django/security/anomaly/backends/redis.py`
- [x] Create `rail_django/security/anomaly/detector.py`
- [x] Update security API with anomaly integration
- [x] Write tests for anomaly detection

### Phase 6: Middleware Integration
- [x] Update authentication middleware
- [x] Update GraphQL security middleware
- [x] Update RBAC evaluation
- [x] Integration tests

### Phase 7: Migration
- [x] Delete old audit code and directories
- [x] Update dashboard views
- [x] Create and run verification script
- [x] Update imports across codebase

### Phase 8: Documentation
- [x] Update framework settings
- [x] Create security-events.md
- [x] Update CLAUDE.md with new patterns

---

## Dependencies

### Required
- Django 4.2+
- Python 3.11+

### Optional (for full features)
- `redis` - Anomaly detection
- `prometheus_client` - Metrics export
- `requests` - Webhook sink

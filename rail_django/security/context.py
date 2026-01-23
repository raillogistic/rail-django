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

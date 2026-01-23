from typing import Optional, Any
from django.http import HttpRequest
from .events.types import SecurityEvent, EventType, Severity, Outcome, Resource
from .events.builder import event, EventBuilder
from .events.bus import get_event_bus
from .context import SecurityContext
from .middleware.context import get_security_context


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
    ) -> Any:  # Returns DetectionResult but typed Any to avoid circular imports
        """Log failed authentication attempt."""
        from .anomaly.detector import get_anomaly_detector
        from .context import get_client_ip

        # Check for brute force
        detector = get_anomaly_detector()
        detection = detector.check_login_failure(
            client_ip=get_client_ip(request),
            username=username
        )

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

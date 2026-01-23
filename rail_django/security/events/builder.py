from typing import Optional
from django.http import HttpRequest
from .types import (
    SecurityEvent, EventType, Severity, Outcome, Resource,
    DEFAULT_SEVERITY, DEFAULT_RISK_SCORES
)
from ..context import SecurityContext
from ..middleware.context import get_security_context


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

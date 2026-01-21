"""
Internal utility functions for security audit.
"""

import hashlib
from enum import Enum
from typing import Any, Optional
from django.db import models
from .types import AuditEventType, AuditSeverity


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum): return value.value
    if isinstance(value, dict): return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list): return [_json_safe(i) for i in value]
    return value


def _resolve_request(context: Any) -> Optional[Any]:
    if context is None: return None
    if hasattr(context, "META") and hasattr(context, "method"): return context
    return getattr(context, "request", None)


def _resolve_user(context: Any, request: Any) -> Optional[Any]:
    user = getattr(context, "user", None)
    if user is not None: return user
    return getattr(request, "user", None) if request is not None else None


def _snapshot_instance_fields(instance: models.Model) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field in getattr(instance._meta, "concrete_fields", []):
        try:
            if field.is_relation and (field.many_to_one or field.one_to_one): snapshot[field.name] = getattr(instance, field.attname, None)
            else: snapshot[field.name] = getattr(instance, field.name, None)
        except Exception: snapshot[field.name] = None
    return snapshot


def _classify_exception(exc: Exception):
    message = str(exc).lower()
    if isinstance(exc, PermissionError): return AuditEventType.PERMISSION_DENIED, AuditSeverity.WARNING
    if "rate limit" in message: return AuditEventType.RATE_LIMIT_EXCEEDED, AuditSeverity.WARNING
    if "introspection" in message: return AuditEventType.INTROSPECTION_ATTEMPT, AuditSeverity.WARNING
    if any(p in message for p in ["permission", "authentication", "not permitted"]): return AuditEventType.PERMISSION_DENIED, AuditSeverity.WARNING
    return AuditEventType.SYSTEM_ERROR, AuditSeverity.ERROR


def get_client_ip(request) -> Optional[str]:
    """RÇ¸cupÇºre l'adresse IP du client."""
    if not request: return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0] if x_forwarded_for else request.META.get("REMOTE_ADDR")


def hash_query(operation) -> str:
    """GÇ¸nÇºre un hash pour une opÇ¸ration GraphQL."""
    if not operation: return ""
    return hashlib.sha256(str(operation).encode()).hexdigest()[:16]

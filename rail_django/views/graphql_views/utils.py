"""
Helper functions for GraphQL views.
"""

from typing import Any, Optional

from django.conf import settings
from django.http import HttpRequest


def _normalize_host(host: str) -> str:
    if not host:
        return ""
    host = str(host).strip().lower()
    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[1:end]
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host


def _get_request_host(request: HttpRequest) -> str:
    meta = getattr(request, "META", {}) or {}
    host = meta.get("HTTP_HOST") or meta.get("SERVER_NAME") or ""
    if host:
        return _normalize_host(host)
    getter = getattr(request, "get_host", None)
    if callable(getter):
        try:
            return _normalize_host(getter())
        except Exception:
            pass
    return ""


def _get_request_ip(request: HttpRequest) -> str:
    meta = getattr(request, "META", {}) or {}
    forwarded_for = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return meta.get("REMOTE_ADDR", "") or ""


def _host_allowed(request: HttpRequest, allowed_hosts: list[str]) -> bool:
    if not allowed_hosts:
        return True
    normalized = {_normalize_host(host) for host in allowed_hosts if host}
    if not normalized:
        return True
    host = _get_request_host(request)
    if host in normalized:
        return True
    client_ip = _get_request_ip(request)
    if client_ip and _normalize_host(client_ip) in normalized:
        return True
    return False


def _get_authenticated_user(request: HttpRequest):
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user
    try:
        from django.contrib.auth import get_user
    except Exception:
        return None
    try:
        session_user = get_user(request)
    except Exception:
        return None
    if session_user and getattr(session_user, "is_authenticated", False):
        return session_user
    return None


def _get_effective_schema_settings(
    schema_info: dict[str, Any]
) -> dict[str, Any]:
    """Resolve schema settings using defaults plus schema overrides."""
    schema_settings = getattr(schema_info, "settings", {}) or {}
    try:
        from dataclasses import asdict
        from ...core.settings import SchemaSettings

        resolved_settings = asdict(SchemaSettings.from_schema(schema_info.name))
        return {**resolved_settings, **schema_settings}
    except Exception:
        return schema_settings

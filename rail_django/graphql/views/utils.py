"""
Utility functions and exceptions for GraphQL views.

This module contains helper functions for request handling, host validation,
and authentication that are used by MultiSchemaGraphQLView and SchemaListView.
"""

import logging
from typing import Any, Optional

from django.http import HttpRequest

logger = logging.getLogger(__name__)

# Fields used for GraphQL introspection queries
INTROSPECTION_FIELDS = {"__schema", "__type", "__typename"}


class SchemaRegistryUnavailable(Exception):
    """Raised when the schema registry cannot be accessed."""


def _normalize_host(host: str) -> str:
    """
    Normalize a host string by removing port and converting to lowercase.

    Args:
        host: The host string to normalize (may include port or IPv6 brackets)

    Returns:
        Normalized host string without port, lowercase

    Examples:
        >>> _normalize_host("Example.COM:8080")
        'example.com'
        >>> _normalize_host("[::1]:8080")
        '::1'
    """
    if not host:
        return ""
    host = str(host).strip().lower()
    # Handle IPv6 addresses in brackets
    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[1:end]
    # Remove port from host:port format
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host


def _get_request_host(request: HttpRequest) -> str:
    """
    Extract and normalize the host from an HTTP request.

    Attempts to get the host from HTTP_HOST, SERVER_NAME, or request.get_host().

    Args:
        request: Django HTTP request object

    Returns:
        Normalized host string, or empty string if not available
    """
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
    """
    Extract the client IP address from an HTTP request.

    Handles X-Forwarded-For header for proxied requests.

    Args:
        request: Django HTTP request object

    Returns:
        Client IP address string, or empty string if not available
    """
    meta = getattr(request, "META", {}) or {}
    forwarded_for = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return meta.get("REMOTE_ADDR", "") or ""


def _host_allowed(request: HttpRequest, allowed_hosts: list[str]) -> bool:
    """
    Check if the request originates from an allowed host.

    Args:
        request: Django HTTP request object
        allowed_hosts: List of allowed host patterns

    Returns:
        True if host is allowed or list is empty, False otherwise
    """
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


def _get_authenticated_user(request: HttpRequest) -> Optional[object]:
    """
    Get the authenticated user from a request.

    Attempts to get the user from request.user or Django session.

    Args:
        request: Django HTTP request object

    Returns:
        Authenticated user object, or None if not authenticated
    """
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


def _get_effective_schema_settings(schema_info: dict[str, Any]) -> dict[str, Any]:
    """Resolve schema settings using defaults plus schema overrides."""
    schema_settings = getattr(schema_info, "settings", {}) or {}
    try:
        from dataclasses import asdict
        from rail_django.core.settings import SchemaSettings

        resolved_settings = asdict(SchemaSettings.from_schema(schema_info.name))
        return {**resolved_settings, **schema_settings}
    except Exception:
        return schema_settings

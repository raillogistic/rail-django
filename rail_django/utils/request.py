"""
Request utilities for Rail Django.

This module provides helpers for resolving authenticated users from requests.
"""

from typing import Any, Callable, Optional

from django.http import HttpRequest


def resolve_request_user(
    request: HttpRequest,
    *,
    get_user_from_token: Optional[Callable[[str], Any]] = None,
) -> Any:
    """
    Resolve a user from the request session or Authorization header.

    Args:
        request: The Django request.
        get_user_from_token: Optional callback to resolve a user from a token.

    Returns:
        The authenticated user or None.
    """
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user

    if not get_user_from_token:
        return user

    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header and (
        auth_header.startswith("Bearer ") or auth_header.startswith("Token ")
    ):
        parts = auth_header.split(" ", 1)
        if len(parts) == 2:
            token = parts[1].strip()
            if token:
                try:
                    fallback_user = get_user_from_token(token)
                except Exception:
                    fallback_user = None
                if fallback_user and getattr(fallback_user, "is_authenticated", False):
                    request.user = fallback_user
                    return fallback_user

    return user


__all__ = ["resolve_request_user"]

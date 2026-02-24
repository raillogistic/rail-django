"""
Internal utility functions for authentication middleware.
"""

from django.conf import settings
from django.http import HttpRequest

from ...utils.network import is_trusted_proxy


def _get_anonymous_user():
    """Lazily import AnonymousUser."""
    from django.contrib.auth.models import AnonymousUser

    return AnonymousUser()


def get_client_ip(request: HttpRequest) -> str:
    """Resolve client IP with trusted-proxy awareness."""
    raw = getattr(settings, "RAIL_DJANGO_TRUSTED_PROXIES", [])
    if raw is None:
        trusted_proxies: list[str] = []
    elif isinstance(raw, (list, tuple, set)):
        trusted_proxies = [str(proxy).strip() for proxy in raw if str(proxy).strip()]
    else:
        value = str(raw).strip()
        trusted_proxies = [value] if value else []

    remote_addr = (request.META.get("REMOTE_ADDR", "") or "").strip()
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR", "") or "").strip()
    real_ip = (request.META.get("HTTP_X_REAL_IP", "") or "").strip()

    if (
        remote_addr
        and trusted_proxies
        and is_trusted_proxy(remote_addr, trusted_proxies)
    ):
        if forwarded_for:
            candidate = forwarded_for.split(",", 1)[0].strip()
            if candidate:
                return candidate
        if real_ip:
            return real_ip

    if remote_addr:
        return remote_addr
    if real_ip:
        return real_ip
    return "Unknown"

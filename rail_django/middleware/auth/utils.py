"""
Internal utility functions for authentication middleware.
"""

from typing import Any, Optional
from django.http import HttpRequest

def _get_anonymous_user():
    """Lazily import AnonymousUser."""
    from django.contrib.auth.models import AnonymousUser
    return AnonymousUser()


def get_client_ip(request: HttpRequest) -> str:
    """RÇ¸cupÇºre l'adresse IP du client en tenant compte des proxies."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for: return forwarded_for.split(",")[0].strip()
    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip: return real_ip
    return request.META.get("REMOTE_ADDR", "Unknown")

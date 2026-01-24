"""
Network utilities for Rail Django.

This module provides helpers for IP handling and rate limit identifiers.
"""

import ipaddress
from typing import Iterable


def is_trusted_proxy(remote_addr: str, trusted_proxies: Iterable[str]) -> bool:
    """Check if the remote address is in the trusted proxy list."""
    if not remote_addr:
        return False
    for proxy in trusted_proxies:
        proxy = str(proxy).strip()
        if not proxy:
            continue
        if "/" in proxy:
            try:
                if ipaddress.ip_address(remote_addr) in ipaddress.ip_network(
                    proxy, strict=False
                ):
                    return True
            except ValueError:
                continue
        if remote_addr == proxy:
            return True
    return False


def get_rate_limit_identifier(request, trusted_proxies: Iterable[str]) -> str:
    """Resolve a rate limit identifier for the request."""
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return f"user:{user.id}"

    remote_addr = request.META.get("REMOTE_ADDR", "")
    ip_address = remote_addr or "unknown"
    if is_trusted_proxy(remote_addr, trusted_proxies):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()

    return f"ip:{ip_address}"


__all__ = ["get_rate_limit_identifier", "is_trusted_proxy"]

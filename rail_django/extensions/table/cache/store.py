"""Simple in-memory cache store."""

from __future__ import annotations

from time import time

_cache: dict[str, tuple[float, object]] = {}


def set_cache(key: str, value: object, ttl_seconds: int = 60) -> None:
    _cache[key] = (time() + ttl_seconds, value)


def get_cache(key: str):
    hit = _cache.get(key)
    if not hit:
        return None
    expires_at, value = hit
    if expires_at < time():
        _cache.pop(key, None)
        return None
    return value


def clear_cache_prefix(prefix: str) -> None:
    for key in [k for k in _cache if k.startswith(prefix)]:
        _cache.pop(key, None)

"""
Lightweight query cache hooks for GraphQL resolvers.

Caching is opt-in and disabled unless a backend is registered via
rail_django.core.services.set_query_cache_factory.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional


class InMemoryQueryCacheBackend:
    """Simple in-memory cache backend for tests or local development."""

    def __init__(self, default_timeout: int = 300):
        self.default_timeout = default_timeout
        self._lock = threading.RLock()
        self._store: Dict[str, Dict[str, Any]] = {}
        self._versions: Dict[str, str] = {}

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at = entry.get("expires_at")
            if expires_at is not None and expires_at <= time.time():
                self._store.pop(key, None)
                return None
            return entry.get("value")

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        resolved_timeout = self.default_timeout if timeout is None else timeout
        expires_at = None
        if resolved_timeout and resolved_timeout > 0:
            expires_at = time.time() + resolved_timeout
        with self._lock:
            self._store[key] = {"value": value, "expires_at": expires_at}

    def get_version(self, namespace: str) -> str:
        with self._lock:
            version = self._versions.get(namespace)
            if version:
                return version
            version = _new_version()
            self._versions[namespace] = version
            return version

    def bump_version(self, namespace: str) -> str:
        version = _new_version()
        with self._lock:
            self._versions[namespace] = version
        return version


def _new_version() -> str:
    return uuid.uuid4().hex

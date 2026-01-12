"""
Persisted query support (APQ-style) with optional allowlist enforcement.

This module is opt-in and only active when enabled in persisted_query_settings.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Optional, Set, Tuple

from django.core.cache import caches

from ..config_proxy import get_setting


PERSISTED_QUERY_NOT_FOUND = "PERSISTED_QUERY_NOT_FOUND"
PERSISTED_QUERY_NOT_ALLOWED = "PERSISTED_QUERY_NOT_ALLOWED"
PERSISTED_QUERY_HASH_MISMATCH = "PERSISTED_QUERY_HASH_MISMATCH"
PERSISTED_QUERY_DISABLED = "PERSISTED_QUERY_DISABLED"


@dataclass(frozen=True)
class PersistedQuerySettings:
    enabled: bool
    cache_alias: str
    ttl: int
    allow_unregistered: bool
    enforce_allowlist: bool
    allowlist: Dict[str, str]
    allowlist_hashes: Set[str]
    hash_algorithm: str
    max_query_length: int


@dataclass(frozen=True)
class PersistedQueryResolution:
    query: Optional[str]
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def has_error(self) -> bool:
        return bool(self.error_code)


class PersistedQueryStore:
    """Cache-backed store for persisted queries."""

    def __init__(self, cache_alias: str, default_ttl: int):
        self.cache_alias = cache_alias
        self.default_ttl = default_ttl
        self._cache = self._resolve_cache()
        self._fallback_store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _resolve_cache(self):
        try:
            return caches[self.cache_alias]
        except Exception:
            return None

    def get(self, key: str) -> Optional[str]:
        if self._cache is not None:
            return self._cache.get(key)
        with self._lock:
            entry = self._fallback_store.get(key)
            if not entry:
                return None
            expires_at = entry.get("expires_at")
            if expires_at is not None and expires_at <= time.time():
                self._fallback_store.pop(key, None)
                return None
            return entry.get("value")

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        resolved_ttl = self.default_ttl if ttl is None else ttl
        if self._cache is not None:
            self._cache.set(key, value, timeout=resolved_ttl)
            return
        expires_at = None
        if resolved_ttl and resolved_ttl > 0:
            expires_at = time.time() + resolved_ttl
        with self._lock:
            self._fallback_store[key] = {"value": value, "expires_at": expires_at}


_STORE_BY_ALIAS: Dict[str, PersistedQueryStore] = {}


def resolve_persisted_query(
    payload: Dict[str, Any],
    *,
    schema_name: Optional[str] = None,
) -> PersistedQueryResolution:
    settings = _load_settings(schema_name)
    if not settings.enabled:
        return PersistedQueryResolution(
            query=payload.get("query"),
            error_code=None,
            error_message=None,
        )

    extensions = payload.get("extensions") or {}
    persisted = extensions.get("persistedQuery") or {}
    sha = str(persisted.get("sha256Hash") or "").strip()
    if not sha:
        return PersistedQueryResolution(
            query=payload.get("query"),
            error_code=None,
            error_message=None,
        )

    query = payload.get("query")

    if query:
        if settings.max_query_length and len(query) > settings.max_query_length:
            return PersistedQueryResolution(
                query=None,
                error_code=PERSISTED_QUERY_NOT_ALLOWED,
                error_message="Persisted query exceeds max length",
            )

        computed_hash = _hash_query(query, settings.hash_algorithm)
        if computed_hash != sha:
            return PersistedQueryResolution(
                query=None,
                error_code=PERSISTED_QUERY_HASH_MISMATCH,
                error_message="Persisted query hash mismatch",
            )

        if settings.enforce_allowlist and sha not in settings.allowlist_hashes:
            return PersistedQueryResolution(
                query=None,
                error_code=PERSISTED_QUERY_NOT_ALLOWED,
                error_message="Persisted query not allowlisted",
            )

        if settings.allowlist and sha not in settings.allowlist_hashes:
            return PersistedQueryResolution(
                query=None,
                error_code=PERSISTED_QUERY_NOT_ALLOWED,
                error_message="Persisted query not allowlisted",
            )

        if settings.allowlist.get(sha):
            return PersistedQueryResolution(query=settings.allowlist.get(sha))

        if settings.allow_unregistered or not settings.allowlist_hashes:
            _get_store(settings).set(sha, query)
        return PersistedQueryResolution(query=query)

    allowlisted_query = settings.allowlist.get(sha)
    if allowlisted_query:
        return PersistedQueryResolution(query=allowlisted_query)

    stored_query = _get_store(settings).get(sha)
    if stored_query:
        return PersistedQueryResolution(query=stored_query)

    if settings.allowlist_hashes and sha not in settings.allowlist_hashes:
        return PersistedQueryResolution(
            query=None,
            error_code=PERSISTED_QUERY_NOT_ALLOWED,
            error_message="Persisted query not allowlisted",
        )

    return PersistedQueryResolution(
        query=None,
        error_code=PERSISTED_QUERY_NOT_FOUND,
        error_message="Persisted query not found",
    )


def _hash_query(query: str, algorithm: str) -> str:
    algo = (algorithm or "sha256").lower()
    if algo != "sha256":
        algo = "sha256"
    return sha256(query.encode("utf-8")).hexdigest()


def _get_store(settings: PersistedQuerySettings) -> PersistedQueryStore:
    store = _STORE_BY_ALIAS.get(settings.cache_alias)
    if store is None:
        store = PersistedQueryStore(settings.cache_alias, settings.ttl)
        _STORE_BY_ALIAS[settings.cache_alias] = store
    return store


def _load_settings(schema_name: Optional[str]) -> PersistedQuerySettings:
    enabled = bool(
        get_setting("persisted_query_settings.enabled", False, schema_name)
    )
    cache_alias = str(
        get_setting("persisted_query_settings.cache_alias", "default", schema_name)
    )
    ttl = _coerce_int(
        get_setting("persisted_query_settings.ttl", 86400, schema_name),
        default=86400,
    )
    allow_unregistered = bool(
        get_setting("persisted_query_settings.allow_unregistered", True, schema_name)
    )
    enforce_allowlist = bool(
        get_setting("persisted_query_settings.enforce_allowlist", False, schema_name)
    )
    hash_algorithm = str(
        get_setting("persisted_query_settings.hash_algorithm", "sha256", schema_name)
    )
    max_query_length = _coerce_int(
        get_setting("persisted_query_settings.max_query_length", 0, schema_name),
        default=0,
    )

    allowlist_raw = get_setting(
        "persisted_query_settings.allowlist", None, schema_name
    )
    allowlist_path = get_setting(
        "persisted_query_settings.allowlist_path", None, schema_name
    )

    allowlist, allowlist_hashes = _load_allowlist(
        allowlist_raw, allowlist_path
    )

    return PersistedQuerySettings(
        enabled=enabled,
        cache_alias=cache_alias,
        ttl=ttl,
        allow_unregistered=allow_unregistered,
        enforce_allowlist=enforce_allowlist,
        allowlist=allowlist,
        allowlist_hashes=allowlist_hashes,
        hash_algorithm=hash_algorithm,
        max_query_length=max_query_length,
    )


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_allowlist(
    allowlist_raw: Any, allowlist_path: Any
) -> Tuple[Dict[str, str], Set[str]]:
    allowlist: Dict[str, str] = {}
    allowlist_hashes: Set[str] = set()

    def merge_from(value: Any) -> None:
        if isinstance(value, dict):
            for key, query in value.items():
                key_str = str(key).strip()
                if not key_str:
                    continue
                allowlist_hashes.add(key_str)
                if isinstance(query, str) and query.strip():
                    allowlist[key_str] = query
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                key_str = str(item).strip()
                if key_str:
                    allowlist_hashes.add(key_str)

    merge_from(allowlist_raw)

    if allowlist_path:
        try:
            with open(str(allowlist_path), "r", encoding="utf-8") as handle:
                data = json.load(handle)
            merge_from(data)
        except Exception:
            pass

    return allowlist, allowlist_hashes

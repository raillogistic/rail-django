"""
Caching helpers for Form API configuration.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache


def get_form_version(app: str, model: str) -> str:
    """Get a version token for a model's form config."""
    key = f"form_version:{app}:{model}"
    version = cache.get(key)
    if not version:
        version = str(int(time.time() * 1000))
        cache.set(key, version, timeout=None)
    return str(version)


def _make_cache_key(
    app: str,
    model: str,
    *,
    user_id: Optional[str] = None,
    object_id: Optional[str] = None,
    mode: Optional[str] = None,
) -> str:
    version = get_form_version(app, model)
    key = f"form:{version}:{app}:{model}"
    if object_id:
        key = f"{key}:obj:{object_id}"
    if user_id:
        user_hash = hashlib.sha1(str(user_id).encode()).hexdigest()[:8]
        key = f"{key}:user:{user_hash}"
    if mode:
        key = f"{key}:mode:{mode}"
    return key


def get_cached_config(
    app: str,
    model: str,
    *,
    user_id: Optional[str] = None,
    object_id: Optional[str] = None,
    mode: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    if getattr(settings, "DEBUG", False):
        return None
    key = _make_cache_key(app, model, user_id=user_id, object_id=object_id, mode=mode)
    return cache.get(key)


def set_cached_config(
    app: str,
    model: str,
    data: dict[str, Any],
    *,
    user_id: Optional[str] = None,
    object_id: Optional[str] = None,
    mode: Optional[str] = None,
) -> None:
    if getattr(settings, "DEBUG", False):
        return
    key = _make_cache_key(app, model, user_id=user_id, object_id=object_id, mode=mode)
    cache.set(key, data, timeout=3600)


def compute_config_version(payload: dict[str, Any]) -> str:
    """Compute a deterministic hash for a form config payload."""
    def _strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: _strip(v)
                for k, v in obj.items()
                if k not in {"generatedAt", "generated_at", "configVersion", "config_version"}
            }
        if isinstance(obj, list):
            return [_strip(v) for v in obj]
        return obj

    safe_payload = _strip(payload)
    serialized = json.dumps(safe_payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

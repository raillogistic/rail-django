"""
Cache utilities for metadata schema operations.

Provides caching mechanisms for Django model metadata extraction including
in-process caches, cache key generation, version tracking, and invalidation.
Caching is disabled in DEBUG mode for development convenience.
"""

import hashlib
import inspect
import logging
import threading
import time
import uuid
from functools import wraps
from typing import Any, Dict, List, Optional, Type, Union

from django.db import models
from graphql import GraphQLError

from ...config_proxy import get_core_schema_settings
from ...core.settings import SchemaSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process metadata caches (disabled when DEBUG=True)
# ---------------------------------------------------------------------------

_table_cache_lock = threading.RLock()
_table_cache: Dict[str, Dict[str, Any]] = {}
_table_cache_stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0, "invalidations": 0}
_table_cache_policy = {
    "enabled": True,
    "timeout_seconds": 600,
    "max_entries": 1000,
    "cache_authenticated": True,
    "timeout_configured": False,
}

_metadata_cache_lock = threading.RLock()
_metadata_cache: Dict[str, Dict[str, Any]] = {}
_metadata_cache_stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0, "invalidations": 0}
_metadata_cache_policy = {"timeout_seconds": 600, "max_entries": 1000}

_filter_cache_lock = threading.RLock()
_filter_class_cache: Dict[str, Any] = {}

_metadata_version_lock = threading.RLock()
_metadata_versions: Dict[str, str] = {}
_global_metadata_seed = str(int(time.time() * 1000))
_migration_context_cache: Optional[bool] = None


def _generate_metadata_version() -> str:
    """Generate a monotonic-ish metadata version token."""
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _metadata_version_scope(app_name: Optional[str], model_name: Optional[str]) -> str:
    """Compute the scope key for metadata versioning."""
    if not app_name or not model_name:
        return "__global__"
    return f"{app_name.lower()}:{model_name.lower()}"


def _get_metadata_version_value(app_name: str, model_name: str) -> str:
    """Return the current metadata version for the given model."""
    scope = _metadata_version_scope(app_name, model_name)
    with _metadata_version_lock:
        version = _metadata_versions.get(scope)
        if version:
            return version
        _metadata_versions[scope] = _global_metadata_seed
        return _global_metadata_seed


def _bump_metadata_version(
    app_name: Optional[str] = None, model_name: Optional[str] = None
) -> None:
    """Advance the metadata version for a specific model or globally."""
    global _global_metadata_seed
    token = _generate_metadata_version()
    with _metadata_version_lock:
        if app_name and model_name:
            scope = _metadata_version_scope(app_name, model_name)
            _metadata_versions[scope] = token
        else:
            _global_metadata_seed = token
            _metadata_versions.clear()


def _is_fsm_field_instance(field: Any) -> bool:
    """Detect whether a field is a django_fsm.FSMField without forcing the dependency."""
    try:
        from django_fsm import FSMField
        return isinstance(field, FSMField)
    except Exception:
        return False


def _is_debug_mode() -> bool:
    """Check if Django is running in DEBUG mode."""
    try:
        from django.conf import settings as django_settings
        return bool(getattr(django_settings, "DEBUG", False))
    except Exception:
        return False


def _load_table_cache_policy() -> None:
    """Load cache policy for metadata from Django settings (RAIL_DJANGO_GRAPHQL.METADATA)."""
    try:
        from django.conf import settings as django_settings
        config = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {}) or {}
        metadata_cfg = config.get("METADATA", {}) or {}
        _table_cache_policy["enabled"] = bool(metadata_cfg.get("table_cache_enabled", True))
        timeout_configured = "table_cache_timeout_seconds" in metadata_cfg
        try:
            timeout_val = int(metadata_cfg.get("table_cache_timeout_seconds", 600))
        except (TypeError, ValueError):
            timeout_val = 0
        _table_cache_policy["timeout_seconds"] = timeout_val
        _table_cache_policy["timeout_configured"] = timeout_configured
        max_entries_val = int(metadata_cfg.get("table_cache_max_entries", 1000))
        _table_cache_policy["max_entries"] = max_entries_val if max_entries_val > 0 else 1000
        _table_cache_policy["cache_authenticated"] = bool(
            metadata_cfg.get("table_cache_authenticated", True)
        )
    except Exception:
        _table_cache_policy.update({
            "enabled": True, "timeout_seconds": 600, "max_entries": 1000,
            "cache_authenticated": True, "timeout_configured": False,
        })


def _get_table_cache_timeout() -> Optional[int]:
    """Return cache timeout for table metadata (None means no expiry)."""
    timeout_configured = bool(_table_cache_policy.get("timeout_configured"))
    if not _is_debug_mode() and not timeout_configured:
        return None
    try:
        timeout_val = int(_table_cache_policy.get("timeout_seconds", 600))
    except (TypeError, ValueError):
        timeout_val = 0
    return timeout_val if timeout_val > 0 else None


def _get_metadata_cache_timeout(timeout: Optional[int]) -> Optional[int]:
    """Compute effective metadata cache timeout."""
    if not _is_debug_mode():
        return None
    default_timeout = int(_metadata_cache_policy.get("timeout_seconds", 600))
    if timeout is None:
        return default_timeout
    try:
        timeout_val = int(timeout)
    except (TypeError, ValueError):
        return default_timeout
    return timeout_val if timeout_val > 0 else default_timeout


def _make_table_cache_key(
    schema_name: str,
    app_name: str,
    model_name: str,
    counts: bool,
    exclude: Optional[List[str]] = None,
    only: Optional[List[str]] = None,
    include_nested: bool = True,
    only_lookup: Optional[List[str]] = None,
    exclude_lookup: Optional[List[str]] = None,
    include_filters: bool = True,
    include_mutations: bool = True,
    include_templates: bool = True,
    user_cache_key: Optional[str] = None,
) -> str:
    """Build a stable cache key for model_table metadata."""
    try:
        parts = {
            "exclude": ",".join(sorted(exclude or [])),
            "only": ",".join(sorted(only or [])),
            "include_nested": "1" if include_nested else "0",
            "only_lookup": ",".join(sorted(only_lookup or [])),
            "exclude_lookup": ",".join(sorted(exclude_lookup or [])),
            "filters": "1" if include_filters else "0",
            "mutations": "1" if include_mutations else "0",
            "templates": "1" if include_templates else "0",
            "user": user_cache_key or "",
        }
        signature = "|".join(f"{k}={v}" for k, v in parts.items())
        digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:8]
        user_part = f":user={user_cache_key}" if user_cache_key else ""
        return (
            f"model-table:{schema_name}:{app_name}:{model_name}:counts={1 if counts else 0}"
            f":filters={1 if include_filters else 0}:mutations={1 if include_mutations else 0}"
            f":templates={1 if include_templates else 0}:cf={digest}{user_part}"
        )
    except Exception:
        fallback = (
            f"model-table:{schema_name}:{app_name}:{model_name}:counts={1 if counts else 0}"
            f":filters={1 if include_filters else 0}:mutations={1 if include_mutations else 0}"
            f":templates={1 if include_templates else 0}"
        )
        if user_cache_key:
            fallback = f"{fallback}:user={user_cache_key}"
        return fallback


def _make_filter_cache_key(schema_name: str, model: Type[models.Model]) -> str:
    """Build a cache key for filter class caching."""
    try:
        model_label = getattr(model._meta, "label_lower", None) or model.__name__
    except Exception:
        model_label = model.__name__
    return f"filter-class:{schema_name}:{model_label}"


def _get_user_cache_key(user: Any) -> Optional[str]:
    """Build a stable, hashed cache key for an authenticated user."""
    if not user:
        return None
    try:
        identifier = (
            getattr(user, "cache_key", None)
            or getattr(user, "sub", None)
            or getattr(user, "pk", None)
            or getattr(user, "id", None)
        )
        if identifier is None:
            return None
        return hashlib.sha1(str(identifier).encode("utf-8")).hexdigest()[:12]
    except Exception:
        return None


def _self_cache_token(instance: Any) -> str:
    """Generate a cache token for a class instance."""
    class_name = instance.__class__.__name__
    schema_name = getattr(instance, "schema_name", None)
    max_depth = getattr(instance, "max_depth", None)
    parts = [class_name]
    if schema_name is not None:
        parts.append(f"schema={schema_name}")
    if max_depth is not None:
        parts.append(f"depth={max_depth}")
    return ":".join(parts)


def _normalize_cache_value(value: Any) -> str:
    """Normalize a value for inclusion in a cache key."""
    if value is None:
        return "none"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_normalize_cache_value(item) for item in value) + "]"
    if isinstance(value, set):
        return "{" + ",".join(sorted(_normalize_cache_value(item) for item in value)) + "}"
    if isinstance(value, dict):
        items = sorted(
            (_normalize_cache_value(key), _normalize_cache_value(val))
            for key, val in value.items()
        )
        return "{" + ",".join(f"{key}:{val}" for key, val in items) + "}"
    if hasattr(value, "_meta") and getattr(value._meta, "label_lower", None):
        return f"model:{value._meta.label_lower}"
    if hasattr(value, "model") and hasattr(value, "name"):
        model = getattr(value, "model", None)
        if model and getattr(model, "_meta", None) and getattr(model._meta, "label_lower", None):
            return f"field:{model._meta.label_lower}.{value.name}"
    return repr(value)


def _make_metadata_cache_key(
    func, bound_args: inspect.BoundArguments, user_specific: bool, user_cache_key: Optional[str]
) -> str:
    """Build a cache key for general metadata caching."""
    parts: List[str] = [f"{func.__module__}.{func.__qualname__}"]
    for name, value in bound_args.arguments.items():
        if name == "self":
            parts.append(f"self={_self_cache_token(value)}")
        elif name == "user":
            if user_specific:
                parts.append(f"user={user_cache_key or 'anon'}")
        else:
            parts.append(f"{name}={_normalize_cache_value(value)}")
    raw_key = "|".join(parts)
    return f"metadata:{hashlib.sha1(raw_key.encode('utf-8')).hexdigest()}"


def cache_metadata(
    timeout: int = None,
    user_specific: bool = True,
    invalidate_on_model_change: bool = True,
):
    """
    Cache metadata extraction results when DEBUG is False with no expiry.

    Args:
        timeout: Cache TTL in seconds (ignored when DEBUG is False).
        user_specific: Whether to include the user in the cache key.
        invalidate_on_model_change: Reserved for future invalidation controls.
    """
    def decorator(func):
        signature = None
        try:
            signature = inspect.signature(func)
        except Exception:
            signature = None

        @wraps(func)
        def wrapper(*args, **kwargs):
            if func.__name__ == "extract_model_table_metadata":
                return func(*args, **kwargs)
            if _is_debug_mode():
                return func(*args, **kwargs)
            if signature is None:
                return func(*args, **kwargs)
            try:
                bound_args = signature.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()
            except Exception:
                return func(*args, **kwargs)

            user = bound_args.arguments.get("user")
            user_authenticated = bool(user and getattr(user, "is_authenticated", False))
            user_cache_key = _get_user_cache_key(user) if user_specific else None
            if user_specific and user_authenticated and not user_cache_key:
                return func(*args, **kwargs)

            cache_key = _make_metadata_cache_key(
                func, bound_args, user_specific=user_specific, user_cache_key=user_cache_key
            )
            now = time.time()
            with _metadata_cache_lock:
                entry = _metadata_cache.get(cache_key)
                expires_at = entry.get("expires_at") if entry else None
                if entry and (expires_at is None or expires_at > now):
                    _metadata_cache_stats["hits"] += 1
                    return entry.get("value")
                _metadata_cache_stats["misses"] += 1

            result = func(*args, **kwargs)

            timeout_seconds = _get_metadata_cache_timeout(timeout)
            expires_at = None if timeout_seconds is None else now + timeout_seconds
            with _metadata_cache_lock:
                _metadata_cache[cache_key] = {
                    "value": result, "expires_at": expires_at, "created_at": now
                }
                _metadata_cache_stats["sets"] += 1
                max_entries = _metadata_cache_policy.get("max_entries", 1000) or 0
                if max_entries > 0 and len(_metadata_cache) > max_entries:
                    excess = len(_metadata_cache) - max_entries
                    oldest = sorted(
                        _metadata_cache.items(), key=lambda kv: kv[1].get("created_at", 0)
                    )[:excess]
                    for key, _ in oldest:
                        _metadata_cache.pop(key, None)
                        _metadata_cache_stats["deletes"] += 1
            return result
        return wrapper
    return decorator


def invalidate_metadata_cache(model_name: str = None, app_name: str = None) -> None:
    """Invalidate cached metadata, optionally scoped to a specific model/app."""
    global _table_cache, _metadata_cache
    with _table_cache_lock:
        if _table_cache:
            keys_to_delete = []
            for k in list(_table_cache.keys()):
                parts = k.split(":")
                cache_app = parts[2] if len(parts) > 2 else None
                cache_model = parts[3] if len(parts) > 3 else None
                if model_name or app_name:
                    if (not app_name or app_name == cache_app) and (
                        not model_name or model_name == cache_model
                    ):
                        keys_to_delete.append(k)
                else:
                    keys_to_delete.append(k)
            for k in keys_to_delete:
                _table_cache.pop(k, None)
                _table_cache_stats["deletes"] += 1
        _table_cache_stats["invalidations"] += 1

    with _metadata_cache_lock:
        if _metadata_cache:
            _metadata_cache_stats["deletes"] += len(_metadata_cache)
            _metadata_cache.clear()
        _metadata_cache_stats["invalidations"] += 1

    with _filter_cache_lock:
        if _filter_class_cache:
            if model_name or app_name:
                filter_keys = []
                for key in list(_filter_class_cache.keys()):
                    parts = key.split(":")
                    cache_label = parts[2] if len(parts) > 2 else ""
                    label_parts = cache_label.split(".")
                    cache_app = label_parts[0] if len(label_parts) > 0 else ""
                    cache_model = label_parts[1] if len(label_parts) > 1 else ""
                    if (not app_name or str(app_name).lower() == str(cache_app).lower()) and (
                        not model_name or str(model_name).lower() == str(cache_model).lower()
                    ):
                        filter_keys.append(key)
                for key in filter_keys:
                    _filter_class_cache.pop(key, None)
            else:
                _filter_class_cache.clear()

    if app_name and model_name:
        _bump_metadata_version(app_name=app_name, model_name=model_name)
    else:
        _bump_metadata_version()


def invalidate_cache_on_startup() -> None:
    """Invalidate metadata cache on Django startup (controlled by settings)."""
    try:
        from django.conf import settings as django_settings
        config = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {}) or {}
        metadata_config = config.get("METADATA", {}) or {}
        clear_on_start = bool(metadata_config.get("clear_cache_on_start", False))
        debug_only = bool(metadata_config.get("clear_cache_on_start_debug_only", False))
        debug_mode = bool(getattr(django_settings, "DEBUG", False))
        if clear_on_start and (not debug_only or debug_mode):
            invalidate_metadata_cache()
            logger.info("Metadata cache invalidated on application startup")
    except Exception as e:
        logger.debug(f"Skipping startup cache invalidation: {e}")
    _load_table_cache_policy()


def _get_requested_field_names(info) -> set:
    """Extract top-level selection field names from a GraphQL resolve info object."""
    names = set()
    try:
        field_nodes = getattr(info, "field_nodes", None) or getattr(info, "field_asts", None)
        for node in field_nodes or []:
            selection_set = getattr(node, "selection_set", None)
            if not selection_set:
                continue
            for selection in selection_set.selections:
                sel_name = getattr(getattr(selection, "name", None), "value", None)
                if sel_name:
                    names.add(sel_name)
    except Exception:
        return set()
    return names


def get_user_model_lazy():
    """Lazily import and return the Django user model to avoid AppRegistryNotReady."""
    from django.contrib.auth import get_user_model
    return get_user_model()


def _is_metadata_enabled(
    schema_settings: Optional[Union[SchemaSettings, Dict[str, Any]]]
) -> bool:
    """Check if metadata is enabled for the given schema settings."""
    if not schema_settings:
        return False
    if isinstance(schema_settings, dict):
        return bool(schema_settings.get("show_metadata"))
    return bool(getattr(schema_settings, "show_metadata", False))


def _require_metadata_access(info) -> Any:
    """Validate metadata access is allowed (enabled + authenticated)."""
    schema_settings = get_core_schema_settings(getattr(info.context, "schema_name", None))
    if not _is_metadata_enabled(schema_settings):
        raise GraphQLError("Metadata is disabled for this schema.")
    user = getattr(info.context, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise GraphQLError("Authentication required to access metadata.")
    return user

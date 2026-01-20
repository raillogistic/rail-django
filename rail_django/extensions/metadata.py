"""SModel metadata schema for Django GraphQL Auto-Generation.

This module provides comprehensive metadata exposure for Django models to support
rich frontend interfaces including advanced filtering, CRUD operations, and
complex forms with nested fields.
"""

import hashlib
import inspect
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Dict, List, Optional, Type, Union, get_args, get_origin

import graphene
from graphene.types.generic import GenericScalar
from django.apps import apps
from django.db import models
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.utils.encoding import force_str
from graphql import GraphQLError
from rail_django.plugins import base

from ..config_proxy import get_core_schema_settings
from ..core.settings import SchemaSettings
from ..generators.introspector import ModelIntrospector
from ..utils.graphql_meta import get_model_graphql_meta

# Remove imports that cause AppRegistryNotReady error
# from ..core.security import AuthorizationManager
from ..extensions.permissions import PermissionLevel, OperationType
from ..security.field_permissions import (
    FieldAccessLevel,
    FieldContext,
    FieldVisibility,
    field_permission_manager,
)

try:
    from .templating import (
        template_registry,
        _url_prefix as _templating_url_prefix,
        evaluate_template_access,
    )
except Exception:  # pragma: no cover - optional dependency during early startup
    template_registry = None
    evaluate_template_access = None

    def _templating_url_prefix() -> str:
        return "templates"


logger = logging.getLogger(__name__)

# In-process metadata caches (disabled when DEBUG=True).

# Lightweight, targeted cache for model_table metadata only
_table_cache_lock = threading.RLock()
_table_cache: dict[str, dict[str, Any]] = {}
_table_cache_stats = {
    "hits": 0,
    "misses": 0,
    "sets": 0,
    "deletes": 0,
    "invalidations": 0,
}
_table_cache_policy = {
    "enabled": True,
    "timeout_seconds": 600,
    "max_entries": 1000,
    "cache_authenticated": True,
    "timeout_configured": False,
}
_metadata_cache_lock = threading.RLock()
_metadata_cache: dict[str, dict[str, Any]] = {}
_metadata_cache_stats = {
    "hits": 0,
    "misses": 0,
    "sets": 0,
    "deletes": 0,
    "invalidations": 0,
}
_metadata_cache_policy = {
    "timeout_seconds": 600,
    "max_entries": 1000,
}

_filter_cache_lock = threading.RLock()
_filter_class_cache: dict[str, Any] = {}

_metadata_version_lock = threading.RLock()
_metadata_versions: dict[str, str] = {}
_global_metadata_seed = str(int(time.time() * 1000))
_migration_context_cache: Optional[bool] = None


def _generate_metadata_version() -> str:
    """Generate a monotonic-ish metadata version token."""
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _metadata_version_scope(app_name: Optional[str], model_name: Optional[str]) -> str:
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
    """
    Detect whether a field is provided by django_fsm.FSMField without forcing the dependency at import time.
    """
    try:
        from django_fsm import FSMField

        return isinstance(field, FSMField)
    except Exception:
        return False


def _load_table_cache_policy() -> None:
    """
    Load cache policy for metadata from Django settings.
    Supported keys under RAIL_DJANGO_GRAPHQL.METADATA:
      - table_cache_enabled (bool)
      - table_cache_timeout_seconds (int)
      - table_cache_max_entries (int)
      - table_cache_authenticated (bool)  # allow caching per-user
    """
    try:
        from django.conf import settings as django_settings

        config = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {}) or {}
        metadata_cfg = config.get("METADATA", {}) or {}
        _table_cache_policy["enabled"] = bool(
            metadata_cfg.get("table_cache_enabled", True)
        )
        timeout_configured = "table_cache_timeout_seconds" in metadata_cfg
        try:
            timeout_val = int(
                metadata_cfg.get("table_cache_timeout_seconds", 600)
            )
        except (TypeError, ValueError):
            timeout_val = 0
        _table_cache_policy["timeout_seconds"] = timeout_val
        _table_cache_policy["timeout_configured"] = timeout_configured
        max_entries_val = int(metadata_cfg.get("table_cache_max_entries", 1000))
        _table_cache_policy["max_entries"] = (
            max_entries_val if max_entries_val > 0 else 1000
        )
        _table_cache_policy["cache_authenticated"] = bool(
            metadata_cfg.get("table_cache_authenticated", True)
        )
    except Exception:
        # Keep defaults on failure
        _table_cache_policy.update(
            {
                "enabled": True,
                "timeout_seconds": 600,
                "max_entries": 1000,
                "cache_authenticated": True,
                "timeout_configured": False,
            }
        )


def _get_table_cache_timeout() -> Optional[int]:
    """Return cache timeout for table metadata (None means no expiry)."""
    timeout_configured = bool(_table_cache_policy.get("timeout_configured"))
    if not _is_debug_mode() and not timeout_configured:
        return None
    try:
        timeout_val = int(_table_cache_policy.get("timeout_seconds", 600))
    except (TypeError, ValueError):
        timeout_val = 0
    if timeout_val <= 0:
        return None
    return timeout_val


def _make_table_cache_key(
    schema_name: str,
    app_name: str,
    model_name: str,
    counts: bool,
    exclude: Optional[list[str]] = None,
    only: Optional[list[str]] = None,
    include_nested: bool = True,
    only_lookup: Optional[list[str]] = None,
    exclude_lookup: Optional[list[str]] = None,
    include_filters: bool = True,
    include_mutations: bool = True,
    include_templates: bool = True,
    user_cache_key: Optional[str] = None,
) -> str:
    """
    Purpose: Build a stable cache key for model_table metadata.
    Args:
        schema_name: str schema identifier
        app_name: str Django app label
        model_name: str Django model name
        counts: bool include reverse relationship counts
        exclude: Optional[List[str]] field names to exclude from filters
        only: Optional[List[str]] field names to include in filters
        include_nested: bool whether nested filters are included
        only_lookup: Optional[List[str]] lookups to include (e.g., ["exact","in"])
        exclude_lookup: Optional[List[str]] lookups to exclude
    Returns: str: cache key
    Raises: None
    Example:
        >>> _make_table_cache_key('default','app','Model',False, only=["name"], include_nested=False)
        'model-table:default:app:Model:counts=0:filters=1:mutations=1:templates=1:cf=f9b1f2b3'
    """
    try:
        # Build a compact signature hash for filter controls to avoid overly long keys
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
        # Fallback to legacy key format if hashing fails
        fallback = (
            f"model-table:{schema_name}:{app_name}:{model_name}:counts={1 if counts else 0}"
            f":filters={1 if include_filters else 0}:mutations={1 if include_mutations else 0}"
            f":templates={1 if include_templates else 0}"
        )
        if user_cache_key:
            fallback = f"{fallback}:user={user_cache_key}"
        return fallback


def _make_filter_cache_key(schema_name: str, model: type[models.Model]) -> str:
    try:
        model_label = getattr(model._meta, "label_lower", None) or model.__name__
    except Exception:
        model_label = model.__name__
    return f"filter-class:{schema_name}:{model_label}"


def _get_user_cache_key(user: Any) -> Optional[str]:
    """
    Build a stable cache key for an authenticated user without leaking raw identifiers.
    """
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
        digest = hashlib.sha1(str(identifier).encode("utf-8")).hexdigest()[:12]
        return digest
    except Exception:
        return None


def _is_debug_mode() -> bool:
    try:
        from django.conf import settings as django_settings

        return bool(getattr(django_settings, "DEBUG", False))
    except Exception:
        return False


def _self_cache_token(instance: Any) -> str:
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
            (
                _normalize_cache_value(key),
                _normalize_cache_value(val),
            )
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


def _get_metadata_cache_timeout(timeout: Optional[int]) -> Optional[int]:
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


def _make_metadata_cache_key(
    func, bound_args: inspect.BoundArguments, user_specific: bool, user_cache_key: Optional[str]
) -> str:
    parts: list[str] = [f"{func.__module__}.{func.__qualname__}"]
    for name, value in bound_args.arguments.items():
        if name == "self":
            parts.append(f"self={_self_cache_token(value)}")
        elif name == "user":
            if user_specific:
                parts.append(f"user={user_cache_key or 'anon'}")
        else:
            parts.append(f"{name}={_normalize_cache_value(value)}")
    raw_key = "|".join(parts)
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
    return f"metadata:{digest}"


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
                    cached = entry.get("value")
                    return cached
                _metadata_cache_stats["misses"] += 1

            result = func(*args, **kwargs)

            timeout_seconds = _get_metadata_cache_timeout(timeout)
            expires_at = None if timeout_seconds is None else now + timeout_seconds
            with _metadata_cache_lock:
                _metadata_cache[cache_key] = {
                    "value": result,
                    "expires_at": expires_at,
                    "created_at": now,
                }
                _metadata_cache_stats["sets"] += 1
                max_entries = _metadata_cache_policy.get("max_entries", 1000) or 0
                if max_entries > 0 and len(_metadata_cache) > max_entries:
                    excess = len(_metadata_cache) - max_entries
                    oldest = sorted(
                        _metadata_cache.items(),
                        key=lambda kv: kv[1].get("created_at", 0),
                    )[:excess]
                    for key, _ in oldest:
                        _metadata_cache.pop(key, None)
                        _metadata_cache_stats["deletes"] += 1

            return result

        return wrapper

    return decorator


def invalidate_metadata_cache(model_name: str = None, app_name: str = None):
    """
    Purpose: Invalidate cached metadata. Currently focuses on model_table cache.
    Args:
        model_name: Optional[str] model name to invalidate
        app_name: Optional[str] app label to scope invalidation
    Returns: None
    Raises: None
    Example:
        >>> invalidate_metadata_cache(model_name="Product", app_name="inventory")
    """
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
                    if model_name or app_name:
                        label_parts = cache_label.split(".")
                        cache_app = label_parts[0] if len(label_parts) > 0 else ""
                        cache_model = label_parts[1] if len(label_parts) > 1 else ""
                        if (
                            not app_name
                            or str(app_name).lower() == str(cache_app).lower()
                        ) and (
                            not model_name
                            or str(model_name).lower() == str(cache_model).lower()
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
    """

    Purpose: Invalidate metadata cache when the Django application starts, controlled by settings.
    Args: None
    Returns: None
    Raises: None
    Example:
        >>> invalidate_cache_on_startup()
    """
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
    """
    Extract top-level selection field names from a GraphQL resolve info object.
    """
    names = set()
    try:
        field_nodes = getattr(info, "field_nodes", None) or getattr(
            info, "field_asts", None
        )
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


# Use lazy import to avoid AppRegistryNotReady error
def get_user_model_lazy():
    from django.contrib.auth import get_user_model

    return get_user_model()


def _is_metadata_enabled(
    schema_settings: Optional[Union[SchemaSettings, dict[str, Any]]]
) -> bool:
    if not schema_settings:
        return False
    if isinstance(schema_settings, dict):
        return bool(schema_settings.get("show_metadata"))
    return bool(getattr(schema_settings, "show_metadata", False))


def _require_metadata_access(info) -> Any:
    schema_settings = get_core_schema_settings(
        getattr(info.context, "schema_name", None)
    )
    if not _is_metadata_enabled(schema_settings):
        raise GraphQLError("Metadata is disabled for this schema.")
    user = getattr(info.context, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise GraphQLError("Authentication required to access metadata.")
    return user


@dataclass
class InputFieldMetadata:
    """Metadata for mutation input fields."""

    name: str
    field_type: str
    required: bool
    default_value: Optional[Any] = None
    description: Optional[str] = None
    choices: Optional[list[dict[str, Any]]] = None
    validation_rules: Optional[dict[str, Any]] = None
    widget_type: Optional[str] = None
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None
    related_model: Optional[str] = None
    multiple: bool = False


@dataclass
class MutationMetadata:
    """Metadata for GraphQL mutations."""

    name: str
    method_name: Optional[str] = None
    description: Optional[str] = None
    input_fields: list[InputFieldMetadata] = field(default_factory=list)
    return_type: Optional[str] = None
    input_type: Optional[str] = None
    requires_authentication: bool = True
    required_permissions: list[str] = field(default_factory=list)
    mutation_type: str = "custom"  # create, update, delete, custom
    model_name: Optional[str] = None
    form_config: Optional[dict[str, Any]] = None
    validation_schema: Optional[dict[str, Any]] = None
    success_message: Optional[str] = None
    error_messages: Optional[dict[str, str]] = None
    action: Optional[dict[str, Any]] = None


# ChoiceType : {"value":str,"label":str}    graphene class
class ChoiceType(graphene.ObjectType):
    value = graphene.String(required=True, description="Choice value")
    label = graphene.String(required=True, description="Choice label")


class FilterOptionType(graphene.ObjectType):
    """GraphQL type for individual filter options within a grouped filter."""

    name = graphene.String(
        required=True, description="Filter option name (e.g., 'slug__iexact')"
    )
    lookup_expr = graphene.String(
        required=True, description="Django lookup expression (e.g., 'iexact')"
    )
    help_text = graphene.String(
        required=True, description="Filter help text in French using field verbose_name"
    )
    filter_type = graphene.String(
        required=True, description="Filter class type (e.g., 'CharFilter')"
    )
    choices = graphene.List(
        ChoiceType,
        description="Available choices for the field (if any, typically for CharField)",
    )


class FilterFieldType(graphene.ObjectType):
    """GraphQL type for grouped filter field metadata."""

    field_name = graphene.String(required=True, description="Target model field name")
    is_nested = graphene.Boolean(
        required=True, description="Whether this is a nested filter"
    )
    related_model = graphene.String(description="Related model name for nested filters")
    is_custom = graphene.Boolean(
        required=True, description="Whether this includes custom filters"
    )
    field_label = graphene.String(
        required=True, description="Human-readable label for the field"
    )

    options = graphene.List(
        FilterOptionType,
        required=True,
        description="List of filter options for this field",
    )

    # Nested filter fields for related lookups (e.g., famille__code)
    nested = graphene.List(
        lambda: FilterFieldType,
        description="Nested filter fields for related model attributes",
    )

    # New fields for nested filter style support
    filter_input_type = graphene.String(
        description="Nested filter input type (e.g., StringFilterInput)"
    )
    available_operators = graphene.List(
        graphene.String,
        description="Available operators for nested filter style",
    )


class FilterPresetType(graphene.ObjectType):
    """Filter preset metadata for introspection."""
    name = graphene.String(required=True, description="Preset name")
    description = graphene.String(description="Preset description")
    filter_json = graphene.JSONString(required=True, description="Filter configuration")


class FilterSchemaType(graphene.ObjectType):
    """Schema for model filter introspection."""
    model = graphene.String(required=True, description="Model name")
    fields = graphene.List(
        lambda: FilterFieldType, required=True, description="Available filter fields"
    )
    presets = graphene.List(
        FilterPresetType, required=True, description="Available filter presets"
    )
    supports_fts = graphene.Boolean(
        required=True, description="Whether full-text search is supported"
    )
    supports_aggregation = graphene.Boolean(
        required=True, description="Whether aggregation filtering is supported"
    )


class FilterStyleEnum(graphene.Enum):
    """Filter input style enumeration."""

    FLAT = "flat"
    NESTED = "nested"


class FilterConfigType(graphene.ObjectType):
    """Filter configuration for a model."""

    style = graphene.Field(
        FilterStyleEnum, required=True, description="Filter input style"
    )
    argument_name = graphene.String(
        required=True, description="GraphQL argument name ('filters' or 'where')"
    )
    input_type_name = graphene.String(
        required=True, description="Filter input type name"
    )
    supports_and = graphene.Boolean(required=True, description="Supports AND operator")
    supports_or = graphene.Boolean(required=True, description="Supports OR operator")
    supports_not = graphene.Boolean(required=True, description="Supports NOT operator")
    dual_mode_enabled = graphene.Boolean(
        required=True, description="Both filter styles available"
    )


class RelationFilterType(graphene.ObjectType):
    """Relation filter metadata for M2M and reverse relations."""

    relation_name = graphene.String(required=True, description="Relation field name")
    relation_type = graphene.String(
        required=True, description="Type (MANY_TO_MANY, REVERSE_FK)"
    )
    supports_some = graphene.Boolean(
        required=True, description="Supports _some quantifier"
    )
    supports_every = graphene.Boolean(
        required=True, description="Supports _every quantifier"
    )
    supports_none = graphene.Boolean(
        required=True, description="Supports _none quantifier"
    )
    supports_count = graphene.Boolean(
        required=True, description="Supports _count filter"
    )
    nested_filter_type = graphene.String(
        description="Nested filter input type for the related model"
    )


class InputFieldMetadataType(graphene.ObjectType):
    """GraphQL type for input field metadata."""

    name = graphene.String(required=True, description="Field name")
    field_type = graphene.String(required=True, description="Field data type")
    required = graphene.Boolean(required=True, description="Whether field is required")
    default_value = graphene.JSONString(description="Default value for the field")
    description = graphene.String(description="Field description")
    choices = graphene.List(
        graphene.JSONString, description="Available choices for the field"
    )
    validation_rules = graphene.JSONString(description="Validation rules as JSON")
    widget_type = graphene.String(description="Recommended UI widget type")
    placeholder = graphene.String(description="Placeholder text for input")
    graphene.String(description="Help text for the field")
    min_length = graphene.Int(description="Minimum length for string fields")
    max_length = graphene.Int(description="Maximum length for string fields")
    min_value = graphene.Float(description="Minimum value for numeric fields")
    max_value = graphene.Float(description="Maximum value for numeric fields")
    pattern = graphene.String(description="Regex pattern for validation")
    related_model = graphene.String(description="Related model name for foreign keys")
    multiple = graphene.Boolean(
        required=True, description="Whether field accepts multiple values"
    )


class MutationMetadataType(graphene.ObjectType):
    """GraphQL type for mutation metadata."""

    name = graphene.String(required=True, description="Mutation name")
    method_name = graphene.String(description="Underlying model method name")
    description = graphene.String(description="Mutation description")
    input_fields = graphene.List(
        InputFieldMetadataType,
        required=True,
        description="Input fields for the mutation",
    )
    return_type = graphene.String(description="Return type of the mutation")
    input_type = graphene.String(description="GraphQL input type for the mutation")
    requires_authentication = graphene.Boolean(
        required=True, description="Whether mutation requires authentication"
    )
    required_permissions = graphene.List(
        graphene.String,
        required=True,
        description="Required permissions to execute mutation",
    )
    mutation_type = graphene.String(
        required=True, description="Type of mutation (create, update, delete, custom)"
    )
    model_name = graphene.String(description="Associated model name")
    form_config = graphene.JSONString(description="Frontend form configuration")
    validation_schema = graphene.JSONString(
        description="Validation schema for the mutation"
    )
    success_message = graphene.String(description="Success message template")
    error_messages = graphene.JSONString(description="Error message templates")
    action = graphene.JSONString(description="UI action metadata for row actions")


class FieldPermissionMetadataType(graphene.ObjectType):
    """GraphQL type exposing field-level permission metadata."""

    can_read = graphene.Boolean(
        required=True, description="Whether the current user may read the field"
    )
    can_write = graphene.Boolean(
        required=True, description="Whether the current user may edit the field"
    )
    visibility = graphene.String(
        required=True,
        description="Resolved visibility (visible, hidden, masked, redacted)",
    )
    access_level = graphene.String(
        required=True, description="Access level value (none, read, write, admin)"
    )
    mask_value = graphene.String(
        description="Mask value used when the field is partially hidden"
    )
    reason = graphene.String(
        description="Optional explanation describing why the field is restricted"
    )


class ModelPermissionMatrixType(graphene.ObjectType):
    """GraphQL type describing model-level permissions for the current user."""

    can_create = graphene.Boolean(
        required=True, description="Whether create operations are permitted"
    )
    can_update = graphene.Boolean(
        required=True, description="Whether update operations are permitted"
    )
    can_delete = graphene.Boolean(
        required=True, description="Whether delete operations are permitted"
    )
    can_read = graphene.Boolean(
        required=True, description="Whether retrieve/detail operations are permitted"
    )
    can_list = graphene.Boolean(
        required=True, description="Whether listing operations are permitted"
    )
    can_history = graphene.Boolean(
        required=True,
        description="Whether history operations are permitted",
    )
    reasons = graphene.JSONString(
        description="Optional mapping of operation identifiers to denial reasons"
    )


@dataclass
class FieldMetadata:
    """Metadata for a single model field."""

    name: str
    field_type: str
    is_required: bool
    is_nullable: bool
    null: bool
    default_value: Any
    help_text: str
    db_column: Optional[str]
    db_type: Optional[str]
    internal_type: Optional[str]
    max_length: Optional[int]
    min_length: Optional[int]
    min_value: Optional[Union[int, float]]
    max_value: Optional[Union[int, float]]
    regex: Optional[str]
    choices: Optional[list[dict[str, str]]]
    is_primary_key: bool
    is_foreign_key: bool
    is_unique: bool
    is_indexed: bool
    has_auto_now: bool
    has_auto_now_add: bool
    blank: bool
    editable: bool
    verbose_name: str
    has_permission: bool


@dataclass
class RelationshipMetadata:
    """Metadata for model relationships."""

    name: str
    relationship_type: str
    cardinality: str
    related_model: str
    related_app: str
    to_field: Optional[str]
    from_field: str
    is_reverse: bool
    is_required: bool
    many_to_many: bool
    one_to_one: bool
    foreign_key: bool
    on_delete: Optional[str]
    related_name: Optional[str]
    has_permission: bool
    verbose_name: str


def _relationship_cardinality(
    is_reverse: bool, many_to_many: bool, one_to_one: bool, foreign_key: bool
) -> str:
    if many_to_many:
        return "many_to_many"
    if one_to_one:
        return "one_to_one"
    if foreign_key:
        return "one_to_many" if is_reverse else "many_to_one"
    return "unknown"


@dataclass
class FieldPermissionMetadata:
    """Permission snapshot for a field."""

    can_read: bool
    can_write: bool
    visibility: str
    access_level: str
    mask_value: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class ModelPermissionMatrix:
    """Model-level CRUD permissions for the current user."""

    can_create: bool = True
    can_update: bool = True
    can_delete: bool = True
    can_read: bool = True
    can_list: bool = True
    can_history: bool = True
    reasons: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class ModelMetadata:
    """Complete metadata for a Django model."""

    metadata_version: str
    app_name: str
    model_name: str
    verbose_name: str
    verbose_name_plural: str
    table_name: str
    primary_key_field: str
    fields: list[FieldMetadata]
    relationships: list[RelationshipMetadata]
    permissions: list[str]
    ordering: list[str]
    default_ordering: list[str]
    unique_together: list[list[str]]
    unique_constraints: list[dict[str, Any]]
    indexes: list[dict[str, Any]]
    abstract: bool
    proxy: bool
    managed: bool
    filters: list[dict[str, Any]]
    mutations: list["MutationMetadata"]


@dataclass
class FormFieldMetadata:
    """Metadata for form fields with Django-specific attributes."""

    name: str
    field_type: str
    is_required: bool
    verbose_name: str
    help_text: str
    widget_type: str
    placeholder: Optional[str] = None
    default_value: Any = None
    choices: Optional[list[dict[str, str]]] = None
    # Django CharField attributes
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    # Django DecimalField attributes
    decimal_places: Optional[int] = None
    max_digits: Optional[int] = None
    # Django IntegerField/FloatField attributes
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    # Django DateField/DateTimeField attributes
    auto_now: bool = False
    auto_now_add: bool = False
    # Common field attributes
    blank: bool = False
    null: bool = False
    unique: bool = False
    editable: bool = True
    # Validation attributes
    validators: Optional[list[str]] = None
    error_messages: Optional[dict[str, str]] = None
    # Form-specific attributes
    disabled: bool = False
    readonly: bool = False
    css_classes: Optional[str] = None
    data_attributes: Optional[dict[str, str]] = None
    has_permission: bool = True
    permissions: Optional[FieldPermissionMetadata] = None


@dataclass
class FormRelationshipMetadata:
    """Metadata for form relationship fields with nested model information."""

    name: str
    relationship_type: str
    cardinality: str
    verbose_name: str
    help_text: str
    widget_type: str
    is_required: bool
    # Related model information
    related_model: str
    related_app: str
    to_field: Optional[str] = None
    from_field: str = ""
    # Relationship characteristics
    many_to_many: bool = False
    one_to_one: bool = False
    foreign_key: bool = False
    is_reverse: bool = False
    # Form-specific attributes
    multiple: bool = False
    queryset_filters: Optional[dict[str, Any]] = None
    empty_label: Optional[str] = None
    limit_choices_to: Optional[dict[str, Any]] = None
    # UI attributes
    disabled: bool = False
    readonly: bool = False
    css_classes: Optional[str] = None
    data_attributes: Optional[dict[str, str]] = None
    has_permission: bool = True
    permissions: Optional[FieldPermissionMetadata] = None


@dataclass
class ModelFormMetadata:
    """Complete metadata for Django model forms."""

    metadata_version: str
    app_name: str
    model_name: str
    verbose_name: str
    verbose_name_plural: str
    form_title: str

    form_description: Optional[str]
    fields: list[FormFieldMetadata]
    relationships: list[FormRelationshipMetadata]
    nested: list["ModelFormMetadata"] = field(default_factory=list)
    # Form configuration
    field_order: Optional[list[str]] = None
    # When this instance is produced as a nested metadata entry for a relationship,
    # these attributes describe the parent relationship that led to this nesting.
    # They remain None for top-level metadata.
    name: Optional[str] = None
    field_name: Optional[str] = None
    relationship_type: Optional[str] = None
    to_field: Optional[str] = None
    from_field: Optional[str] = None
    is_required: Optional[bool] = None
    exclude_fields: list[str] = field(default_factory=list)
    readonly_fields: list[str] = field(default_factory=list)
    # Validation and permissions
    required_permissions: list[str] = field(default_factory=list)
    form_validation_rules: Optional[dict[str, Any]] = None
    # UI configuration
    form_layout: Optional[dict[str, Any]] = None
    css_classes: Optional[str] = None
    form_attributes: Optional[dict[str, str]] = None
    permissions: Optional[ModelPermissionMatrix] = None


@dataclass
class TableFieldMetadata:
    """Metadata for a table field used in data grid displays."""

    name: str
    accessor: str
    display: str
    editable: bool
    field_type: str
    filterable: bool
    sortable: bool
    title: str
    help_text: str
    is_property: bool
    is_related: bool
    permissions: Optional[FieldPermissionMetadata] = None


@dataclass
class TemplateActionMetadata:
    """Metadata describing a printable template action exposed to the frontend."""

    key: str
    method_name: str
    title: str
    endpoint: str
    url_path: str
    guard: Optional[str]
    require_authentication: bool
    roles: list[str]
    permissions: list[str]
    allowed: bool
    denial_reason: Optional[str] = None
    allow_client_data: bool = False
    client_data_fields: list[str] = field(default_factory=list)
    client_data_schema: list[dict[str, Any]] = field(default_factory=list)
    client_data_schema: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ModelTableMetadata:
    """Comprehensive table metadata for a Django model, including fields and filters."""

    metadata_version: str
    app: str
    model: str
    verbose_name: str
    verbose_name_plural: str
    table_name: str
    primary_key: str
    ordering: list[str]
    default_ordering: list[str]
    get_latest_by: Optional[str]
    managers: list[str]
    managed: bool
    fields: list[TableFieldMetadata]
    generics: list[TableFieldMetadata]
    filters: list[dict[str, Any]]
    permissions: Optional[ModelPermissionMatrix] = None
    mutations: list[MutationMetadata] = field(default_factory=list)
    pdf_templates: list[TemplateActionMetadata] = field(default_factory=list)


def _build_field_permission_snapshot(
    user,
    model_class: type[models.Model],
    field_name: str,
) -> Optional[FieldPermissionMetadata]:
    """Build a permission snapshot for a field."""

    if not user or not getattr(user, "is_authenticated", False):
        return FieldPermissionMetadata(
            can_read=False,
            can_write=False,
            visibility=FieldVisibility.HIDDEN.value,
            access_level=FieldAccessLevel.NONE.value,
            reason="Authentification requise.",
        )

    context = FieldContext(
        user=user,
        model_class=model_class,
        field_name=field_name,
        operation_type="read",
    )
    access_level = field_permission_manager.get_field_access_level(context)
    visibility, mask_value = field_permission_manager.get_field_visibility(context)
    can_read = access_level in (
        FieldAccessLevel.READ,
        FieldAccessLevel.WRITE,
        FieldAccessLevel.ADMIN,
    )
    can_write = access_level in (FieldAccessLevel.WRITE, FieldAccessLevel.ADMIN)
    reason = None if can_read else "Permission insuffisante pour consulter ce champ."
    return FieldPermissionMetadata(
        can_read=can_read,
        can_write=can_write,
        visibility=visibility.value,
        access_level=access_level.value,
        mask_value=mask_value,
        reason=reason,
    )


def _build_model_permission_matrix(
    model: type[models.Model], user
) -> ModelPermissionMatrix:
    """Compute CRUD permissions for a model and user."""

    app_label = model._meta.app_label
    model_lower = model._meta.model_name
    operations = {
        "create": f"{app_label}.add_{model_lower}",
        "update": f"{app_label}.change_{model_lower}",
        "delete": f"{app_label}.delete_{model_lower}",
        "read": f"{app_label}.view_{model_lower}",
        "list": f"{app_label}.view_{model_lower}",
        "history": f"{app_label}.view_{model_lower}",
    }
    guard_map = {
        "create": "create",
        "update": "update",
        "delete": "delete",
        "read": "retrieve",
        "list": "list",
        "history": "history",
    }
    reasons: dict[str, Optional[str]] = {}

    if not user or not getattr(user, "is_authenticated", False):
        for op in operations.keys():
            reasons[op] = "Authentification requise."
        return ModelPermissionMatrix(
            can_create=False,
            can_update=False,
            can_delete=False,
            can_read=False,
            can_list=False,
            reasons=reasons,
        )

    guard_results: dict[str, dict[str, Any]] = {}
    try:
        graphql_meta = get_model_graphql_meta(model)
    except Exception:
        graphql_meta = None

    if graphql_meta:
        for guard_name in set(guard_map.values()):
            guard_results[guard_name] = graphql_meta.describe_operation_guard(
                guard_name, user=user
            )

    def evaluate(op: str) -> bool:
        allowed = user.has_perm(operations[op])
        reason = None if allowed else f"Permission {operations[op]} requise."
        guard_name = guard_map.get(op)
        guard_info = guard_results.get(guard_name) if guard_name else None
        if guard_info:
            guard_allowed = guard_info.get("allowed", True)
            if guard_allowed:
                allowed = True
                reason = None
            else:
                allowed = False
                reason = guard_info.get("reason") or reason
        if not allowed and reason:
            reasons[op] = reason
        return allowed

    matrix = ModelPermissionMatrix(
        can_create=evaluate("create"),
        can_update=evaluate("update"),
        can_delete=evaluate("delete"),
        can_read=evaluate("read"),
        can_list=evaluate("list"),
        can_history=evaluate("history"),
        reasons=reasons,
    )
    return matrix


class FieldMetadataType(graphene.ObjectType):
    """GraphQL type for field metadata."""

    name = graphene.String(required=True, description="Field name")
    field_type = graphene.String(required=True, description="Django field type")
    is_required = graphene.Boolean(
        required=True, description="Whether field is required"
    )
    is_nullable = graphene.Boolean(
        required=True, description="Whether field can be null"
    )
    null = graphene.Boolean(required=True, description="Whether field can be null")
    default_value = graphene.String(description="Default value as string")
    graphene.String(description="Field help text")
    db_column = graphene.String(description="Database column name")
    db_type = graphene.String(description="Database column type")
    internal_type = graphene.String(description="Django internal field type")
    max_length = graphene.Int(description="Maximum length for string fields")
    min_length = graphene.Int(description="Minimum length for string fields")
    min_value = GenericScalar(description="Minimum allowed value")
    max_value = GenericScalar(description="Maximum allowed value")
    regex = graphene.String(description="Regex validation pattern")
    choices = graphene.List(ChoiceType, description="Field choices")
    is_primary_key = graphene.Boolean(
        required=True, description="Whether field is primary key"
    )
    is_foreign_key = graphene.Boolean(
        required=True, description="Whether field is foreign key"
    )
    is_unique = graphene.Boolean(
        required=True, description="Whether field has unique constraint"
    )
    is_indexed = graphene.Boolean(required=True, description="Whether field is indexed")
    has_auto_now = graphene.Boolean(
        required=True, description="Whether field has auto_now"
    )
    has_auto_now_add = graphene.Boolean(
        required=True, description="Whether field has auto_now_add"
    )
    blank = graphene.Boolean(required=True, description="Whether field can be blank")
    editable = graphene.Boolean(required=True, description="Whether field is editable")
    graphene.String(required=True, description="Field verbose name")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission for this field"
    )


class RelationshipMetadataType(graphene.ObjectType):
    """GraphQL type for relationship metadata."""

    name = graphene.String(required=True, description="Relationship field name")
    relationship_type = graphene.String(
        required=True, description="Type of relationship"
    )
    cardinality = graphene.String(
        required=True, description="Relationship cardinality"
    )
    related_model = graphene.String(
        required=True,
        description="Related model name",
    )
    related_app = graphene.String(required=True, description="Related model app")
    to_field = graphene.String(description="Target field name")
    from_field = graphene.String(required=True, description="Source field name")
    is_reverse = graphene.Boolean(
        required=True, description="Whether this is a reverse relationship"
    )
    is_required = graphene.Boolean(
        required=True, description="Whether this is a reverse relationship"
    )
    many_to_many = graphene.Boolean(
        required=True, description="Whether this is many-to-many"
    )
    one_to_one = graphene.Boolean(
        required=True, description="Whether this is one-to-one"
    )
    foreign_key = graphene.Boolean(
        required=True, description="Whether this is foreign key"
    )
    on_delete = graphene.String(description="On delete behavior")
    related_name = graphene.String(description="Related name for reverse lookups")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission for this relationship"
    )
    graphene.String(required=True, description="Model verbose name")


class ModelMetadataType(graphene.ObjectType):
    """GraphQL type for complete model metadata."""

    metadataVersion = graphene.String(
        required=True,
        description="Stable metadata version identifier for this model metadata",
        source="metadata_version",
    )
    app_name = graphene.String(required=True, description="Django app name")
    model_name = graphene.String(required=True, description="Model class name")
    graphene.String(required=True, description="Model verbose name")
    verbose_name_plural = graphene.String(
        required=True, description="Model verbose name plural"
    )
    graphene.String(required=True, description="Database table name")
    primary_key_field = graphene.String(
        required=True, description="Primary key field name"
    )
    fields = graphene.List(FieldMetadataType, required=True, description="Model fields")
    relationships = graphene.List(
        RelationshipMetadataType, required=True, description="Model relationships"
    )
    permissions = graphene.List(
        graphene.String, required=True, description="Available permissions"
    )
    ordering = graphene.List(
        graphene.String, required=True, description="Default ordering"
    )
    default_ordering = graphene.List(
        graphene.String,
        required=True,
        description="Fallback ordering applied when no explicit ordering is set",
    )
    unique_together = graphene.List(
        graphene.List(graphene.String),
        required=True,
        description="Unique together constraints",
    )
    unique_constraints = graphene.List(
        graphene.JSONString,
        required=True,
        description="Unique constraints defined on the model",
    )
    indexes = graphene.List(
        graphene.JSONString, required=True, description="Database indexes"
    )
    abstract = graphene.Boolean(required=True, description="Whether model is abstract")
    proxy = graphene.Boolean(required=True, description="Whether model is proxy")
    managed = graphene.Boolean(
        required=True, description="Whether model is managed by Django"
    )
    filters = graphene.List(
        FilterFieldType, required=True, description="Available filter fields"
    )
    mutations = graphene.List(
        MutationMetadataType,
        required=True,
        description="Available mutations for this model",
    )


class FormFieldMetadataType(graphene.ObjectType):
    """GraphQL type for form field metadata."""

    name = graphene.String(required=True, description="Field name")
    field_type = graphene.String(required=True, description="Django field type")
    is_required = graphene.Boolean(
        required=True, description="Whether field is required"
    )
    graphene.String(required=True, description="Field verbose name")
    graphene.String(description="Field help text")
    widget_type = graphene.String(
        required=True, description="Recommended UI widget type"
    )
    placeholder = graphene.String(description="Placeholder text for input")
    default_value = graphene.JSONString(description="Default value for the field")
    choices = graphene.List(ChoiceType, description="Field choices")
    max_length = graphene.Int(description="Maximum length for string fields")
    min_length = graphene.Int(description="Minimum length for string fields")
    decimal_places = graphene.Int(description="Number of decimal places")
    max_digits = graphene.Int(description="Maximum number of digits")
    min_value = graphene.Float(description="Minimum value for numeric fields")
    max_value = graphene.Float(description="Maximum value for numeric fields")
    auto_now = graphene.Boolean(required=True, description="Whether field has auto_now")
    auto_now_add = graphene.Boolean(
        required=True, description="Whether field has auto_now_add"
    )
    blank = graphene.Boolean(required=True, description="Whether field can be blank")
    null = graphene.Boolean(required=True, description="Whether field can be null")
    unique = graphene.Boolean(
        required=True, description="Whether field has unique constraint"
    )
    editable = graphene.Boolean(required=True, description="Whether field is editable")
    validators = graphene.List(graphene.String, description="Field validators")
    error_messages = graphene.JSONString(description="Custom error messages")
    disabled = graphene.Boolean(
        required=True, description="Whether field is disabled in form"
    )
    readonly = graphene.Boolean(
        required=True, description="Whether field is readonly in form"
    )
    css_classes = graphene.String(description="CSS classes for form field")
    data_attributes = graphene.JSONString(description="Data attributes for form field")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission to access this field"
    )
    permissions = graphene.Field(
        FieldPermissionMetadataType,
        description="Detailed permission metadata for the field",
    )


class FormRelationshipMetadataType(graphene.ObjectType):
    """GraphQL type for form relationship metadata."""

    name = graphene.String(required=True, description="Relationship field name")
    relationship_type = graphene.String(
        required=True, description="Type of relationship"
    )
    cardinality = graphene.String(
        required=True, description="Relationship cardinality"
    )
    graphene.String(required=True, description="Field verbose name")
    graphene.String(description="Field help text")
    widget_type = graphene.String(
        required=True, description="Recommended UI widget type"
    )
    is_required = graphene.Boolean(
        required=True, description="Whether field is required"
    )
    related_model = graphene.String(
        required=True,
        description="Related model name",
    )
    related_app = graphene.String(required=True, description="Related model app")
    to_field = graphene.String(description="Target field name")
    from_field = graphene.String(required=True, description="Source field name")
    many_to_many = graphene.Boolean(
        required=True, description="Whether this is many-to-many"
    )
    one_to_one = graphene.Boolean(
        required=True, description="Whether this is one-to-one"
    )
    foreign_key = graphene.Boolean(
        required=True, description="Whether this is foreign key"
    )
    is_reverse = graphene.Boolean(
        required=True, description="Whether this is a reverse relationship"
    )
    multiple = graphene.Boolean(
        required=True, description="Whether field accepts multiple values"
    )
    queryset_filters = graphene.JSONString(description="Queryset filters for choices")
    empty_label = graphene.String(description="Empty choice label")
    limit_choices_to = graphene.JSONString(
        description="Limit choices to specific criteria"
    )
    disabled = graphene.Boolean(
        required=True, description="Whether field is disabled in form"
    )
    readonly = graphene.Boolean(
        required=True, description="Whether field is readonly in form"
    )
    css_classes = graphene.String(description="CSS classes for form field")
    data_attributes = graphene.JSONString(description="Data attributes for form field")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission to access this field"
    )
    permissions = graphene.Field(
        FieldPermissionMetadataType,
        description="Detailed permission metadata for this relationship",
    )


class ModelFormMetadataType(graphene.ObjectType):
    """GraphQL type for complete model form metadata."""

    metadataVersion = graphene.String(
        required=True,
        description="Stable metadata version identifier for cache coordination",
        source="metadata_version",
    )
    app_name = graphene.String(required=True, description="Django app name")
    model_name = graphene.String(required=True, description="Model class name")
    graphene.String(required=True, description="Model verbose name")
    verbose_name_plural = graphene.String(
        required=True, description="Model verbose name plural"
    )
    # Relationship linkage information for nested metadata entries
    # These are typically only populated for nested entries
    name = graphene.String(
        description="Deprecated: use field_name; retained for compatibility"
    )
    field_name = graphene.String(
        description="Parent relationship field name that produced this nested metadata"
    )
    relationship_type = graphene.String(
        description="Relationship type for the parent field (ForeignKey, ManyToManyField, OneToOneField)"
    )
    to_field = graphene.String(
        description="Target field name on the related model (if specified)"
    )
    from_field = graphene.String(description="Source field name on the parent model")
    is_required = graphene.Boolean(
        description="Whether the parent relationship field is required"
    )
    form_title = graphene.String(required=True, description="Form title")
    form_description = graphene.String(description="Form description")
    fields = graphene.List(
        FormFieldMetadataType, required=True, description="Form fields"
    )
    relationships = graphene.List(
        FormRelationshipMetadataType, required=True, description="Form relationships"
    )
    nested = graphene.List(
        lambda: ModelFormMetadataType,
        required=True,
        description="Nested form metadata for specified fields",
    )
    # Form configuration
    field_order = graphene.List(graphene.String, description="Field display order")
    exclude_fields = graphene.List(
        graphene.String, required=True, description="Fields to exclude from form"
    )
    readonly_fields = graphene.List(
        graphene.String, required=True, description="Fields that are readonly"
    )
    # Validation and permissions
    required_permissions = graphene.List(
        graphene.String, required=True, description="Required permissions"
    )
    form_validation_rules = graphene.JSONString(description="Form validation rules")
    # UI configuration
    form_layout = graphene.JSONString(description="Form layout configuration")
    css_classes = graphene.String(description="CSS classes for form")
    form_attributes = graphene.JSONString(description="Form HTML attributes")
    permissions = graphene.Field(
        ModelPermissionMatrixType,
        description="Operation-level permissions for the current user",
    )


class TableFieldMetadataType(graphene.ObjectType):
    """GraphQL type for table field metadata used in data grid."""

    name = graphene.String(required=True, description="Field name")
    accessor = graphene.String(required=True, description="Field accessor")
    display = graphene.String(required=True, description="Field display accessor")
    editable = graphene.Boolean(required=True, description="Whether field is editable")
    field_type = graphene.String(required=True, description="Field data type")
    filterable = graphene.Boolean(
        required=True, description="Whether field is filterable"
    )
    sortable = graphene.Boolean(required=True, description="Whether field is sortable")
    title = graphene.String(required=True, description="Field title (verbose name)")
    graphene.String(required=True, description="Help text or description")
    is_property = graphene.Boolean(
        required=True, description="Whether field is a property"
    )
    is_related = graphene.Boolean(required=True, description="Whether field is related")
    permissions = graphene.Field(
        FieldPermissionMetadataType,
        description="Permission metadata for this table column",
    )


class TemplateActionMetadataType(graphene.ObjectType):
    """GraphQL type exposing printable template metadata for ModelTable consumers."""

    key = graphene.String(
        required=True, description="Stable identifier for the template"
    )
    methodName = graphene.String(
        required=True,
        description="Model method name declared with @model_pdf_template",
        source="method_name",
    )
    title = graphene.String(required=True, description="Human readable title")
    endpoint = graphene.String(
        required=True,
        description="Relative endpoint prefix under /api for this template",
    )
    urlPath = graphene.String(
        required=True,
        description="Template path appended to the templating URL prefix",
        source="url_path",
    )
    guard = graphene.String(
        description="GraphQL guard name enforced when rendering this template"
    )
    requireAuthentication = graphene.Boolean(
        required=True,
        description="Whether authentication is required to hit this endpoint",
        source="require_authentication",
    )
    roles = graphene.List(
        graphene.String,
        required=True,
        description="Roles required to access the template",
    )
    permissions = graphene.List(
        graphene.String,
        required=True,
        description="Permissions required to access the template",
    )
    allowed = graphene.Boolean(
        required=True, description="Whether the current user passes static checks"
    )
    denialReason = graphene.String(
        description="Reason describing why the template is unavailable",
        source="denial_reason",
    )
    allowClientData = graphene.Boolean(
        required=True,
        description="Permet à l'utilisateur de fournir des données personnalisées",
        source="allow_client_data",
    )
    clientDataFields = graphene.List(
        graphene.String,
        required=True,
        description="Clés autorisées pour les données client",
        source="client_data_fields",
    )
    clientDataSchema = graphene.List(
        GenericScalar,
        required=True,
        description="Schéma des champs client (name/type)",
        source="client_data_schema",
    )
    clientDataSchema = graphene.List(
        graphene.JSONString,
        required=True,
        description="Schéma des champs client (name/type)",
        source="client_data_schema",
    )


class ModelTableType(graphene.ObjectType):
    """GraphQL type for comprehensive table metadata for a Django model."""

    metadataVersion = graphene.String(
        required=True,
        description="Stable metadata version identifier for this table metadata",
        source="metadata_version",
    )
    app = graphene.String(required=True, description="Application name")
    model = graphene.String(required=True, description="Model name")
    graphene.String(required=True, description="Singular verbose name")
    verbose_name_plural = graphene.String(
        required=True, description="Plural verbose name"
    )
    graphene.String(required=True, description="Database table name")
    graphene.String(required=True, description="Primary key field name")
    ordering = graphene.List(
        graphene.String, required=True, description="Default ordering fields"
    )
    default_ordering = graphene.List(
        graphene.String, required=True, description="Fallback ordering fields"
    )
    get_latest_by = graphene.String(description="Field used by 'latest' manager")
    managers = graphene.List(
        graphene.String, required=True, description="Manager names"
    )
    managed = graphene.Boolean(
        required=True, description="Whether Django manages the table"
    )
    fields = graphene.List(
        TableFieldMetadataType, required=True, description="All field metadata"
    )
    generics = graphene.List(
        TableFieldMetadataType, required=True, description="GenericRelation fields"
    )
    filters = graphene.List(
        FilterFieldType,
        required=True,
        description="Available filters with field structure",
    )
    permissions = graphene.Field(
        ModelPermissionMatrixType,
        description="Operation-level permissions for listing and mutations",
    )
    mutations = graphene.List(
        MutationMetadataType,
        description="Available GraphQL mutations relevant to this model",
    )
    pdfTemplates = graphene.List(
        TemplateActionMetadataType,
        description="Printable templates derived from @model_pdf_template decorators",
        source="pdf_templates",
    )


def resolve_filter_schema(root, info, model: str, depth: int = 1):
    """
    Resolver for __filterSchema query.
    """
    try:
        # Find model class from name
        target_model = None
        for app_config in apps.get_app_configs():
            for m in app_config.get_models():
                if m.__name__ == model:
                    target_model = m
                    break
            if target_model:
                break
        
        if not target_model:
            return None

        # Get filter metadata using the generator
        from ..generators.filter_inputs import FilterMetadataGenerator
        
        # Determine schema name from context or default
        schema_name = getattr(info.context, "schema_name", "default")
        generator = FilterMetadataGenerator(schema_name=schema_name)
        
        grouped_filters = generator.get_grouped_filters(target_model)
        
        # Get presets
        presets = []
        try:
            graphql_meta = get_model_graphql_meta(target_model)
            if graphql_meta and graphql_meta.filter_presets:
                for name, definition in graphql_meta.filter_presets.items():
                    presets.append(
                        FilterPresetType(
                            name=name,
                            description=f"Preset: {name}",
                            filter_json=json.dumps(definition)
                        )
                    )
        except Exception:
            pass

        # Convert to FilterFieldType objects
        # We need to map the generator's GroupedFieldFilter to the GraphQL FilterFieldType
        # Note: We are reusing the existing FilterFieldType which might differ slightly from the plan's ideal.
        # We'll map as best as possible.
        
        fields = []
        for gf in grouped_filters:
            options = []
            for op in gf.operations:
                options.append(
                    FilterOptionType(
                        name=op.name,
                        lookup_expr=op.lookup_expr,
                        help_text=op.description or "",
                        filter_type=op.filter_type,
                        choices=[], 
                    )
                )
            
            fields.append(
                FilterFieldType(
                    field_name=gf.field_name,
                    is_nested=False, # TODO: Detect nested
                    related_model=None, # TODO: Detect relation
                    is_custom=False,
                    field_label=gf.field_name,
                    options=options,
                    nested=[],
                    filter_input_type=gf.field_type + "FilterInput", # Guessing naming convention
                    available_operators=[op.name for op in gf.operations]
                )
            )

        from ..core.settings import FilteringSettings
        filtering_settings = None
        try:
            filtering_settings = FilteringSettings.from_schema(schema_name)
        except Exception:
            pass
            
        supports_fts = getattr(filtering_settings, "enable_full_text_search", False) if filtering_settings else False

        return FilterSchemaType(
            model=model,
            fields=fields,
            presets=presets,
            supports_fts=supports_fts,
            supports_aggregation=True
        )

    except Exception as e:
        logger.error(f"Error resolving filter schema: {e}")
        return None


class ModelMetadataExtractor:
    """Extracts comprehensive metadata from Django models."""

    def __init__(self, schema_name: str = "default", max_depth: int = 1):
        """
        Initialize the metadata extractor.

        Args:
            schema_name: Name of the schema configuration to use
            max_depth: Maximum depth for nested related model metadata
        """
        # Lazy import to avoid AppRegistryNotReady
        # from ..core.settings import get_schema_settings

        self.schema_name = schema_name
        self.max_depth = max_depth
        # self.settings = get_schema_settings(schema_name)

    def _json_safe_value(self, value: Any) -> Any:
        """Convert Django/Python values (dates, decimals, lazy translations) to JSON-serializable primitives."""
        from datetime import date, datetime, time
        from decimal import Decimal

        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, time)):
            try:
                return value.isoformat()
            except Exception:
                return force_str(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {
                force_str(key): self._json_safe_value(val) for key, val in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe_value(val) for val in value]
        return force_str(value)

    def _sanitize_action_payload(self, payload: Any) -> Any:
        """Strip callables and non-serializable values from action metadata."""
        if payload is None:
            return None
        if isinstance(payload, dict):
            cleaned: dict[str, Any] = {}
            for key, val in payload.items():
                if callable(val):
                    continue
                cleaned[force_str(key)] = self._sanitize_action_payload(val)
            return cleaned
        if isinstance(payload, (list, tuple, set)):
            return [
                self._sanitize_action_payload(val)
                for val in payload
                if not callable(val)
            ]
        return self._json_safe_value(payload)

    @cache_metadata(
        timeout=0,
        user_specific=True,
        # timeout=1200, user_specific=True
    )  # 20 minutes cache for field metadata
    def _extract_field_metadata(self, field, user) -> Optional[FieldMetadata]:
        """
        Extract metadata for a single field with permission checking.

        Args:
            field: Django model field instance

        Returns:
            FieldMetadata if user has permission, None otherwise
        """
        # Lazy import to avoid AppRegistryNotReady
        from django.db import models

        # Get field choices
        choices = None
        if hasattr(field, "choices") and field.choices:
            choices = [
                {
                    "value": self._json_safe_value(choice[0]),
                    "label": force_str(choice[1]),
                }
                for choice in field.choices
            ]

        # Get max length
        max_length = getattr(field, "max_length", None)
        min_length = getattr(field, "min_length", None)
        min_value = None
        max_value = None
        regex = None
        validators = getattr(field, "validators", None) or []
        try:
            from django.core.validators import (
                MaxLengthValidator,
                MaxValueValidator,
                MinLengthValidator,
                MinValueValidator,
                RegexValidator,
            )
        except (ImportError, AttributeError) as exc:
            logger.debug("Validator imports unavailable: %s", exc)
        else:
            for validator in validators:
                if isinstance(validator, MinValueValidator):
                    min_value = validator.limit_value
                elif isinstance(validator, MaxValueValidator):
                    max_value = validator.limit_value
                elif isinstance(validator, MinLengthValidator) and min_length is None:
                    min_length = validator.limit_value
                elif isinstance(validator, MaxLengthValidator) and max_length is None:
                    max_length = validator.limit_value
                elif isinstance(validator, RegexValidator):
                    try:
                        regex = validator.regex.pattern
                    except (AttributeError, TypeError):
                        regex = str(getattr(validator, "regex", None) or "")

        db_column = getattr(field, "db_column", None) or getattr(field, "column", None)
        internal_type = None
        try:
            internal_type = field.get_internal_type()
        except (AttributeError, TypeError, NotImplementedError):
            internal_type = None

        db_type = None
        try:
            from django.db import DatabaseError, connection

            db_type = field.db_type(connection)
        except (AttributeError, TypeError, ValueError, NotImplementedError, DatabaseError):
            db_type = None

        # Get on_delete behavior for foreign keys (guard None)
        on_delete = None
        if getattr(field, "remote_field", None) is not None:
            remote_on_delete = getattr(field.remote_field, "on_delete", None)
            if remote_on_delete:
                on_delete = getattr(remote_on_delete, "__name__", None)

        # Simplified permission flag; adjust with actual permission checks if needed
        has_permission = True
        is_fsm_field = _is_fsm_field_instance(field)
        editable_flag = bool(field.editable) and not is_fsm_field
        default_value = (
            self._json_safe_value(field.default)
            if field.default != models.NOT_PROVIDED
            else None
        )

        return FieldMetadata(
            name=field.name,
            field_type=field.__class__.__name__,
            is_required=not field.blank and field.default == models.NOT_PROVIDED,
            is_nullable=field.null,
            null=field.null,
            default_value=default_value,
            help_text=field.help_text or "",
            db_column=db_column,
            db_type=db_type,
            internal_type=internal_type,
            max_length=max_length,
            min_length=min_length,
            min_value=min_value,
            max_value=max_value,
            regex=regex,
            choices=choices,
            is_primary_key=getattr(field, "primary_key", None),
            is_foreign_key=isinstance(field, models.ForeignKey),
            is_unique=field.unique,
            is_indexed=field.db_index,
            has_auto_now=getattr(field, "auto_now", False),
            has_auto_now_add=getattr(field, "auto_now_add", False),
            blank=field.blank,
            editable=editable_flag,
            verbose_name=str(field.verbose_name),
            has_permission=has_permission,
        )

    @cache_metadata(
        timeout=1200, user_specific=True
    )  # 20 minutes cache for relationship metadata
    def _extract_relationship_metadata(
        self, field, user, current_depth: int = 0
    ) -> Optional[RelationshipMetadata]:
        """
        Extract metadata for relationship fields.

        Args:
            field: Django relationship field instance

        Returns:
            RelationshipMetadata if user has permission, None otherwise
        """
        # Lazy import to avoid AppRegistryNotReady
        from django.db import models

        related_model = field.related_model
        on_delete = None

        if getattr(field, "remote_field", None) is not None:
            remote_on_delete = getattr(field.remote_field, "on_delete", None)
            if remote_on_delete:
                on_delete = getattr(remote_on_delete, "__name__", None)

        # Simplified permission flag; adjust with actual checks if needed
        has_permission = True

        if related_model is None or not hasattr(related_model, "_meta"):
            return None

        related_app_label = getattr(related_model._meta, "app_label", "")
        related_model_class_name = related_model.__name__
        many_to_many = isinstance(field, models.ManyToManyField)
        one_to_one = isinstance(field, models.OneToOneField)
        foreign_key = isinstance(field, models.ForeignKey)

        return RelationshipMetadata(
            name=field.name,
            relationship_type=field.__class__.__name__,
            cardinality=_relationship_cardinality(
                False, many_to_many, one_to_one, foreign_key
            ),
            related_model=related_model_class_name,
            is_required=not field.blank,
            related_app=related_app_label,
            to_field=field.remote_field.name
            if hasattr(field, "remote_field") and field.remote_field
            else None,
            from_field=field.name,
            is_reverse=False,
            many_to_many=many_to_many,
            one_to_one=one_to_one,
            foreign_key=foreign_key,
            on_delete=on_delete,
            related_name=getattr(field, "related_name", None),
            has_permission=has_permission,
            verbose_name=field.verbose_name,
        )

    @cache_metadata(
        timeout=1800, user_specific=True
    )  # 30 minutes cache for complete model metadata
    def extract_model_metadata(
        self,
        app_name: str,
        model_name: str,
        user,
        nested_fields: bool = True,
        permissions_included: bool = True,
        include_filters: bool = True,
        include_mutations: bool = True,
        current_depth: int = 0,
    ) -> Optional[ModelMetadata]:
        """
        Extract complete metadata for a Django model.

        Args:
            app_name: Django app label
            model_name: Model class name
            user: Current user for permission checking
            nested_fields: Whether to include relationship metadata
            permissions_included: Whether to include permission information
            include_filters: Whether to include filter metadata
            include_mutations: Whether to include mutation metadata

        Returns:
            ModelMetadata with filtered fields based on permissions, or None on error
        """
        # Resolve the model from app and model name
        try:
            model = apps.get_model(app_name, model_name)
        except Exception as e:
            logger.error(
                "Model '%s' not found in app '%s': %s", model_name, app_name, e
            )
            return None

        introspector = ModelIntrospector.for_model(model, self.schema_name)

        # Extract field metadata with permission filtering using concrete model fields
        fields = []
        for django_field in model._meta.get_fields():
            # Only include concrete fields (exclude relations and auto-created reverse accessors)
            if getattr(django_field, "is_relation", False):
                continue
            if getattr(django_field, "auto_created", False):
                continue
            field_metadata = self._extract_field_metadata(django_field, user)
            if field_metadata:
                fields.append(field_metadata)

        # Extract relationship metadata with permission filtering (declared relations only)
        relationships = []
        if nested_fields:
            for django_field in model._meta.get_fields():
                if not getattr(django_field, "is_relation", False):
                    continue
                # Skip polymorphic_ctype field
                if django_field.name == "polymorphic_ctype":
                    continue
                # Skip auto-created reverse relations; they will be added below
                if getattr(django_field, "auto_created", False):
                    continue
                rel_metadata = self._extract_relationship_metadata(
                    django_field, user, current_depth=current_depth
                )
                if rel_metadata:
                    relationships.append(rel_metadata)

        # Always include reverse relationships
        if nested_fields:
            reverse_relations = []
            if hasattr(model._meta, "related_objects"):
                reverse_relations = list(model._meta.related_objects)
            for rel in reverse_relations:
                related_model = getattr(rel, "related_model", None)
                if related_model is None or not hasattr(related_model, "_meta"):
                    continue
                accessor_name = rel.get_accessor_name()
                rel_field = getattr(rel, "field", None)
                many_to_many = bool(getattr(rel, "many_to_many", False)) or (
                    rel_field is not None
                    and isinstance(rel_field, models.ManyToManyField)
                )
                one_to_one = bool(getattr(rel, "one_to_one", False)) or (
                    rel_field is not None and isinstance(rel_field, models.OneToOneField)
                )
                foreign_key = bool(getattr(rel, "many_to_one", False)) or (
                    rel_field is not None and isinstance(rel_field, models.ForeignKey)
                )
                relationship_type = (
                    rel_field.__class__.__name__ if rel_field else "ReverseRelation"
                )
                related_app_label = getattr(related_model._meta, "app_label", "")
                relationships.append(
                    RelationshipMetadata(
                        name=accessor_name,
                        verbose_name=related_model._meta.verbose_name,
                        relationship_type=relationship_type,
                        cardinality=_relationship_cardinality(
                            True, many_to_many, one_to_one, foreign_key
                        ),
                        related_model=related_model.__name__,
                        related_app=related_app_label,
                        to_field=getattr(rel_field, "name", None),
                        is_required=False,
                        from_field=accessor_name,
                        is_reverse=True,
                        many_to_many=many_to_many,
                        one_to_one=one_to_one,
                        foreign_key=foreign_key,
                        on_delete=None,
                        related_name=accessor_name,
                        has_permission=True,
                    )
                )
            if not reverse_relations:
                reverse_relations = introspector.get_reverse_relations()
                for rel_name, related_model in reverse_relations.items():
                    related_app_label = getattr(related_model._meta, "app_label", "")
                    relationships.append(
                        RelationshipMetadata(
                            name=rel_name,
                            verbose_name=related_model._meta.verbose_name,
                            relationship_type="ReverseRelation",
                            cardinality=_relationship_cardinality(
                                True, False, False, False
                            ),
                            related_model=related_model.__name__,
                            related_app=related_app_label,
                            to_field=None,
                            is_required=False,
                            from_field=rel_name,
                            is_reverse=True,
                            many_to_many=False,
                            one_to_one=False,
                            foreign_key=False,
                            on_delete=None,
                            related_name=rel_name,
                            has_permission=True,
                        )
                    )

        # Get model permissions for the user
        permissions = []
        if permissions_included and user:
            # Lazy import to avoid AppRegistryNotReady
            from django.contrib.auth.models import AnonymousUser

            if not isinstance(user, AnonymousUser):
                app_label = model._meta.app_label
                model_name_code = model._meta.model_name

                # Check standard Django permissions
                for action in ["add", "change", "delete", "view"]:
                    perm_code = f"{app_label}.{action}_{model_name_code}"
                    try:
                        if user.has_perm(perm_code):
                            permissions.append(perm_code)
                    except Exception:
                        continue

        # Get ordering
        ordering = list(model._meta.ordering) if model._meta.ordering else []
        default_ordering = ordering.copy()
        if not default_ordering:
            if getattr(model._meta, "get_latest_by", None):
                default_ordering = [f"-{model._meta.get_latest_by}"]
            else:
                default_ordering = [model._meta.pk.name]

        # Get unique_together
        unique_together = []
        if hasattr(model._meta, "unique_together") and model._meta.unique_together:
            unique_together = [
                list(constraint) for constraint in model._meta.unique_together
            ]

        # Get unique constraints
        unique_constraints = []
        if hasattr(model._meta, "constraints"):
            for constraint in model._meta.constraints:
                if isinstance(constraint, models.UniqueConstraint):
                    unique_constraints.append(
                        {
                            "name": constraint.name,
                            "fields": list(getattr(constraint, "fields", []) or []),
                            "condition": str(constraint.condition)
                            if getattr(constraint, "condition", None)
                            else None,
                            "deferrable": getattr(constraint, "deferrable", None),
                        }
                    )

        # Get indexes
        indexes = []
        if hasattr(model._meta, "indexes"):
            for index in model._meta.indexes:
                indexes.append(
                    {
                        "name": index.name,
                        "fields": list(index.fields),
                        "unique": getattr(index, "unique", False),
                        "condition": str(index.condition)
                        if getattr(index, "condition", None)
                        else None,
                        "include": list(getattr(index, "include", []) or []),
                    }
                )

        # Extract filter metadata
        filters = self._extract_filter_metadata(model) if include_filters else []

        # Extract mutations metadata (user-aware for permission filtering)
        mutations = (
            self.extract_mutations_metadata(model, user) if include_mutations else []
        )

        return ModelMetadata(
            metadata_version=_get_metadata_version_value(app_name, model_name),
            app_name=model._meta.app_label,
            model_name=model.__name__,
            verbose_name=str(model._meta.verbose_name),
            verbose_name_plural=str(model._meta.verbose_name_plural),
            table_name=model._meta.db_table,
            primary_key_field=model._meta.pk.name,
            fields=fields,
            relationships=relationships,
            permissions=permissions,
            ordering=ordering,
            default_ordering=default_ordering,
            unique_together=unique_together,
            unique_constraints=unique_constraints,
            indexes=indexes,
            abstract=model._meta.abstract,
            proxy=model._meta.proxy,
            managed=model._meta.managed,
            filters=filters,
            mutations=mutations,
        )

    def _has_field_permission(self, user, model: type, field_name: str) -> bool:
        """
        Check if user has permission to access a specific field.

        Args:
            user: Django user instance
            model: Django model class
            field_name: Name of the field to check

        Returns:
            bool: True if user has permission to access the field
        """
        # Lazy import to avoid AppRegistryNotReady
        from django.contrib.auth.models import AnonymousUser

        if isinstance(user, AnonymousUser):
            return False

        # Check basic view permission for the model
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        view_permission = f"{app_label}.view_{model_name}"

        try:
            return user.has_perm(view_permission)
        except Exception:
            return False

    @cache_metadata(
        timeout=1800, user_specific=False
    )  # 30 minutes cache for filter metadata (not user-specific)
    def _extract_filter_metadata(self, model) -> list[dict[str, Any]]:
        """
        Extract comprehensive filter metadata for a Django model with enhanced features.

        Args:
            model: Django model class

        Returns:
            List of grouped filter field metadata dictionaries
        """
        try:
            # Import the enhanced filter generator
            from ..generators.filter_inputs import (
                AdvancedFilterGenerator,
                EnhancedFilterGenerator,
            )
            from ..utils.graphql_meta import get_model_graphql_meta

            # Use the instance's max_depth parameter
            max_depth = self.max_depth

            # Create enhanced filter generator instance with configurable depth
            enhanced_generator = EnhancedFilterGenerator(
                max_nested_depth=max_depth,
                enable_nested_filters=True,
                schema_name=self.schema_name,
            )

            # Get grouped filters for the model
            grouped_filters = enhanced_generator.get_grouped_filters(model)

            # Get GraphQL meta for custom filters
            graphql_meta = get_model_graphql_meta(model)

            # Create a dictionary to group filters by field name
            grouped_filter_dict = {}

            # Process enhanced filters
            for grouped_filter in grouped_filters:
                field_name = grouped_filter.field_name

                # Exclude the primary key 'id' field from filter metadata
                if field_name == "id" or "quick" in field_name:
                    continue

                # Get field verbose name for help text
                try:
                    field = model._meta.get_field(field_name)
                    verbose_name = str(field.verbose_name)
                except Exception:
                    # Ensure 'field' is defined to avoid UnboundLocalError later
                    field = None
                    verbose_name = field_name

                options = []
                for operation in grouped_filter.operations:
                    filter_name = (
                        f"{field_name}__{operation.lookup_expr}"
                        if operation.lookup_expr != "exact"
                        else field_name
                    )

                    # Translate help text to French using verbose_name
                    # Be defensive: some operations may not have description
                    help_text = self._translate_help_text_to_french(
                        operation.description or operation.lookup_expr, verbose_name
                    )

                    # Include choices if this is a CharField with declared choices (primarily for exact)
                    option_choices = None
                    if field is not None and isinstance(field, models.CharField):
                        raw_choices = getattr(field, "choices", None)
                        if raw_choices:
                            try:
                                option_choices = [
                                    {
                                        "value": self._json_safe_value(val),
                                        "label": force_str(lbl),
                                    }
                                    for val, lbl in raw_choices
                                ]
                            except Exception:
                                option_choices = None

                    options.append(
                        {
                            "name": filter_name,
                            "lookup_expr": operation.lookup_expr,
                            "help_text": help_text,
                            "filter_type": operation.filter_type,
                            "choices": option_choices,
                        }
                    )
                # Safely resolve related model name even when 'field' lookup fails
                related_model_name = (
                    field.related_model.__name__
                    if (field is not None and getattr(field, "related_model", None))
                    else None
                )

                grouped_filter_dict[field_name] = {
                    "field_name": field_name,
                    "is_nested": False,
                    "related_model": related_model_name,
                    "is_custom": False,
                    "field_label": verbose_name,
                    "options": options,
                }

            # Add nested filters from traditional generator - RESTRUCTURED TO PARENT LEVEL
            try:
                filter_generator = AdvancedFilterGenerator(
                    max_nested_depth=max_depth,  # Use configurable depth
                    enable_nested_filters=True,
                    schema_name=self.schema_name,
                )

                filter_class = filter_generator.generate_filter_set(model)

                # Process nested filters and GROUP them under the base field name
                for filter_name, filter_instance in filter_class.base_filters.items():
                    if "quick" in filter_name:
                        continue

                    if "__" in filter_name and not filter_name.endswith("_count"):
                        field_parts = filter_name.split("__")
                        base_field_name = field_parts[0]
                        lookup_expr = "__".join(field_parts[1:])

                        # Optional depth control (kept if present elsewhere)
                        try:
                            if len(field_parts) - 1 > max_depth:  # type: ignore[name-defined]
                                continue
                        except Exception:
                            # If max_depth is not defined, proceed without depth restriction
                            pass

                        # Get related model info
                        related_model = None
                        try:
                            field = model._meta.get_field(base_field_name)
                            if hasattr(field, "related_model"):
                                related_model = field.related_model.__name__
                        except:
                            continue

                        # Get verbose name for nested field
                        try:
                            verbose_name = str(field.verbose_name)
                        except:
                            verbose_name = base_field_name

                        # GROUP: Add nested filter as an option under the base field
                        help_text = self._translate_help_text_to_french(
                            lookup_expr, verbose_name
                        )

                        if base_field_name not in grouped_filter_dict:
                            grouped_filter_dict[base_field_name] = {
                                "field_name": base_field_name,
                                "is_nested": True,
                                "related_model": related_model,
                                "is_custom": False,
                                "field_label": verbose_name,
                                "options": [],
                            }

                        grouped_filter_dict[base_field_name]["options"].append(
                            {
                                "name": filter_name,  # full path for execution
                                "lookup_expr": lookup_expr,
                                "help_text": help_text,
                                "filter_type": filter_instance.__class__.__name__,
                            }
                        )

                # Add property filters for @property-based fields
                try:
                    from ..generators.introspector import ModelIntrospector

                    introspector = ModelIntrospector.for_model(model, self.schema_name)
                    property_map = getattr(introspector, "properties", {}) or {}
                    property_names = set(property_map.keys())

                    # Iterate base filters and group property filters under property name
                    for fname, finstance in getattr(
                        filter_class, "base_filters", {}
                    ).items():
                        base_name = fname.split("__")[0]
                        if "quick" in base_name:
                            continue
                        if base_name in property_names:
                            lookup_expr = "__".join(fname.split("__")[1:]) or "exact"
                            prop_obj = property_map.get(base_name)
                            # Prefer fget.short_description when available for properties
                            verbose = (
                                getattr(
                                    getattr(prop_obj, "fget", None),
                                    "short_description",
                                    None,
                                )
                                or getattr(prop_obj, "verbose_name", None)
                                or base_name
                            )
                            original_help = (
                                getattr(finstance, "help_text", None)
                                or getattr(finstance, "label", "")
                                or f"Filter for {base_name}"
                            )
                            help_text = self._translate_help_text_to_french(
                                original_help, verbose
                            )

                            if base_name not in grouped_filter_dict:
                                grouped_filter_dict[base_name] = {
                                    "field_name": base_name,
                                    "is_nested": False,
                                    "related_model": None,
                                    "is_custom": False,
                                    "field_label": verbose,
                                    "options": [],
                                }

                            grouped_filter_dict[base_name]["options"].append(
                                {
                                    "name": fname,
                                    "lookup_expr": lookup_expr,
                                    "help_text": help_text,
                                    "filter_type": finstance.__class__.__name__,
                                }
                            )
                except Exception as e:
                    logger.warning(
                        f"Error processing property filters for {model.__name__}: {e}"
                    )

            except Exception as e:
                logger.warning(
                    f"Error processing nested filters for {model.__name__}: {e}"
                )

            # ENHANCED: Add custom filters from GraphQLMeta with better quick filter support
            if graphql_meta:
                # Add quick filters with comprehensive field support
                if (
                    hasattr(graphql_meta, "quick_filter_fields")
                    and graphql_meta.quick_filter_fields
                ):
                    quick_fields = graphql_meta.quick_filter_fields

                    # Create comprehensive quick filter entry
                    grouped_filter_dict["quick"] = {
                        "field_name": "quick",
                        "is_nested": False,
                        "related_model": None,
                        "is_custom": True,
                        "field_label": "Quick filter",
                        "options": [
                            {
                                "name": "quick",
                                "lookup_expr": "icontains",
                                "help_text": f"Recherche rapide dans les champs: {', '.join(quick_fields)}",
                                "filter_type": "CharFilter",
                            }
                        ],
                    }

                    # Also add individual quick filter options for each field
                    # for quick_field in quick_fields:
                    #     if "__" in quick_field:  # Handle nested quick fields
                    #         # Add nested quick field as separate filter
                    #         quick_filter_name = (
                    #             f"quick_{quick_field.replace('__', '_')}"
                    #         )
                    #         grouped_filter_dict[quick_filter_name] = {
                    #             "field_name": quick_filter_name,
                    #             "is_nested": True,
                    #             "related_model": self._get_related_model_name(
                    #                 model, quick_field
                    #             ),
                    #             "is_custom": True,
                    #             "field_label": quick_filter_name,
                    #             "options": [
                    #                 {
                    #                     "name": quick_filter_name,
                    #                     "lookup_expr": "icontains",
                    #                     "help_text": f"Recherche rapide dans {quick_field}",
                    #                     "filter_type": "CharFilter",
                    #                 }
                    #             ],
                    #         }

                # Add custom filters
                if (
                    hasattr(graphql_meta, "custom_filters")
                    and graphql_meta.custom_filters
                ):
                    for (
                        custom_name,
                        custom_method,
                    ) in graphql_meta.custom_filters.items():
                        if "quick" in custom_name:
                            continue
                        grouped_filter_dict[custom_name] = {
                            "field_name": custom_name,
                            "is_nested": False,
                            "related_model": None,
                            "is_custom": True,
                            "field_label": custom_name,
                            "options": [
                                {
                                    "name": custom_name,
                                    "lookup_expr": "custom",
                                    "help_text": f"Filtre personnalisé: {custom_name}",
                                    "filter_type": "CustomFilter",
                                }
                            ],
                        }

            # Convert to list format and sort for consistency
            # Fallback: if no filters were constructed, build a minimal set
            if not grouped_filter_dict:
                try:
                    for f in model._meta.get_fields():
                        if not hasattr(f, "name") or getattr(f, "auto_created", False):
                            continue

                        fname = f.name
                        if fname == "id":
                            # Exclude id from minimal filter construction as requested
                            continue
                        verbose = str(getattr(f, "verbose_name", fname))
                        options = []

                        # Minimal operation set per common field types
                        if isinstance(f, (models.CharField, models.TextField)):
                            for lookup in ("exact", "icontains"):
                                help_text = self._translate_help_text_to_french(
                                    lookup, verbose
                                )
                                option_choices = None
                                if lookup == "exact" and isinstance(
                                    f, models.CharField
                                ):
                                    raw_choices = getattr(f, "choices", None)
                                    if raw_choices:
                                        try:
                                            option_choices = [
                                                {
                                                    "value": self._json_safe_value(val),
                                                    "label": force_str(lbl),
                                                }
                                                for val, lbl in raw_choices
                                            ]
                                        except Exception:
                                            option_choices = None
                                options.append(
                                    {
                                        "name": fname
                                        if lookup == "exact"
                                        else f"{fname}__{lookup}",
                                        "lookup_expr": lookup,
                                        "help_text": help_text,
                                        "filter_type": "CharFilter",
                                        "choices": option_choices,
                                    }
                                )
                        elif isinstance(
                            f,
                            (
                                models.IntegerField,
                                models.FloatField,
                                models.DecimalField,
                            ),
                        ):
                            for lookup in ("exact", "gt", "gte", "lt", "lte"):
                                help_text = self._translate_help_text_to_french(
                                    lookup, verbose
                                )
                                options.append(
                                    {
                                        "name": fname
                                        if lookup == "exact"
                                        else f"{fname}__{lookup}",
                                        "lookup_expr": lookup,
                                        "help_text": help_text,
                                        "filter_type": "NumberFilter",
                                    }
                                )
                        elif isinstance(f, (models.DateField, models.DateTimeField)):
                            for lookup in (
                                "exact",
                                "range",
                                "today",
                                "this_month",
                                "this_year",
                            ):
                                help_text = self._translate_help_text_to_french(
                                    lookup, verbose
                                )
                                options.append(
                                    {
                                        "name": fname
                                        if lookup == "exact"
                                        else f"{fname}__{lookup}",
                                        "lookup_expr": lookup,
                                        "help_text": help_text,
                                        "filter_type": "DateFilter",
                                    }
                                )
                        elif isinstance(f, models.BooleanField):
                            for lookup in ("exact", "isnull"):
                                help_text = self._translate_help_text_to_french(
                                    lookup, verbose
                                )
                                options.append(
                                    {
                                        "name": fname
                                        if lookup == "exact"
                                        else f"{fname}__{lookup}",
                                        "lookup_expr": lookup,
                                        "help_text": help_text,
                                        "filter_type": "BooleanFilter",
                                    }
                                )
                        elif isinstance(f, models.ForeignKey):
                            # Basic FK filter: exact by id
                            help_text = self._translate_help_text_to_french(
                                "exact", verbose
                            )
                            options.append(
                                {
                                    "name": fname,
                                    "lookup_expr": "exact",
                                    "help_text": help_text,
                                    "filter_type": "NumberFilter",
                                }
                            )
                        elif isinstance(f, models.ManyToManyField):
                            # Basic M2M filter: in
                            help_text = self._translate_help_text_to_french(
                                "in", verbose
                            )
                            options.append(
                                {
                                    "name": f"{fname}__in",
                                    "lookup_expr": "in",
                                    "help_text": help_text,
                                    "filter_type": "ModelMultipleChoiceFilter",
                                }
                            )

                        if options:
                            grouped_filter_dict[fname] = {
                                "field_name": fname,
                                "is_nested": False,
                                "related_model": getattr(
                                    getattr(f, "related_model", None), "__name__", None
                                ),
                                "is_custom": False,
                                "field_label": verbose,
                                "options": options,
                            }
                except Exception as e:
                    logger.warning(
                        f"Fallback filter construction failed for {model.__name__}: {e}"
                    )

            result = list(grouped_filter_dict.values())
            # Sort filters: regular fields first, then nested, then custom
            result.sort(key=lambda x: (x["is_custom"], x["is_nested"], x["field_name"]))
            return result

        except Exception as e:
            logger.error(f"Error extracting filter metadata for {model.__name__}: {e}")
            return []

    def _get_related_model_name(self, model, field_path: str) -> Optional[str]:
        """
        Get the related model name for a nested field path.

        Args:
            model: Base Django model
            field_path: Field path like 'author__username'

        Returns:
            Related model name or None
        """
        try:
            field_parts = field_path.split("__")
            current_model = model

            for field_name in field_parts[:-1]:  # Exclude the final field
                field = current_model._meta.get_field(field_name)
                if hasattr(field, "related_model"):
                    current_model = field.related_model
                else:
                    return None

            return current_model.__name__
        except:
            return None

    def _translate_help_text_to_french(
        self, original_text: str, verbose_name: str
    ) -> str:
        """
        Translate help text to French using field verbose_name.

        Args:
            original_text: Original English help text
            verbose_name: Field verbose name to use in translation

        Returns:
            French translated help text
        """
        # Basic translation mapping
        translations = {
            "exact": f"Correspondance exacte pour {verbose_name}",
            "iexact": f"Correspondance exacte insensible à la casse pour {verbose_name}",
            "contains": f"Contient le texte dans {verbose_name}",
            "icontains": f"Contient le texte (insensible à la casse) dans {verbose_name}",
            "startswith": f"Commence par le texte dans {verbose_name}",
            "istartswith": f"Commence par le texte (insensible à la casse) dans {verbose_name}",
            "endswith": f"Se termine par le texte dans {verbose_name}",
            "iendswith": f"Se termine par le texte (insensible à la casse) dans {verbose_name}",
            "in": f"Correspond à l'une des valeurs fournies pour {verbose_name}",
            "gt": f"Supérieur à la valeur pour {verbose_name}",
            "gte": f"Supérieur ou égal à la valeur pour {verbose_name}",
            "lt": f"Inférieur à la valeur pour {verbose_name}",
            "lte": f"Inférieur ou égal à la valeur pour {verbose_name}",
            "range": f"Valeur dans la plage pour {verbose_name}",
            "isnull": f"Vérifier si {verbose_name} est nul",
            "today": f"Filtrer pour la date d'aujourd'hui dans {verbose_name}",
            "yesterday": f"Filtrer pour la date d'hier dans {verbose_name}",
            "this_week": f"Filtrer pour les dates de cette semaine dans {verbose_name}",
            "this_month": f"Filtrer pour les dates de ce mois dans {verbose_name}",
            "this_year": f"Filtrer pour les dates de cette année dans {verbose_name}",
            "past_week": f"Filtrer pour les dates de la semaine dernière dans {verbose_name}",
            "past_month": f"Filtrer pour les dates du mois dernier dans {verbose_name}",
            "past_year": f"Filtrer pour les dates de l'année dernière dans {verbose_name}",
            "last_week": f"Filtrer pour les dates de la semaine dernière dans {verbose_name}",
            "last_month": f"Filtrer pour les dates du mois dernier dans {verbose_name}",
            "last_year": f"Filtrer pour les dates de l'année dernière dans {verbose_name}",
            "year": f"Filtrer par année pour {verbose_name}",
            "month": f"Filtrer par mois pour {verbose_name}",
            "day": f"Filtrer par jour pour {verbose_name}",
        }

        # Normalize for matching
        original_lc = original_text.lower()

        # Prioritize relative date/time lookups so they aren't overshadowed by generic matches
        for rel_lookup in (
            "today",
            "yesterday",
            "this_week",
            "this_month",
            "this_year",
            "past_week",
            "past_month",
            "past_year",
            "last_week",
            "last_month",
            "last_year",
            "year",
            "month",
            "day",
        ):
            if rel_lookup in original_lc:
                return translations[rel_lookup]

        # Then match common generic lookups
        for gen_lookup in (
            "exact",
            "iexact",
            "contains",
            "icontains",
            "startswith",
            "istartswith",
            "endswith",
            "iendswith",
            "in",
            "gt",
            "gte",
            "lt",
            "lte",
            "range",
            "isnull",
        ):
            if gen_lookup in original_lc:
                return translations[gen_lookup]

        # Fallback: basic translation
        if "exact match" in original_lc:
            return f"Correspondance exacte pour {verbose_name}"
        elif "contains" in original_lc:
            return f"Contient le texte dans {verbose_name}"
        elif "greater than" in original_lc:
            return f"Supérieur à la valeur pour {verbose_name}"
        elif "less than" in original_lc:
            return f"Inférieur à la valeur pour {verbose_name}"
        else:
            return f"Filtre pour {verbose_name}"

    @cache_metadata(timeout=900, user_specific=True)
    def extract_mutations_metadata(
        self, model: type[models.Model], user=None
    ) -> list[MutationMetadata]:
        """
        Extract mutation metadata for a Django model.

        Args:
            model: Django model class

        Returns:
            List of MutationMetadata objects
        """
        try:
            from ..config_proxy import get_mutation_generator_settings
            from ..generators.mutations import MutationGenerator
            from ..generators.types import TypeGenerator

            mutations = []
            model_name = model.__name__

            # Initialize mutation generator
            type_generator = TypeGenerator(schema_name=self.schema_name)
            mutation_settings = get_mutation_generator_settings(self.schema_name)
            mutation_generator = MutationGenerator(
                type_generator=type_generator,
                settings=mutation_settings,
                schema_name=self.schema_name,
            )

            # Generate CRUD mutations if enabled
            if mutation_settings.enable_create:
                create_mutation = self._extract_create_mutation_metadata(
                    model, mutation_generator
                )
                if create_mutation:
                    mutations.append(create_mutation)

            if mutation_settings.enable_update:
                update_mutation = self._extract_update_mutation_metadata(
                    model, mutation_generator
                )
                if update_mutation:
                    mutations.append(update_mutation)

            if mutation_settings.enable_delete:
                delete_mutation = self._extract_delete_mutation_metadata(
                    model, mutation_generator
                )
                if delete_mutation:
                    mutations.append(delete_mutation)

            # Generate bulk mutations if enabled
            if mutation_settings.enable_bulk_operations:
                bulk_mutations = self._extract_bulk_mutations_metadata(
                    model, mutation_generator
                )
                mutations.extend(bulk_mutations)

            # Generate method mutations if enabled
            if mutation_settings.enable_method_mutations:
                method_mutations = self._extract_method_mutations_metadata(
                    model, mutation_generator, user=user
                )
                mutations.extend(method_mutations)

            return mutations

        except Exception as e:
            logger.error(
                f"Error extracting mutations metadata for {model.__name__}: {e}"
            )
            return []

    def _extract_create_mutation_metadata(
        self, model: type[models.Model], mutation_generator
    ) -> Optional[MutationMetadata]:
        """Extract metadata for create mutation."""
        try:
            model_name = model.__name__
            input_fields = self._extract_input_fields_from_model(model, "create")

            return MutationMetadata(
                name=f"create_{model_name.lower()}",
                description=f"Create a new {model_name} instance",
                input_fields=input_fields,
                return_type=f"{model_name}Type",
                requires_authentication=True,
                required_permissions=[
                    f"{model._meta.app_label}.add_{model._meta.model_name}"
                ],
                mutation_type="create",
                model_name=model_name,
                success_message=f"{model_name} created successfully",
                form_config={
                    "title": f"Create {model_name}",
                    "submit_text": "Create",
                    "cancel_text": "Cancel",
                },
            )
        except Exception as e:
            logger.error(f"Error extracting create mutation metadata: {e}")
            return None

    def _extract_update_mutation_metadata(
        self, model: type[models.Model], mutation_generator
    ) -> Optional[MutationMetadata]:
        """Extract metadata for update mutation."""
        try:
            model_name = model.__name__
            input_fields = self._extract_input_fields_from_model(model, "update")

            # Add ID field for update
            id_field = InputFieldMetadata(
                name="id",
                field_type="ID",
                required=True,
                description=f"ID of the {model_name} to update",
                widget_type="hidden",
            )
            input_fields.insert(0, id_field)

            return MutationMetadata(
                name=f"update_{model_name.lower()}",
                description=f"Update an existing {model_name} instance",
                input_fields=input_fields,
                return_type=f"{model_name}Type",
                requires_authentication=True,
                required_permissions=[f"change_{model._meta.model_name}"],
                mutation_type="update",
                model_name=model_name,
                success_message=f"{model_name} updated successfully",
                form_config={
                    "title": f"Update {model_name}",
                    "submit_text": "Update",
                    "cancel_text": "Cancel",
                },
            )
        except Exception as e:
            logger.error(f"Error extracting update mutation metadata: {e}")
            return None

    def _extract_delete_mutation_metadata(
        self, model: type[models.Model], mutation_generator
    ) -> Optional[MutationMetadata]:
        """Extract metadata for delete mutation."""
        try:
            model_name = model.__name__

            id_field = InputFieldMetadata(
                name="id",
                field_type="ID",
                required=True,
                description=f"ID of the {model_name} to delete",
                widget_type="hidden",
            )

            return MutationMetadata(
                name=f"delete_{model_name.lower()}",
                description=f"Delete a {model_name} instance",
                input_fields=[id_field],
                return_type="Boolean",
                requires_authentication=True,
                required_permissions=[f"delete_{model._meta.model_name}"],
                mutation_type="delete",
                model_name=model_name,
                success_message=f"{model_name} deleted successfully",
                form_config={
                    "title": f"Delete {model_name}",
                    "submit_text": "Delete",
                    "cancel_text": "Cancel",
                    "confirmation_required": True,
                    "confirmation_message": f"Are you sure you want to delete this {model_name}?",
                },
            )
        except Exception as e:
            logger.error(f"Error extracting delete mutation metadata: {e}")
            return None

    def _extract_bulk_mutations_metadata(
        self, model: type[models.Model], mutation_generator
    ) -> list[MutationMetadata]:
        """Extract metadata for bulk mutations."""
        mutations = []
        model_name = model.__name__

        try:
            # Bulk create
            input_fields = self._extract_input_fields_from_model(model, "create")
            bulk_create = MutationMetadata(
                name=f"bulk_create_{model_name.lower()}",
                description=f"Create multiple {model_name} instances",
                input_fields=[
                    InputFieldMetadata(
                        name="objects",
                        field_type="List",
                        required=True,
                        description=f"List of {model_name} objects to create",
                        multiple=True,
                    )
                ],
                return_type=f"List[{model_name}Type]",
                requires_authentication=True,
                required_permissions=[f"add_{model._meta.model_name}"],
                mutation_type="bulk_create",
                model_name=model_name,
                success_message=f"Multiple {model_name} instances created successfully",
            )
            mutations.append(bulk_create)

            # Bulk update
            bulk_update = MutationMetadata(
                name=f"bulk_update_{model_name.lower()}",
                description=f"Update multiple {model_name} instances",
                input_fields=[
                    InputFieldMetadata(
                        name="objects",
                        field_type="List",
                        required=True,
                        description=f"List of {model_name} objects to update",
                        multiple=True,
                    )
                ],
                return_type=f"List[{model_name}Type]",
                requires_authentication=True,
                required_permissions=[f"change_{model._meta.model_name}"],
                mutation_type="bulk_update",
                model_name=model_name,
                success_message=f"Multiple {model_name} instances updated successfully",
            )
            mutations.append(bulk_update)

            # Bulk delete
            bulk_delete = MutationMetadata(
                name=f"bulk_delete_{model_name.lower()}",
                description=f"Delete multiple {model_name} instances",
                input_fields=[
                    InputFieldMetadata(
                        name="ids",
                        field_type="List[ID]",
                        required=True,
                        description=f"List of {model_name} IDs to delete",
                        multiple=True,
                    )
                ],
                return_type="Boolean",
                requires_authentication=True,
                required_permissions=[f"delete_{model._meta.model_name}"],
                mutation_type="bulk_delete",
                model_name=model_name,
                success_message=f"Multiple {model_name} instances deleted successfully",
            )
            mutations.append(bulk_delete)

        except Exception as e:
            logger.error(f"Error extracting bulk mutations metadata: {e}")

        return mutations

    def _extract_method_mutations_metadata(
        self, model: type[models.Model], mutation_generator, user=None
    ) -> list[MutationMetadata]:
        """Extract metadata for method-based mutations."""
        mutations = []

        try:
            from ..generators.introspector import ModelIntrospector

            introspector = ModelIntrospector.for_model(model)
            model_methods = introspector.get_model_methods()

            for method_name, method_info in model_methods.items():
                if method_info.is_mutation and not method_info.is_private:
                    method_mutation = self._extract_method_mutation_metadata(
                        model, method_name, method_info, user=user
                    )
                    if method_mutation:
                        mutations.append(method_mutation)

        except Exception as e:
            logger.error(f"Error extracting method mutations metadata: {e}")

        return mutations

    def _extract_method_mutation_metadata(
        self, model: type[models.Model], method_name: str, method_info, user=None
    ) -> Optional[MutationMetadata]:
        """Extract metadata for a specific method mutation."""
        try:
            model_name = model.__name__
            method = getattr(model, method_name)

            # Extract input fields from method signature
            input_fields = self._extract_input_fields_from_method(method)
            input_type_name = None

            # Get custom attributes from decorators
            description = getattr(method, "_mutation_description", method.__doc__)
            custom_name = getattr(method, "_custom_mutation_name", None)
            requires_permissions = getattr(method, "_requires_permissions", None)
            if requires_permissions is None:
                legacy = getattr(method, "_requires_permission", None)
                requires_permissions = [legacy] if legacy else []
            action_meta = getattr(method, "_action_ui", None)
            action_kind = getattr(method, "_action_kind", None)

            mutation_name = custom_name or f"{model_name.lower()}_{method_name}"
            if input_fields:
                input_type_name = (
                    getattr(method, "_mutation_input_type", None).__name__
                    if getattr(method, "_mutation_input_type", None)
                    else f"{model_name}{method_name.title()}Input"
                )
            action_payload = None
            if action_meta:
                action_payload = self._sanitize_action_payload(
                    {
                        **action_meta,
                        "kind": action_kind or action_meta.get("mode"),
                        "label": action_meta.get("title")
                        or method_name.replace("_", " ").title(),
                    }
                )
                if action_kind == "confirm":
                    input_fields = []
                    input_type_name = None
                # Graphene JSONString will serialize the dict; avoid pre-dumping to keep a single level

            if user and requires_permissions:
                missing = [
                    perm for perm in requires_permissions if not user.has_perm(perm)
                ]
                if missing:
                    return None

            return MutationMetadata(
                name=mutation_name,
                method_name=method_name,
                description=description or f"Execute {method_name} on {model_name}",
                input_fields=input_fields,
                return_type="JSONString",
                input_type=input_type_name,
                requires_authentication=True,
                required_permissions=requires_permissions or [],
                mutation_type="custom",
                model_name=model_name,
                success_message=f"{method_name} executed successfully",
                action=action_payload,
            )

        except Exception as e:
            logger.error(f"Error extracting method mutation metadata: {e}")
            return None

    def _extract_input_fields_from_model(
        self, model: type[models.Model], mutation_type: str
    ) -> list[InputFieldMetadata]:
        """Extract input fields from Django model fields."""
        input_fields = []

        for field in model._meta.fields:
            # Skip auto fields and primary keys for create mutations
            if getattr(field, "primary_key", None) and mutation_type == "create":
                continue

            # Skip auto-generated fields
            if hasattr(field, "auto_now") or hasattr(field, "auto_now_add"):
                continue

            input_field = self._convert_django_field_to_input_metadata(
                field, mutation_type
            )
            if input_field:
                input_fields.append(input_field)

        return input_fields

    def _convert_django_field_to_input_metadata(
        self, field, mutation_type: str
    ) -> Optional[InputFieldMetadata]:
        """Convert Django field to InputFieldMetadata."""
        try:
            from django.db import models

            field_name = field.name
            field_type = "String"  # Default
            required = (
                not field.null and not field.blank and not hasattr(field, "default")
            )

            # For update mutations, make fields optional
            if mutation_type == "update":
                required = False

            # Map Django field types to GraphQL types
            if isinstance(field, models.CharField):
                field_type = "String"
            elif isinstance(field, models.TextField):
                field_type = "String"
            elif isinstance(field, models.IntegerField):
                field_type = "Int"
            elif isinstance(field, models.FloatField):
                field_type = "Float"
            elif isinstance(field, models.BooleanField):
                field_type = "Boolean"
            elif isinstance(field, models.DateTimeField):
                field_type = "DateTime"
            elif isinstance(field, models.DateField):
                field_type = "Date"
            elif isinstance(field, models.EmailField):
                field_type = "String"
            elif isinstance(field, models.URLField):
                field_type = "String"
            elif isinstance(field, models.ForeignKey):
                field_type = "ID"
            elif isinstance(field, models.ManyToManyField):
                field_type = "List[ID]"

            # Get choices if available
            choices = None
            if hasattr(field, "choices") and field.choices:
                choices = [
                    {
                        "value": self._json_safe_value(choice[0]),
                        "label": force_str(choice[1]),
                    }
                    for choice in field.choices
                ]

            # Determine widget type
            widget_type = self._get_widget_type_for_field(field)

            return InputFieldMetadata(
                name=field_name,
                field_type=field_type,
                required=required,
                description=str(field.verbose_name)
                if hasattr(field, "verbose_name")
                else None,
                choices=choices,
                widget_type=widget_type,
                help_text=str(field.help_text)
                if hasattr(field, "help_text") and field.help_text
                else None,
                max_length=getattr(field, "max_length", None),
                related_model=field.related_model.__name__
                if hasattr(field, "related_model") and field.related_model
                else None,
                multiple=isinstance(field, models.ManyToManyField),
            )
        except Exception as e:
            logger.error(f"Error converting field {field.name}: {e}")
            return None

    def _get_widget_type_for_field(self, field) -> str:
        """Determine the appropriate widget type for a Django field."""
        from django.db import models

        if isinstance(field, models.TextField):
            return "textarea"
        elif isinstance(field, models.EmailField):
            return "email"
        elif isinstance(field, models.URLField):
            return "url"
        elif isinstance(field, models.BooleanField):
            return "checkbox"
        elif isinstance(field, models.DateTimeField):
            return "datetime-local"
        elif isinstance(field, models.DateField):
            return "date"
        elif isinstance(field, models.IntegerField):
            return "number"
        elif isinstance(field, models.FloatField):
            return "number"
        elif isinstance(field, models.ForeignKey):
            return "select"
        elif isinstance(field, models.ManyToManyField):
            return "multiselect"
        elif hasattr(field, "choices") and field.choices:
            return "select"
        else:
            return "text"

    def _extract_input_fields_from_method(self, method) -> list[InputFieldMetadata]:
        """Extract input fields from method signature (with decorator overrides)."""
        import inspect
        from datetime import date, datetime, time

        input_fields: list[InputFieldMetadata] = []
        signature = inspect.signature(method)
        action_ui = getattr(method, "_action_ui", {}) or {}
        field_overrides: dict[str, dict[str, Any]] = action_ui.get("fields", {}) or {}

        for param_name, param in signature.parameters.items():
            if param_name == "self":
                continue

            field_type = "String"  # Default
            required = param.default == inspect.Parameter.empty
            default_value = (
                param.default if param.default != inspect.Parameter.empty else None
            )

            # Try to infer type from annotation (with Optional/Union support)
            if param.annotation != inspect.Parameter.empty:
                annotation = param.annotation
                origin = get_origin(annotation)
                args = get_args(annotation)
                base_annotation = annotation
                if origin is Union:
                    non_none = [arg for arg in args if arg is not type(None)]
                    if non_none:
                        base_annotation = non_none[0]
                        required = False
                if base_annotation == int:
                    field_type = "Int"
                elif base_annotation == float:
                    field_type = "Float"
                elif base_annotation == bool:
                    field_type = "Boolean"
                elif base_annotation in (date, datetime):
                    field_type = "Date" if base_annotation is date else "DateTime"
                elif base_annotation is time:
                    field_type = "Time"
                elif origin in (list, tuple, set):
                    inner = args[0] if args else Any
                    inner_type = "String"
                    if inner == int:
                        inner_type = "Int"
                    elif inner == float:
                        inner_type = "Float"
                    elif inner == bool:
                        inner_type = "Boolean"
                    field_type = f"List[{inner_type}]"

            input_field = InputFieldMetadata(
                name=param_name,
                field_type=field_type,
                required=required,
                default_value=default_value,
                description=f"Parameter {param_name} for method execution",
            )

            override = field_overrides.get(param_name) or {}
            if override:
                if "label" in override:
                    input_field.description = force_str(override.get("label"))
                if "required" in override:
                    input_field.required = bool(override.get("required"))
                if "choices" in override and override.get("choices"):
                    try:
                        input_field.choices = [
                            {
                                "value": self._json_safe_value(choice.get("value")),
                                "label": force_str(choice.get("label")),
                            }
                            for choice in override.get("choices", [])
                            if isinstance(choice, dict)
                        ]
                    except Exception:
                        input_field.choices = None
                if "widget_type" in override:
                    input_field.widget_type = override.get("widget_type")
                if "placeholder" in override:
                    input_field.placeholder = override.get("placeholder")
                if "help_text" in override:
                    input_field.help_text = override.get("help_text")
                if "related_model" in override or "model" in override:
                    input_field.related_model = override.get(
                        "related_model", override.get("model")
                    )
                if "default_value" in override:
                    input_field.default_value = self._json_safe_value(
                        override.get("default_value")
                    )
                if "queryset" in override and override.get("queryset") is not None:
                    try:
                        qs = override.get("queryset")
                        related_label = override.get("related_model") or override.get(
                            "model"
                        )
                        model_cls = None
                        if related_label:
                            try:
                                model_cls = apps.get_model(related_label)
                            except Exception:
                                model_cls = None
                        if callable(qs):
                            try:
                                if model_cls:
                                    qs = qs(model_cls)
                                else:
                                    qs = qs()
                            except TypeError:
                                qs = qs()
                        from django.db.models.query import QuerySet  # type: ignore

                        if isinstance(qs, QuerySet):
                            sample = list(qs[:50])
                            input_field.choices = [
                                {
                                    "value": self._json_safe_value(
                                        getattr(obj, "pk", None)
                                    ),
                                    "label": force_str(obj),
                                }
                                for obj in sample
                            ]
                    except Exception:
                        # silently ignore queryset override failures
                        pass

            input_fields.append(input_field)

        return input_fields


class ModelFormMetadataExtractor:
    """
    Extractor for Django model form metadata, providing all necessary information
    to construct forms on the frontend.
    """

    def __init__(self, schema_name: str = "default", max_depth: int = 1):
        """
        Initialize the form metadata extractor.

        Args:
            schema_name: Name of the schema configuration to use
            max_depth: Maximum depth for nested related model metadata
        """
        self.schema_name = schema_name
        self.max_depth = max_depth

    def _json_safe_value(self, value: Any) -> Any:
        """Convert values into JSON-friendly primitives."""
        from datetime import date, datetime, time
        from decimal import Decimal

        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, time)):
            try:
                return value.isoformat()
            except Exception:
                return force_str(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {
                force_str(key): self._json_safe_value(val) for key, val in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe_value(val) for val in value]
        return force_str(value)

    @cache_metadata(
        timeout=1200, user_specific=True
    )  # 20 minutes cache for form field metadata
    def _extract_form_field_metadata(self, field, user) -> Optional[FormFieldMetadata]:
        """
        Extract form-specific metadata for a single field with permission checking.

        Args:
            field: Django model field instance
            user: User instance for permission checking

        Returns:
            FormFieldMetadata if user has permission, None otherwise
        """
        from django.db import models

        # Get field choices
        choices = None
        if hasattr(field, "choices") and field.choices:
            choices = [
                {
                    "value": self._json_safe_value(choice[0]),
                    "label": force_str(choice[1]),
                }
                for choice in field.choices
            ]

        # Determine widget type based on field type
        widget_type = self._get_form_widget_type(field)

        # Generate placeholder text
        placeholder = self._generate_placeholder(field)

        # Get validation attributes
        max_length = getattr(field, "max_length", None)
        min_length = (
            getattr(field, "min_length", None) if hasattr(field, "min_length") else None
        )
        max_value = (
            getattr(field, "max_value", None) if hasattr(field, "max_value") else None
        )
        min_value = (
            getattr(field, "min_value", None) if hasattr(field, "min_value") else None
        )

        # Handle decimal fields
        decimal_places = getattr(field, "decimal_places", None)
        max_digits = getattr(field, "max_digits", None)

        # Determine if field is required for forms (different from database nullable)
        is_required = not field.blank and field.default == models.NOT_PROVIDED

        # Get default value for forms
        default_value = None
        if field.default != models.NOT_PROVIDED:
            if callable(field.default):
                try:
                    default_value = field.default()
                except Exception:
                    default_value = None
            else:
                default_value = field.default
        # Ensure JSONString fields receive JSON-serializable values
        default_value = self._to_json_safe(default_value)

        model = field.model
        permission_snapshot = _build_field_permission_snapshot(user, model, field.name)
        if permission_snapshot and not permission_snapshot.can_read:
            return None
        has_permission = permission_snapshot.can_read if permission_snapshot else True

        is_fsm_field = _is_fsm_field_instance(field)
        editable_flag = bool(field.editable) and not is_fsm_field
        disabled_flag = not editable_flag
        readonly_flag = (not editable_flag) or bool(
            getattr(field, "primary_key", False)
        )
        if permission_snapshot and not permission_snapshot.can_write:
            disabled_flag = True
            readonly_flag = True

        validators = self._extract_field_validators(field)
        error_messages = self._extract_error_messages(field)

        return FormFieldMetadata(
            name=field.name,
            field_type=field.__class__.__name__,
            is_required=is_required,
            verbose_name=str(field.verbose_name),
            help_text=field.help_text or "",
            widget_type=widget_type,
            placeholder=placeholder,
            default_value=default_value,
            choices=choices,
            max_length=max_length,
            min_length=min_length,
            decimal_places=decimal_places,
            max_digits=max_digits,
            min_value=min_value,
            max_value=max_value,
            auto_now=getattr(field, "auto_now", False),
            auto_now_add=getattr(field, "auto_now_add", False),
            blank=field.blank,
            null=field.null,
            unique=field.unique,
            editable=editable_flag,
            validators=validators,
            error_messages=error_messages,
            has_permission=has_permission,
            disabled=disabled_flag,
            readonly=readonly_flag,
            css_classes=self._get_css_classes(field),
            data_attributes=self._to_json_safe(self._get_data_attributes(field)),
            permissions=permission_snapshot,
        )

    @cache_metadata(
        timeout=1200, user_specific=True
    )  # 20 minutes cache for form relationship metadata
    def _extract_form_relationship_metadata(
        self, field, user, current_depth: int = 0, visited_models: set = None
    ) -> Optional[FormRelationshipMetadata]:
        """
        Extract form-specific metadata for relationship fields.

        Args:
            field: Django relationship field instance
            user: User instance for permission checking
            current_depth: Current nesting depth

        Returns:
            FormRelationshipMetadata if user has permission, None otherwise
        """
        from django.db import models

        related_model = field.related_model

        if related_model is None or not hasattr(related_model, "_meta"):
            return None

        related_app_label = getattr(related_model._meta, "app_label", "")
        related_model_class_name = related_model.__name__

        # Check recursion depth to prevent infinite loops in circular relationships
        if current_depth >= self.max_depth:
            # Return basic relationship metadata without nested form data
            pass
        else:
            # Build embedded related model form metadata only if within depth limit
            embedded_related = self.extract_model_form_metadata(
                app_name=related_app_label,
                model_name=related_model_class_name,
                user=user,
                nested_fields=[],  # No nested fields for relationships by default
                current_depth=current_depth + 1,
                visited_models=visited_models,
            )

            if embedded_related is None:
                return None

        # Determine widget type for relationship
        widget_type = self._get_relationship_widget_type(field)

        model = field.model
        permission_snapshot = _build_field_permission_snapshot(user, model, field.name)
        if permission_snapshot and not permission_snapshot.can_read:
            return None
        has_permission = permission_snapshot.can_read if permission_snapshot else True

        # Handle verbose_name for reverse relationships
        if hasattr(field, "verbose_name"):
            verbose_name = str(field.verbose_name)
        else:
            # For reverse relationships like ManyToOneRel, generate a readable name
            verbose_name = field.name.replace("_", " ").title()

        many_to_many = isinstance(field, models.ManyToManyField)
        one_to_one = isinstance(field, models.OneToOneField)
        foreign_key = isinstance(field, models.ForeignKey)

        # Detect reverse relationships using Django's reverse_related classes
        try:
            from django.db.models.fields.reverse_related import (
                ManyToOneRel,
                ManyToManyRel,
                OneToOneRel,
            )

            is_reverse = isinstance(field, (ManyToOneRel, ManyToManyRel, OneToOneRel))
            if isinstance(field, ManyToManyRel):
                many_to_many = True
            elif isinstance(field, OneToOneRel):
                one_to_one = True
            elif isinstance(field, ManyToOneRel):
                foreign_key = True
        except Exception:
            # Fallback: use multiple signals to detect reverse relations conservatively
            is_reverse = False
            # Heuristic 1: auto_created and not a standard forward field class
            try:
                from django.db import models as dj_models

                if bool(getattr(field, "auto_created", False)) and not isinstance(
                    field,
                    (
                        dj_models.ForeignKey,
                        dj_models.OneToOneField,
                        dj_models.ManyToManyField,
                    ),
                ):
                    is_reverse = True
            except Exception:
                # If models import fails for any reason, keep current is_reverse value
                pass
            # Heuristic 2: GenericRelation should be treated as reverse-facing relation in forms
            try:
                from django.contrib.contenttypes.fields import GenericRelation

                if isinstance(field, GenericRelation):
                    is_reverse = True
            except Exception:
                # GenericRelation may not be installed; ignore
                pass

        return FormRelationshipMetadata(
            name=field.name,
            relationship_type=field.__class__.__name__,
            cardinality=_relationship_cardinality(
                is_reverse, many_to_many, one_to_one, foreign_key
            ),
            verbose_name=verbose_name,
            help_text=getattr(field, "help_text", "") or "",
            widget_type=widget_type,
            is_required=not getattr(field, "blank", True),
            related_model=related_model_class_name,
            related_app=related_app_label,
            to_field=field.remote_field.name
            if hasattr(field, "remote_field") and field.remote_field
            else None,
            from_field=field.name,
            many_to_many=many_to_many,
            one_to_one=one_to_one,
            foreign_key=foreign_key,
            is_reverse=is_reverse,
            multiple=many_to_many,
            queryset_filters=self._to_json_safe(self._get_queryset_filters(field)),
            empty_label=self._get_empty_label(field),
            limit_choices_to=self._to_json_safe(
                getattr(field, "limit_choices_to", None)
            ),
            has_permission=has_permission,
            disabled=(not field.editable)
            or (permission_snapshot and not permission_snapshot.can_write),
            readonly=(
                not field.editable
                or getattr(field, "primary_key", None)
                or (permission_snapshot and not permission_snapshot.can_write)
            ),
            css_classes=self._get_css_classes(field),
            data_attributes=self._to_json_safe(self._get_data_attributes(field)),
            permissions=permission_snapshot,
        )

    @cache_metadata(
        timeout=1800, user_specific=True
    )  # 30 minutes cache for complete model form metadata
    def extract_model_form_metadata(
        self,
        app_name: str,
        model_name: str,
        user,
        nested_fields: list[str] = None,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        exclude_relationships: Optional[list[str]] = None,
        only_relationships: Optional[list[str]] = None,
        current_depth: int = 0,
        visited_models: set = None,
    ) -> Optional[ModelFormMetadata]:
        """

        Purpose: Extract comprehensive form metadata for a Django model, with optional field selection filters.
        Args:
            app_name (str): Django app name.
            model_name (str): Model class name.
            user: User instance for permission checking.
            nested_fields (List[str], optional): Field names to include nested metadata for.
            exclude (List[str], optional): Regular form field names to exclude from the result.
            only (List[str], optional): Regular form field names to exclusively include in the result.
            exclude_relationships (List[str], optional): Relationship field names to exclude from the result.
            only_relationships (List[str], optional): Relationship field names to exclusively include in the result.
            current_depth (int): Current nesting depth for recursive extraction.
            visited_models (set): Set of already visited models to prevent circular references.
        Returns:
            Optional[ModelFormMetadata]: Metadata with form-specific information, possibly filtered by selection.
        Raises:
            None
        Example:
            >>> extractor.extract_model_form_metadata(
            ...     app_name="auth", model_name="User", user=request.user,
            ...     only=["username", "email"], exclude_relationships=["groups"]
            ... )
        """
        # Initialize visited models set if not provided
        if visited_models is None:
            visited_models = set()

        # Create a unique identifier for this model
        model_key = f"{app_name}.{model_name}"

        # Check if we've already visited this model to prevent infinite recursion
        if model_key in visited_models:
            logger.warning(
                f"Circular reference detected for model {model_key}, skipping to prevent infinite recursion"
            )
            return None

        # Add current model to visited set
        visited_models.add(model_key)

        try:
            model = apps.get_model(app_name, model_name)
        except (LookupError, ValueError) as e:
            logger.error(f"Model {app_name}.{model_name} not found: {e}")
            visited_models.discard(model_key)  # Remove from visited set on error
            return None

        if not model or not hasattr(model, "_meta"):
            visited_models.discard(model_key)  # Remove from visited set on error
            return None

        meta = model._meta
        nested_fields = nested_fields or []

        # Normalize selection inputs
        exclude = exclude or []
        only = only or []
        exclude_relationships = exclude_relationships or []
        only_relationships = only_relationships or []

        # Detect polymorphic/multi-table inheritance to hide parent/child pointers
        # and reverse OneToOne relations from form metadata.
        try:
            from ..generators.inheritance import inheritance_handler

            inheritance_info = inheritance_handler.analyze_model_inheritance(model)
        except Exception:
            inheritance_info = {}

        is_polymorphic_model = False
        try:
            for _f in meta.get_fields():
                if getattr(_f, "name", None) == "polymorphic_ctype":
                    is_polymorphic_model = True
                    break
        except Exception:
            pass

        if getattr(meta, "parents", None):
            try:
                if len(meta.parents) > 0:
                    is_polymorphic_model = True
            except Exception:
                # Some Django versions expose parents as a dict-like
                is_polymorphic_model = True

        if inheritance_info and (
            inheritance_info.get("child_models")
            or inheritance_info.get("concrete_parents")
        ):
            is_polymorphic_model = True

        # Always exclude these known fields from form metadata
        excluded_names = {
            "report_rows",
            "stock_policies",
            "stock_snapshots",
        }

        # Extract form fields
        form_fields = []
        form_relationships = []
        # Track declared order across fields and relationships
        # Keep forward relationships in the main order and push reverse relationships to the end
        declared_forward_order: list[str] = []
        declared_reverse_order: list[str] = []

        for field in meta.get_fields():
            # Global name-based exclusions
            if field.name in excluded_names:
                continue

            # Hide internal polymorphic marker
            if field.name == "polymorphic_ctype":
                continue

            # Hide parent-link pointer fields (multi-table inheritance)
            if field.name.endswith("_ptr"):
                continue

            # Check if this is a relationship field
            if hasattr(field, "related_model") and field.related_model:
                # Skip polymorphic OneToOne reverse accessors (auto-created)
                if is_polymorphic_model and getattr(field, "one_to_one", False):
                    # Avoid exposing child/parent relations in forms
                    if getattr(field, "auto_created", False):
                        continue

                # Always include relationship fields regardless of nested_fields
                relationship_metadata = self._extract_form_relationship_metadata(
                    field, user, current_depth, visited_models
                )
                if relationship_metadata:
                    form_relationships.append(relationship_metadata)
                    if getattr(relationship_metadata, "is_reverse", False):
                        declared_reverse_order.append(field.name)
                    else:
                        declared_forward_order.append(field.name)
            else:
                # This is a regular field
                if not field.name.startswith("_") and field.concrete:
                    # Skip OneToOne parent-link fields for polymorphic models
                    if is_polymorphic_model and isinstance(field, models.OneToOneField):
                        # parent_link is True for the implicit pointer from child to parent
                        if getattr(field, "parent_link", False):
                            continue
                    # Also skip if it looks like an inheritance pointer by naming
                    if field.name.endswith("_ptr"):
                        continue
                    field_metadata = self._extract_form_field_metadata(field, user)
                    if field_metadata:
                        form_fields.append(field_metadata)
                        declared_forward_order.append(field.name)

        # Apply selection filters to fields and relationships
        if only:
            form_fields = [f for f in form_fields if f.name in set(only)]
        if exclude:
            form_fields = [f for f in form_fields if f.name not in set(exclude)]

        if only_relationships:
            form_relationships = [
                r for r in form_relationships if r.name in set(only_relationships)
            ]
        if exclude_relationships:
            form_relationships = [
                r
                for r in form_relationships
                if r.name not in set(exclude_relationships)
            ]

        # Final safeguard: remove any excluded_names that slipped through
        if excluded_names:
            form_fields = [f for f in form_fields if f.name not in excluded_names]
            form_relationships = [
                r for r in form_relationships if r.name not in excluded_names
            ]

        # Get form configuration
        form_title = f"Form for {meta.verbose_name}"
        form_description = f"Create or edit {meta.verbose_name.lower()}"

        # Build field_order using declaration order: forward first, then reverse relationships at the end
        final_field_names = {f.name for f in form_fields}
        final_relationship_names = {r.name for r in form_relationships}
        field_order_forward = [
            name
            for name in declared_forward_order
            if (name in final_field_names or name in final_relationship_names)
        ]
        field_order_reverse = [
            name
            for name in declared_reverse_order
            if (name in final_field_names or name in final_relationship_names)
        ]
        field_order = field_order_forward + field_order_reverse

        # Final stable partition: ensure reverse relationship names appear at the end
        # even if any slipped into the forward list due to detection issues elsewhere.
        reverse_names = {
            r.name for r in form_relationships if getattr(r, "is_reverse", False)
        }
        if reverse_names:
            non_reverse_order = [
                name for name in field_order if name not in reverse_names
            ]
            reverse_order = [name for name in field_order if name in reverse_names]
            field_order = non_reverse_order + reverse_order

        # Get excluded fields (typically auto fields, computed fields)
        exclude_fields = []
        readonly_fields = []

        for field in meta.get_fields():
            if (
                field.auto_created
                or (hasattr(field, "auto_now") and field.auto_now)
                or (hasattr(field, "auto_now_add") and field.auto_now_add)
            ):
                exclude_fields.append(field.name)

            if getattr(field, "primary_key", None) or not field.editable:
                readonly_fields.append(field.name)

        # Required permissions (simplified)
        required_permissions = [
            f"{app_name}.add_{model_name.lower()}",
            f"{app_name}.change_{model_name.lower()}",
        ]

        # Extract nested metadata for specified fields
        nested_metadata = []
        if nested_fields:
            for field_name in nested_fields:
                try:
                    field = meta.get_field(field_name)
                    if hasattr(field, "related_model") and field.related_model:
                        related_model = field.related_model
                        related_meta = related_model._meta

                        # Extract nested form metadata for the related model
                        nested_form_metadata = self.extract_model_form_metadata(
                            app_name=related_meta.app_label,
                            model_name=related_model.__name__,
                            user=user,
                            nested_fields=[],  # Don't go deeper to avoid infinite recursion
                            current_depth=current_depth + 1,
                            visited_models=visited_models.copy(),  # Pass a copy to avoid affecting parent
                        )

                        if nested_form_metadata:
                            # Attach linkage information from the parent relationship field
                            nested_form_metadata.name = field.name
                            nested_form_metadata.field_name = field.name
                            nested_form_metadata.relationship_type = (
                                field.__class__.__name__
                            )
                            nested_form_metadata.to_field = (
                                field.remote_field.name
                                if hasattr(field, "remote_field") and field.remote_field
                                else None
                            )
                            nested_form_metadata.from_field = field.name
                            nested_form_metadata.is_required = not getattr(
                                field, "blank", True
                            )

                            # Exclude parent-linking relationships from nested metadata
                            # Example: when nesting Produit.famille, inside Famille's nested metadata,
                            # exclude relationships that point back to Produit via to_field == "famille".
                            try:
                                parent_app = meta.app_label
                                parent_model = model.__name__
                                parent_field_name = field.name
                                nested_form_metadata.relationships = [
                                    r
                                    for r in (nested_form_metadata.relationships or [])
                                    if not (
                                        (
                                            getattr(r, "related_model", None)
                                            == parent_model
                                        )
                                        and (
                                            getattr(r, "related_app", None)
                                            == parent_app
                                        )
                                        and (
                                            getattr(r, "to_field", None)
                                            == parent_field_name
                                            or getattr(r, "from_field", None)
                                            == parent_field_name
                                        )
                                    )
                                ]
                            except Exception:
                                # If any attribute is missing, skip filtering gracefully
                                pass

                            nested_metadata.append(nested_form_metadata)
                except Exception as e:
                    logger.warning(
                        f"Could not extract nested metadata for field {field_name}: {e}"
                    )

        # If a relationship is represented in nested, exclude it from top-level relationships
        if nested_metadata:
            nested_names = {n.name for n in nested_metadata if getattr(n, "name", None)}
            if nested_names:
                form_relationships = [
                    r for r in form_relationships if r.name not in nested_names
                ]

        # Remove current model from visited set before returning (cleanup)
        visited_models.discard(model_key)

        return ModelFormMetadata(
            metadata_version=_get_metadata_version_value(app_name, model_name),
            app_name=app_name,
            model_name=model_name,
            verbose_name=str(meta.verbose_name),
            verbose_name_plural=str(meta.verbose_name_plural),
            form_title=form_title,
            form_description=form_description,
            fields=form_fields,
            relationships=form_relationships,
            nested=nested_metadata,
            field_order=field_order,
            exclude_fields=exclude_fields,
            readonly_fields=readonly_fields,
            required_permissions=required_permissions,
            form_validation_rules=self._get_form_validation_rules(model),
            form_layout=self._get_form_layout(model),
            css_classes=self._get_form_css_classes(model),
            form_attributes=self._get_form_attributes(model),
            permissions=_build_model_permission_matrix(model, user),
        )

    def _get_form_widget_type(self, field) -> str:
        """Get the recommended widget type for a form field."""
        from django.db import models

        widget_mapping = {
            models.CharField: "text",
            models.TextField: "textarea",
            models.EmailField: "email",
            models.URLField: "url",
            models.IntegerField: "number",
            models.FloatField: "number",
            models.DecimalField: "number",
            models.BooleanField: "checkbox",
            models.DateField: "date",
            models.DateTimeField: "datetime-local",
            models.TimeField: "time",
            models.FileField: "file",
            models.ImageField: "file",
            models.ForeignKey: "select",
            models.ManyToManyField: "select",
            models.OneToOneField: "select",
        }

        # Check for choices first
        if hasattr(field, "choices") and field.choices:
            return "select"

        return widget_mapping.get(field.__class__, "text")

    def _get_relationship_widget_type(self, field) -> str:
        """Get the recommended widget type for relationship fields."""
        from django.db import models

        if isinstance(field, models.ManyToManyField):
            return "multiselect"
        elif isinstance(field, (models.ForeignKey, models.OneToOneField)):
            return "select"

        return "select"

    def _generate_placeholder(self, field) -> Optional[str]:
        """Generate placeholder text for form fields."""
        if hasattr(field, "help_text") and field.help_text:
            return field.help_text

        return f"Enter {field.verbose_name.lower()}"

    def _get_queryset_filters(self, field) -> Optional[dict[str, Any]]:
        """Get queryset filters for relationship fields."""
        if hasattr(field, "limit_choices_to") and field.limit_choices_to:
            return field.limit_choices_to
        return None

    def _get_empty_label(self, field) -> Optional[str]:
        """Get empty label for choice fields."""
        if hasattr(field, "choices") and field.choices:
            return f"Select {field.verbose_name.lower()}"
        return None

    def _get_css_classes(self, field) -> Optional[str]:
        """Get CSS classes for form fields."""
        from django.db import models

        classes = ["form-control"]

        if isinstance(field, models.TextField):
            classes.append("form-textarea")
        elif isinstance(
            field, (models.DateField, models.DateTimeField, models.TimeField)
        ):
            classes.append("form-date")
        elif isinstance(
            field, (models.IntegerField, models.FloatField, models.DecimalField)
        ):
            classes.append("form-number")
        elif isinstance(field, models.BooleanField):
            classes.append("form-checkbox")
        elif isinstance(field, (models.FileField, models.ImageField)):
            classes.append("form-file")

        if getattr(field, "primary_key", None):
            classes.append("form-readonly")

        return " ".join(classes)

    def _get_data_attributes(self, field) -> Optional[dict[str, Any]]:
        """Get data attributes for form fields."""
        attributes = {}

        if hasattr(field, "max_length") and field.max_length:
            attributes["maxlength"] = field.max_length

        if hasattr(field, "min_length") and field.min_length:
            attributes["minlength"] = field.min_length

        return attributes if attributes else None

    def _extract_field_validators(self, field) -> Optional[list[str]]:
        """Return validator identifiers suitable for frontend metadata."""
        validators = getattr(field, "validators", None) or []
        validator_names = []
        for validator in validators:
            name = getattr(validator, "__name__", None) or validator.__class__.__name__
            if name:
                validator_names.append(name)
        return validator_names or None

    def _extract_error_messages(self, field) -> Optional[dict[str, str]]:
        """Return field error message templates as plain strings."""
        error_messages = getattr(field, "error_messages", None) or {}
        if not error_messages:
            return None
        cleaned = {}
        for key, message in error_messages.items():
            if message in (None, ""):
                continue
            cleaned[force_str(key)] = force_str(message)
        return cleaned or None

    def _get_form_validation_rules(self, model) -> Optional[dict[str, Any]]:
        """Get form validation rules for the model."""
        return {
            "validate_on_blur": True,
            "validate_on_change": True,
            "show_errors_inline": True,
        }

    def _get_form_layout(self, model) -> Optional[dict[str, Any]]:
        """Get form layout configuration."""
        return {
            "layout_type": "vertical",
            "field_spacing": "medium",
            "group_related_fields": True,
        }

    def _get_form_css_classes(self, model) -> Optional[str]:
        """Get CSS classes for the form."""
        return f"model-form {model._meta.app_label}-{model._meta.model_name}-form"

    def _get_form_attributes(self, model) -> Optional[dict[str, Any]]:
        """Get form HTML attributes."""
        return {
            "novalidate": False,
            "autocomplete": "on",
            "data-model": f"{model._meta.app_label}.{model._meta.model_name}",
        }

    def _to_json_safe(self, value: Any) -> Any:
        """
        Purpose: Convert Python/Django values into JSON-serializable primitives for Graphene JSONString.
        Args:
            value: Any Python value possibly containing datetime, date, time, Decimal, set/tuple, etc.
        Returns:
            A JSON-serializable value (str, int, float, bool, None, list, dict) with nested items converted.
        Raises:
            None
        Example:
            >>> from datetime import datetime
            >>> v = datetime(2024, 1, 1)
            >>> isinstance(ModelFormMetadataExtractor()._to_json_safe(v), str)
            True
        """
        try:
            from datetime import date, datetime, time
            from decimal import Decimal

            # Primitives remain unchanged
            if value is None or isinstance(value, (str, int, float, bool)):
                return value

            # Datetime-like objects -> ISO 8601 strings
            if isinstance(value, (datetime, date, time)):
                try:
                    # Use isoformat for a stable, interoperable string representation
                    return value.isoformat()
                except Exception:
                    return str(value)

            # Decimal -> string to preserve precision
            if isinstance(value, Decimal):
                return str(value)

            # Sets/Tuples -> lists
            if isinstance(value, (set, tuple)):
                return [self._to_json_safe(v) for v in list(value)]

            # Lists -> convert elements
            if isinstance(value, list):
                return [self._to_json_safe(v) for v in value]

            # Dicts -> convert keys/values
            if isinstance(value, dict):
                return {str(k): self._to_json_safe(v) for k, v in value.items()}

            # Fallback: use string representation
            return str(value)
        except Exception:
            # As a last resort, stringify to avoid GraphQL serialization errors
            return str(value)

    def _has_field_permission(self, user, model: type, field_name: str) -> bool:
        """
        Check if user has permission to access a specific field in forms.

        Args:
            user: The user to check permissions for
            model: The Django model class
            field_name: The name of the field to check

        Returns:
            bool: True if user has permission, False otherwise
        """
        # Anonymous users have no field permissions
        if not user or not user.is_authenticated:
            return False

        # Superusers have access to all fields
        if user.is_superuser:
            return True

        # Check if user has view permission for the model
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        view_permission = f"{app_label}.view_{model_name}"

        try:
            return user.has_perm(view_permission)
        except Exception:
            return False


class ModelTableExtractor:
    """Extractor for comprehensive table metadata including fields and filters."""

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name
        self.metadata_extractor = ModelMetadataExtractor(schema_name=schema_name)

    def _get_model(self, app_name: str, model_name: str):
        try:
            return apps.get_model(app_name, model_name)
        except Exception as e:
            logger.error(
                "Model '%s' not found in app '%s': %s", model_name, app_name, e
            )
            return None

    def _build_table_field_from_django_field(
        self, field, user=None
    ) -> Optional[TableFieldMetadata]:
        from django.db import models

        field_type = field.__class__.__name__
        title = str(getattr(field, "verbose_name", field.name))
        help_text = str(getattr(field, "help_text", ""))
        is_related = isinstance(
            field, (models.ForeignKey, models.OneToOneField, models.ManyToManyField)
        )

        permission_snapshot = (
            _build_field_permission_snapshot(user, field.model, field.name)
            if user is not None
            else None
        )
        if permission_snapshot and not permission_snapshot.can_read:
            return None

        editable_flag = getattr(field, "editable", True)
        if permission_snapshot and not permission_snapshot.can_write:
            editable_flag = False

        return TableFieldMetadata(
            name=field.name,
            accessor=field.name,
            display=f"{field.name}.desc" if is_related else field.name,
            editable=editable_flag,
            field_type=field_type,
            filterable=True,
            sortable=True,
            title=title,
            help_text = help_text,
            is_property=False,
            is_related=is_related,
            permissions=permission_snapshot,
        )

    def _build_table_field_for_property(
        self,
        prop_name: str,
        return_type,
        verbose_name: Optional[str] = None,
    ) -> TableFieldMetadata:
        import inspect
        from datetime import date, datetime, time
        from typing import Any, List, Union, get_args, get_origin

        def _to_graphql_str(py_type: Any) -> str:
            # Handle missing or Any annotations
            if py_type is Any or py_type is None or py_type is inspect._empty:
                return "String"

            # Base type mappings consistent with type generation
            base_map = {
                str: "String",
                int: "Int",
                float: "Float",
                bool: "Boolean",
                date: "Date",
                datetime: "DateTime",
                time: "Time",
            }

            # Dict and JSON-like types
            if py_type in (dict,):
                return "JSON"

            origin = get_origin(py_type)
            if origin is Union:
                # Optional/Union: pick first non-None type
                args = [arg for arg in get_args(py_type) if arg is not type(None)]
                return _to_graphql_str(args[0]) if args else "String"

            if origin is list:
                args = get_args(py_type)
                inner = _to_graphql_str(args[0]) if args else "String"
                return f"List[{inner}]"

            if origin in (dict,):
                return "JSON"

            return base_map.get(py_type, "String")

        field_type_str = _to_graphql_str(return_type)
        return TableFieldMetadata(
            name=prop_name,
            accessor=prop_name,
            display=prop_name,
            editable=False,
            field_type=field_type_str,
            filterable=True,
            sortable=True,
            title=str(verbose_name or prop_name),
            help_text = f"Computed property ({field_type_str})",
            is_property=True,
            is_related=False,
        )

    def _collect_pdf_templates(
        self, model: type[models.Model], user=None
    ) -> list[TemplateActionMetadata]:
        """
        Gather template metadata registered via @model_pdf_template for the model.
        """

        if not template_registry:
            return []

        try:
            registry_entries = template_registry.all().items()
        except Exception:  # pragma: no cover - defensive
            return []

        prefix = _templating_url_prefix().strip("/")
        api_prefix = f"/api/{prefix}".rstrip("/")
        templates: list[TemplateActionMetadata] = []

        for url_path, definition in registry_entries:
            if definition.model is not model:
                continue

            endpoint = f"{api_prefix}/{url_path.strip('/')}"
            decision = (
                evaluate_template_access(definition, user=user)
                if evaluate_template_access
                else None
            )
            allowed = decision.allowed if decision else True
            denial_reason = (
                decision.reason if decision and not decision.allowed else None
            )
            templates.append(
                TemplateActionMetadata(
                    key=f"{model._meta.app_label}.{model._meta.model_name}.{definition.method_name}",
                    method_name=definition.method_name,
                    title=definition.title,
                    endpoint=endpoint,
                    url_path=url_path,
                    guard=definition.guard or "retrieve",
                    require_authentication=definition.require_authentication,
                    roles=list(definition.roles or []),
                    permissions=list(definition.permissions or []),
                    allowed=allowed,
                    denial_reason=denial_reason,
                    allow_client_data=definition.allow_client_data,
                    client_data_fields=list(definition.client_data_fields or []),
                    client_data_schema=[
                        {
                            "name": entry.get("name"),
                            "type": entry.get("type", "string"),
                        }
                        for entry in (definition.client_data_schema or [])
                        if entry.get("name")
                    ],
                )
            )

        templates.sort(key=lambda tpl: tpl.title.lower())
        return templates

    def _build_table_field_for_reverse_count(
        self, introspector, model
    ) -> TableFieldMetadata:
        counts = []
        reverse_relations = introspector.get_manytoone_relations()
        for rel_name, related_model in reverse_relations.items():
            counts.append(
                TableFieldMetadata(
                    name=f"{rel_name}_count",
                    accessor=f"{rel_name}_count",
                    display=f"{rel_name}_count",
                    editable=False,
                    field_type="Count",
                    filterable=True,
                    sortable=True,
                    title=f"Related items count ({rel_name})",
                    help_text = f"Number of related reverse objects ({rel_name})",
                    is_property=False,
                    is_related=False,
                )
            )
        for field in model._meta.get_fields():
            if isinstance(field, models.ManyToManyField):
                counts.append(
                    TableFieldMetadata(
                        name=f"{field.name}_count",
                        accessor=f"{rel_name}_count",
                        display=f"{rel_name}_count",
                        editable=False,
                        field_type="Count",
                        filterable=True,
                        sortable=True,
                        title=f"Related items count ({field.verbose_name})",
                        help_text = f"Number of related reverse objects ({field.verbose_name})",
                        is_property=False,
                        is_related=False,
                    )
                )
        return counts

    def _translate_help_text_to_french(
        self, lookup_expr: str, verbose_name: str
    ) -> str:
        """
        Translate a lookup expression into French help text using the field verbose name.

        Purpose: Provide consistent help text for filter options in table metadata.
        Args:
            lookup_expr: Django lookup expression (e.g., 'exact', 'icontains')
            verbose_name: Human-readable field name to include in the message
        Returns:
            Translated help text string.
        """
        translations = {
            "exact": f"Correspondance exacte pour {verbose_name}",
            "iexact": f"Correspondance exacte insensible à la casse pour {verbose_name}",
            "contains": f"Contient le texte dans {verbose_name}",
            "icontains": f"Contient le texte (insensible à la casse) dans {verbose_name}",
            "startswith": f"Commence par le texte dans {verbose_name}",
            "istartswith": f"Commence par le texte (insensible à la casse) dans {verbose_name}",
            "endswith": f"Se termine par le texte dans {verbose_name}",
            "iendswith": f"Se termine par le texte (insensible à la casse) dans {verbose_name}",
            "in": f"Correspond à l'une des valeurs fournies pour {verbose_name}",
            "gt": f"Supérieur à la valeur pour {verbose_name}",
            "gte": f"Supérieur ou égal à la valeur pour {verbose_name}",
            "lt": f"Inférieur à la valeur pour {verbose_name}",
            "lte": f"Inférieur ou égal à la valeur pour {verbose_name}",
            "range": f"Valeur dans la plage pour {verbose_name}",
            "isnull": f"Vérifier si {verbose_name} est nul",
            "today": f"Filtrer pour la date d'aujourd'hui dans {verbose_name}",
            "yesterday": f"Filtrer pour la date d'hier dans {verbose_name}",
            "this_week": f"Filtrer pour les dates de cette semaine dans {verbose_name}",
            "this_month": f"Filtrer pour les dates de ce mois dans {verbose_name}",
            "this_year": f"Filtrer pour les dates de cette année dans {verbose_name}",
            "last_year": f"Filtrer pour les dates de l'année dernière dans {verbose_name}",
            "past_week": f"Filtrer pour les dates de la semaine dernière dans {verbose_name}",
            "past_month": f"Filtrer pour les dates du mois dernier dans {verbose_name}",
            "past_year": f"Filtrer pour les dates de l'année dernière dans {verbose_name}",
            # Synonyms support
            "last_week": f"Filtrer pour les dates de la semaine dernière dans {verbose_name}",
            "last_month": f"Filtrer pour les dates du mois dernier dans {verbose_name}",
            "year": f"Filtrer par année pour {verbose_name}",
            "month": f"Filtrer par mois pour {verbose_name}",
            "day": f"Filtrer par jour pour {verbose_name}",
        }
        return translations.get(
            lookup_expr, f"Filtre '{lookup_expr}' pour {verbose_name}"
        )

    # Custom fields for table metadata are no longer supported and have been removed.

    @cache_metadata(timeout=1, user_specific=False)
    def extract_model_table_metadata(
        self,
        app_name: str,
        model_name: str,
        custom_fields: Optional[list[str]] = None,
        counts: bool = False,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        include_nested: bool = True,
        only_lookup: Optional[list[str]] = None,
        exclude_lookup: Optional[list[str]] = None,
        include_filters: bool = True,
        include_mutations: bool = True,
        include_pdf_templates: bool = True,
        user=None,
    ) -> Optional[ModelTableMetadata]:
        # Refresh cache policy from settings on each call to reflect dynamic changes without restart.
        _load_table_cache_policy()
        debug_mode = _is_debug_mode()
        user_authenticated = bool(user and getattr(user, "is_authenticated", False))
        user_cache_key = _get_user_cache_key(user) if user_authenticated else None
        cache_enabled = bool(_table_cache_policy.get("enabled", True))
        if debug_mode:
            cache_enabled = False
        if user_authenticated:
            if not _table_cache_policy.get("cache_authenticated", False):
                cache_enabled = False
            elif not user_cache_key:
                cache_enabled = False
        else:
            cache_enabled = False
        cache_key = None
        if cache_enabled:
            try:
                cache_key = _make_table_cache_key(
                    self.schema_name,
                    app_name,
                    model_name,
                    counts,
                    exclude=exclude or [],
                    only=only or [],
                    include_nested=include_nested,
                    only_lookup=only_lookup or [],
                    exclude_lookup=exclude_lookup or [],
                    include_filters=include_filters,
                    include_mutations=include_mutations,
                    include_templates=include_pdf_templates,
                    user_cache_key=user_cache_key,
                )
                now = time.time()
                with _table_cache_lock:
                    entry = _table_cache.get(cache_key)
                    expires_at = entry.get("expires_at") if entry else None
                    if entry and (expires_at is None or expires_at > now):
                        _table_cache_stats["hits"] += 1
                        cached = entry.get("value")
                        if cached is not None:
                            return cached
                    _table_cache_stats["misses"] += 1
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                logger.debug(
                    "Skipping table cache lookup for %s.%s: %s",
                    app_name,
                    model_name,
                    exc,
                )

        model = self._get_model(app_name, model_name)
        if not model:
            return None

        meta = model._meta
        introspector = ModelIntrospector.for_model(model, self.schema_name)
        mutations: list[MutationMetadata] = []
        if include_mutations:
            try:
                mutations = self.metadata_extractor.extract_mutations_metadata(
                    model, user=user
                )
            except Exception as exc:
                logger.warning(
                    "Unable to extract mutations metadata for %s.%s: %s",
                    app_name,
                    model_name,
                    exc,
                )
                mutations = []

        # Detect polymorphic/multi-table inheritance and hide OneToOne relations
        # to avoid exposing parent/child or sibling pointers in table columns.
        # This is especially relevant for django-polymorphic where child models
        # include an auto-managed OneToOne link to the base model and projects
        # may define additional OneToOne links between siblings.
        try:
            from ..generators.inheritance import inheritance_handler

            inheritance_info = inheritance_handler.analyze_model_inheritance(model)
        except Exception:
            inheritance_info = {}

        # Basic heuristic: presence of polymorphic_ctype field, any parents, or any children
        is_polymorphic_model = False
        try:
            for _f in meta.get_fields():
                if getattr(_f, "name", None) == "polymorphic_ctype":
                    is_polymorphic_model = True
                    break
        except Exception:
            pass

        if getattr(meta, "parents", None):
            try:
                if len(meta.parents) > 0:
                    is_polymorphic_model = True
            except Exception:
                # Some Django versions expose parents as a dict-like
                is_polymorphic_model = True

        if inheritance_info and (
            inheritance_info.get("child_models")
            or inheritance_info.get("concrete_parents")
        ):
            is_polymorphic_model = True

        # Table-level metadata
        app_label = meta.app_label
        model_label = model.__name__
        verbose_name = str(meta.verbose_name)
        verbose_name_plural = str(meta.verbose_name_plural)
        table_name = str(meta.db_table)
        primary_key = meta.pk.name if meta.pk else "id"
        ordering = list(meta.ordering) if getattr(meta, "ordering", None) else []
        # Fallback ordering: latest_by or PK
        if not ordering:
            if getattr(meta, "get_latest_by", None):
                ordering = [f"-{meta.get_latest_by}"]
            else:
                ordering = [primary_key]
        default_ordering = ordering.copy()
        get_latest_by = getattr(meta, "get_latest_by", None)
        managers = [m.name for m in getattr(meta, "managers", [])] or [
            m.name for m in model._meta.managers
        ]
        managed = bool(getattr(meta, "managed", True))

        table_fields: list[TableFieldMetadata] = []
        generic_fields: list[TableFieldMetadata] = []

        # For polymorphic models, we need to handle inheritance hierarchy properly
        # to ensure fields from all parent classes are included in child metadata
        if is_polymorphic_model and inheritance_info:
            # Get all fields including inherited ones with proper model attribution
            all_fields = meta.get_fields(include_parents=True)
        else:
            all_fields = meta.get_fields()

        for f in all_fields:
            # Skip auto-created reverse accessors
            if getattr(f, "auto_created", False) and getattr(f, "is_relation", False):
                continue
            # Only include concrete or forward relation fields

            if (
                f.name == "polymorphic_ctype"
                or f.name == "id"
                or f.name.endswith("_ptr")
            ):
                continue

            # In polymorphic/multi-table inheritance contexts, hide OneToOne relations
            # (parent_link or explicit) from table exposure to prevent confusing columns.
            # These links are implementation details rather than user-facing table fields.
            if is_polymorphic_model and isinstance(f, models.OneToOneField):
                continue

            if getattr(f, "concrete", False) or (
                getattr(f, "is_relation", False)
                and not getattr(f, "auto_created", False)
            ):
                try:
                    try:
                        from django.contrib.contenttypes.fields import GenericRelation

                        if isinstance(f, GenericRelation):
                            meta_val = self._build_table_field_from_django_field(
                                f, user=user
                            )
                            if meta_val:
                                generic_fields.append(meta_val)
                            continue
                    except Exception:
                        pass
                    field_meta = self._build_table_field_from_django_field(f, user=user)
                    if field_meta:
                        table_fields.append(field_meta)
                except Exception as e:
                    logger.warning(f"Unable to build field metadata for {f.name}: {e}")
        # Properties from introspector should not surface polymorphic/internal links
        # In polymorphic/multi-table inheritance contexts, also hide properties that
        # correspond to OneToOne relations (parent_link or explicit), as they are
        # implementation details rather than user-facing table fields.
        try:
            properties_dict = getattr(introspector, "properties", {}) or {}
            # Build a set of OneToOne relation names and reverse accessor names
            # to filter property exposure in polymorphic contexts
            one_to_one_relation_names = set()
            reverse_relation_names = set()
            try:
                relationships_dict = getattr(introspector, "relationships", {}) or {}
                for rel_name, rel_info in relationships_dict.items():
                    if getattr(rel_info, "relationship_type", "") == "OneToOneField":
                        one_to_one_relation_names.add(rel_name)
            except Exception:
                # Be resilient if relationships are not available
                pass

            # Collect reverse relation accessor names (includes reverse OneToOne)
            try:
                if hasattr(introspector, "get_reverse_relations"):
                    reverse_relations = introspector.get_reverse_relations() or {}
                    for accessor_name in reverse_relations.keys():
                        reverse_relation_names.add(str(accessor_name))
            except Exception:
                pass

            existing_names = {getattr(tf, "name", None) for tf in table_fields}
            for prop_name, prop_info in properties_dict.items():
                # Skip internal/polymorphic properties and duplicates
                if (
                    prop_name == "pk"
                    or prop_name == "polymorphic_ctype"
                    or str(prop_name).endswith("_ptr")
                    or (
                        is_polymorphic_model
                        and (
                            prop_name in one_to_one_relation_names
                            or prop_name in reverse_relation_names
                        )
                    )
                ):
                    continue

                if prop_name in existing_names:
                    # Avoid duplicating a field already captured from Django model fields
                    continue

                verbose = getattr(prop_info, "verbose_name", prop_name)
                return_type = getattr(prop_info, "return_type", None)
                table_fields.append(
                    self._build_table_field_for_property(
                        prop_name, return_type, verbose
                    )
                )
        except Exception as E:
            # Properties may not be available; ignore quietly
            logger.debug(f"Properties extraction unavailable for {model.__name__}: {E}")
            pass

        # Reverse relationship count field if counts is True
        if counts:
            table_fields.extend(
                self._build_table_field_for_reverse_count(introspector, model)
            )
        # Filters: exclusively use AdvancedFilterGenerator for table filter extraction
        filters: list[dict[str, Any]] = []
        if include_filters:
            try:
                from ..generators.filter_inputs import AdvancedFilterGenerator

                filter_generator = AdvancedFilterGenerator(
                    enable_nested_filters=True, schema_name=self.schema_name
                )
                filter_cache_key = _make_filter_cache_key(self.schema_name, model)
                with _filter_cache_lock:
                    filter_class = _filter_class_cache.get(filter_cache_key)
                if filter_class is None:
                    filter_class = filter_generator.generate_filter_set(model)
                    with _filter_cache_lock:
                        _filter_class_cache[filter_cache_key] = filter_class

                # Collect property metadata to label property-based filters
                try:
                    properties_dict = getattr(introspector, "properties", {}) or {}
                except Exception:
                    properties_dict = {}

                grouped_filter_dict: dict[str, dict[str, Any]] = {}
                base_filters = getattr(filter_class, "base_filters", {}) or {}

                for fname, finstance in base_filters.items():
                    # Skip quick filter
                    if (
                        "quick" in fname
                        or "_ptr" in fname
                        or "polymorphic_ctype" in fname
                        or "_id" in fname
                        or fname == "pk"
                        or fname == "id"
                    ):
                        continue

                    parts = fname.split("__")
                    base_name = parts[0]
                    if (
                        base_name == "id"
                        or base_name == "pk"
                        or "report_rows" in base_name
                        or "_snapshots" in base_name
                        or "_policies" in base_name
                    ):
                        continue
                    # Determine lookup expression; if no explicit lookup, treat as exact
                    lookup_expr = "__".join(parts[1:]) or "exact"

                    # Special handling for time-based Boolean filters named with single underscores
                    # e.g., created_date_today, created_date_yesterday, etc.
                    # These should be grouped under the base field (created_date) with proper lookup.
                    rel_suffix_map = {
                        "_today": "today",
                        "_yesterday": "yesterday",
                        "_this_week": "this_week",
                        "_this_month": "this_month",
                        "_this_year": "this_year",
                        "_past_week": "past_week",
                        "_past_month": "past_month",
                        "_past_year": "past_year",
                        # Support 'last_*' synonyms used in some docs/exports
                        "_last_week": "past_week",
                        "_last_month": "past_month",
                        "_last_year": "past_year",
                    }
                    matched_suffix = None
                    for suf, lookup_val in rel_suffix_map.items():
                        if fname.endswith(suf):
                            matched_suffix = suf
                            lookup_expr = lookup_val
                            # Reset base_name to the field name without the suffix
                            base_name = fname[: -len(suf)]
                            break
                    # A filter is considered nested only when it references a deeper path
                    # beyond the base field (e.g., famille__name__icontains). Direct
                    # lookups on the base field (famille__in, famille__isnull, famille__exact)
                    # must remain at the parent level.
                    is_nested = (len(parts) > 2) and not fname.endswith("_count")

                    # Parent group key
                    group_key = base_name

                    # Resolve field and labels
                    field_obj = None
                    verbose_name_val = group_key
                    related_model_name = None
                    try:
                        field_obj = model._meta.get_field(base_name)
                        # Prefer using the related model's verbose names for relation groups
                        if getattr(field_obj, "related_model", None):
                            related_model_name = field_obj.related_model.__name__
                            rel_meta = field_obj.related_model._meta
                            verbose_name_val = str(
                                getattr(rel_meta, "verbose_name_plural", None)
                                or getattr(rel_meta, "verbose_name", base_name)
                            )
                        else:
                            verbose_name_val = str(
                                getattr(field_obj, "verbose_name", base_name)
                            )
                    except Exception:
                        # Property-based filters
                        prop_info = properties_dict.get(base_name)
                        if "_count" in base_name:
                            # remove "_count"
                            related_model = model._meta.get_field(
                                base_name.replace("_count", "")
                            ).related_model
                            label = base_name.replace("_count", "").upper()
                            if (
                                related_model._meta.verbose_name_plural
                                or related_model._meta.model_name
                            ):
                                label = (
                                    related_model._meta.verbose_name_plural
                                    or related_model._meta.model_name
                                ).lower()

                            verbose_name_val = f"Nombre total des {label} "

                        if prop_info is not None:
                            verbose_name_val = (
                                getattr(
                                    getattr(prop_info, "fget", None),
                                    "short_description",
                                    None,
                                )
                                or getattr(prop_info, "verbose_name", None)
                                or "Nombre de "
                                or base_name
                            )

                        # Reverse relation filters: if base_name is an accessor/related_name,
                        # derive label from the related model's verbose name(s)
                        if field_obj is None and (prop_info is None):
                            try:
                                reverse_rel = None
                                for f in model._meta.get_fields():
                                    # ManyToOneRel / ManyToManyRel have get_accessor_name
                                    accessor = getattr(f, "get_accessor_name", None)
                                    if callable(accessor) and accessor() == base_name:
                                        reverse_rel = f
                                        break
                                if reverse_rel is not None:
                                    rel_model = getattr(
                                        reverse_rel, "related_model", None
                                    )
                                    if rel_model is not None:
                                        related_model_name = rel_model.__name__
                                        rel_meta = rel_model._meta
                                        # Prefer plural for reverse relations (manager-like)
                                        verbose_name_val = str(
                                            getattr(
                                                rel_meta, "verbose_name_plural", None
                                            )
                                            or getattr(
                                                rel_meta, "verbose_name", base_name
                                            )
                                        )
                            except Exception as e:
                                logger.debug(
                                    f"Reverse relation label resolution failed for {model.__name__}.{base_name}: {e}"
                                )

                    # Compute choices for CharField choices on exact and in lookups
                    option_choices = None
                    try:
                        if field_obj is not None and isinstance(
                            field_obj, models.CharField
                        ):
                            raw_choices = getattr(field_obj, "choices", None)
                            if raw_choices and lookup_expr in ("exact", "in"):
                                option_choices = [
                                    {
                                        "value": self._json_safe_value(val),
                                        "label": force_str(lbl),
                                    }
                                    for val, lbl in raw_choices
                                ]
                    except Exception:
                        option_choices = None

                    # Initialize group with nested container
                    if group_key not in grouped_filter_dict:
                        grouped_filter_dict[group_key] = {
                            "field_name": group_key,
                            "is_nested": False,
                            "related_model": related_model_name,
                            "is_custom": False,
                            "field_label": verbose_name_val,
                            "options": [],
                            # Nested will be a list of FilterFieldType-like dicts
                            "nested": [],
                            # Internal: track seen parent lookups to avoid duplicates
                            "_seen_parent": set(),
                        }

                    # Helper to build an option dict
                    def _make_option(
                        name: str, lookup: str, label_for_help: str, choices_src: Any
                    ) -> dict[str, Any]:
                        return {
                            "name": name,
                            "lookup_expr": lookup,
                            "help_text": self._translate_help_text_to_french(
                                lookup, label_for_help
                            ),
                            "filter_type": finstance.__class__.__name__,
                            "choices": choices_src,
                        }

                    if not is_nested:
                        # Determine if this is a relation (ForeignKey/ManyToMany/etc.)
                        is_relation_field = bool(
                            getattr(field_obj, "is_relation", False)
                        )

                        # For parent-level options, avoid duplicates (e.g., base and __exact)
                        seen_parent = grouped_filter_dict[group_key].setdefault(
                            "_seen_parent", set()
                        )

                        # Related fields: keep only exact, in, isnull at parent level
                        if is_relation_field:
                            if lookup_expr in ("exact", "in", "isnull"):
                                # Canonical name for exact is the base field without lookup
                                if lookup_expr == "exact":
                                    if "exact" not in seen_parent:
                                        grouped_filter_dict[group_key][
                                            "options"
                                        ].append(
                                            _make_option(
                                                base_name,
                                                lookup_expr,
                                                verbose_name_val,
                                                option_choices,
                                            )
                                        )
                                        seen_parent.add("exact")
                                else:
                                    key = f"rel:{lookup_expr}"
                                    if key not in seen_parent:
                                        grouped_filter_dict[group_key][
                                            "options"
                                        ].append(
                                            _make_option(
                                                fname,
                                                lookup_expr,
                                                verbose_name_val,
                                                option_choices,
                                            )
                                        )
                                        seen_parent.add(key)
                            # Skip other lookups for relation parent field
                            continue

                        # Simple (non-relation) fields: include all available lookups
                        if lookup_expr == "exact":
                            if "exact" not in seen_parent:
                                grouped_filter_dict[group_key]["options"].append(
                                    _make_option(
                                        base_name,
                                        lookup_expr,
                                        verbose_name_val,
                                        option_choices,
                                    )
                                )
                                seen_parent.add("exact")
                        else:
                            key = f"simple:{lookup_expr}"
                            if key not in seen_parent:
                                grouped_filter_dict[group_key]["options"].append(
                                    _make_option(
                                        fname,
                                        lookup_expr,
                                        verbose_name_val,
                                        option_choices,
                                    )
                                )
                                seen_parent.add(key)
                        continue

                    # Nested: group under 'nested' for the specific nested field path
                    nested_path = fname.rsplit("__", 1)[0]
                    # For nested lookups, only the final token should be the lookup (e.g., 'exact')
                    nested_lookup_expr = (
                        fname.split("__")[-1] if "__" in fname else lookup_expr
                    )

                    # Determine nested field label by traversing the path
                    nested_label = nested_path
                    nested_option_choices = None
                    try:
                        current_model = model
                        segments = nested_path.split("__")
                        final_field_obj = None
                        # Walk segments to find the final field verbose name
                        for i, seg in enumerate(segments):
                            fobj = current_model._meta.get_field(seg)
                            if i < len(segments) - 1:
                                # Relation hop
                                if getattr(fobj, "related_model", None) is not None:
                                    current_model = fobj.related_model
                                else:
                                    break
                            else:
                                final_field_obj = fobj
                                nested_label = str(getattr(fobj, "verbose_name", seg))
                        # If nested field has choices and lookup is exact or in, expose them
                        if final_field_obj is not None and isinstance(
                            final_field_obj, models.CharField
                        ):
                            raw_choices = getattr(final_field_obj, "choices", None)
                            if raw_choices and nested_lookup_expr in ("exact", "in"):
                                nested_option_choices = [
                                    {
                                        "value": self._json_safe_value(val),
                                        "label": force_str(lbl),
                                    }
                                    for val, lbl in raw_choices
                                ]
                    except Exception:
                        nested_label = (
                            segments[-1]
                            if "segments" in locals() and segments
                            else nested_path
                        )

                    # Find or create nested entry
                    nested_groups = grouped_filter_dict[group_key].setdefault(
                        "_nested_groups", {}
                    )
                    if nested_path not in nested_groups:
                        nested_groups[nested_path] = {
                            "field_name": nested_path,
                            "is_nested": True,
                            "related_model": related_model_name,
                            "is_custom": False,
                            "field_label": nested_label,
                            "options": [],
                        }

                    # For exact nested lookups, include both 'path' and full 'fname' entries
                    if nested_lookup_expr == "exact":
                        nested_groups[nested_path]["options"].append(
                            _make_option(
                                nested_path,
                                nested_lookup_expr,
                                nested_label,
                                nested_option_choices,
                            )
                        )
                        nested_groups[nested_path]["options"].append(
                            _make_option(
                                fname,
                                nested_lookup_expr,
                                nested_label,
                                nested_option_choices,
                            )
                        )
                    else:
                        nested_groups[nested_path]["options"].append(
                            _make_option(
                                fname,
                                nested_lookup_expr,
                                nested_label,
                                nested_option_choices,
                            )
                        )

                # Finalize nested lists
                filters = []
                for gval in grouped_filter_dict.values():
                    nested_groups = gval.pop("_nested_groups", {})
                    # Remove internal tracking key if present
                    gval.pop("_seen_parent", None)
                    # Ensure 'exact' appears first in options if present
                    try:
                        opts = list(gval.get("options") or [])
                        if opts:
                            opts.sort(
                                key=lambda o: 0
                                if o.get("lookup_expr") == "exact"
                                else 1
                            )
                            gval["options"] = opts
                    except Exception:
                        # Non-critical ordering step; ignore on failure
                        pass
                    gval["nested"] = (
                        list(nested_groups.values()) if nested_groups else []
                    )
                    filters.append(gval)

                # Apply filter selection variables (exclude, only, include_nested, only_lookup, exclude_lookup)
                def _apply_filter_selection(
                    filters_in: list[dict[str, Any]],
                    only_fields: Optional[list[str]] = None,
                    exclude_fields: Optional[list[str]] = None,
                    include_nested_val: bool = True,
                    only_lk: Optional[list[str]] = None,
                    exclude_lk: Optional[list[str]] = None,
                ) -> list[dict[str, Any]]:
                    """
                    Purpose: Filter the computed filters according to selection variables.
                    Args:
                        filters_in: List of grouped filter dicts
                        only_fields: Field names to include (parent or nested paths)
                        exclude_fields: Field names to exclude (parent or nested paths)
                        include_nested_val: Whether to include nested groups globally
                        only_lk: Lookup expressions to include (e.g., ['exact','in'])
                        exclude_lk: Lookup expressions to exclude
                    Returns:
                        Filter list after applying selection rules
                    Raises:
                        None
                    Example:
                        >>> _apply_filter_selection(filters, only_fields=['name'], include_nested_val=False)
                        [{... 'field_name': 'name', 'nested': []}]
                    """
                    only_fields_set = set(only_fields or [])
                    exclude_fields_set = set(exclude_fields or [])
                    only_lk_set = set(only_lk or [])
                    exclude_lk_set = set(exclude_lk or [])

                    result: list[dict[str, Any]] = []
                    for grp in filters_in:
                        parent_name = grp.get("field_name")

                        # Exclude parent group if in exclude set
                        if parent_name in exclude_fields_set:
                            continue

                        # Determine if parent group should be included based on 'only'
                        include_parent = True
                        if only_fields_set:
                            include_parent = parent_name in only_fields_set or any(
                                (nested.get("field_name") in only_fields_set)
                                for nested in (grp.get("nested") or [])
                            )
                        if not include_parent:
                            continue

                        # Copy group to avoid modifying original
                        new_grp = dict(grp)

                        # Options: apply lookup filters
                        opts = list(new_grp.get("options") or [])
                        if only_lk_set:
                            opts = [
                                o for o in opts if o.get("lookup_expr") in only_lk_set
                            ]
                        if exclude_lk_set:
                            opts = [
                                o
                                for o in opts
                                if o.get("lookup_expr") not in exclude_lk_set
                            ]
                        # Reorder to place 'exact' first, preserving relative order otherwise
                        try:
                            if opts:
                                opts.sort(
                                    key=lambda o: 0
                                    if o.get("lookup_expr") == "exact"
                                    else 1
                                )
                        except Exception:
                            pass
                        new_grp["options"] = opts

                        # Nested handling
                        nested_list = list(new_grp.get("nested") or [])
                        # First, apply include_nested flag
                        if not include_nested_val:
                            # Allow nested entries only if explicitly requested via 'only'
                            if only_fields_set:
                                nested_list = [
                                    n
                                    for n in nested_list
                                    if n.get("field_name") in only_fields_set
                                ]
                            else:
                                nested_list = []
                        # Next, apply only/exclude field sets
                        if only_fields_set:
                            nested_list = [
                                n
                                for n in nested_list
                                if n.get("field_name") in only_fields_set
                            ]
                        if exclude_fields_set:
                            nested_list = [
                                n
                                for n in nested_list
                                if n.get("field_name") not in exclude_fields_set
                            ]

                        # Finally, apply lookup filters to nested options
                        for n in nested_list:
                            n_opts = list(n.get("options") or [])
                            if only_lk_set:
                                n_opts = [
                                    o
                                    for o in n_opts
                                    if o.get("lookup_expr") in only_lk_set
                                ]
                            if exclude_lk_set:
                                n_opts = [
                                    o
                                    for o in n_opts
                                    if o.get("lookup_expr") not in exclude_lk_set
                                ]
                            # Reorder nested options to place 'exact' first
                            try:
                                if n_opts:
                                    n_opts.sort(
                                        key=lambda o: 0
                                        if o.get("lookup_expr") == "exact"
                                        else 1
                                    )
                            except Exception:
                                pass
                            n["options"] = n_opts

                        new_grp["nested"] = nested_list
                        result.append(new_grp)

                    return result

                filters = _apply_filter_selection(
                    filters,
                    only_fields=only or [],
                    exclude_fields=exclude or [],
                    include_nested_val=include_nested,
                    only_lk=only_lookup or [],
                    exclude_lk=exclude_lookup or [],
                )
            except Exception as e:
                logger.warning(f"Error extracting filters for {model_label}: {e}")
                filters = []
        # Assemble final metadata
        pdf_templates = (
            self._collect_pdf_templates(model, user=user)
            if include_pdf_templates
            else []
        )

        metadata = ModelTableMetadata(
            metadata_version=_get_metadata_version_value(app_name, model_name),
            app=app_label,
            model=model_label,
            verbose_name = verbose_name,
            verbose_name_plural = verbose_name_plural,
            table_name = table_name,
            primary_key = primary_key,
            ordering=ordering,
            default_ordering = default_ordering,
            get_latest_by=get_latest_by,
            managers=managers,
            managed=managed,
            fields=table_fields,
            generics=generic_fields,
            filters=filters,
            permissions=_build_model_permission_matrix(model, user),
            mutations=mutations,
            pdf_templates=pdf_templates,
        )
        # Store in TTL cache
        if cache_enabled and cache_key:
            try:
                timeout = _get_table_cache_timeout()
                now = time.time()
                expires_at = None if timeout is None else now + timeout
                with _table_cache_lock:
                    _table_cache[cache_key] = {
                        "value": metadata,
                        "expires_at": expires_at,
                        "created_at": now,
                    }
                    _table_cache_stats["sets"] += 1
                    max_entries = _table_cache_policy.get("max_entries", 1000) or 0
                    if max_entries > 0 and len(_table_cache) > max_entries:
                        excess = len(_table_cache) - max_entries
                        oldest = sorted(
                            _table_cache.items(),
                            key=lambda kv: kv[1].get("created_at", 0),
                        )[:excess]
                        for k, _ in oldest:
                            _table_cache.pop(k, None)
                            _table_cache_stats["deletes"] += 1
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                logger.debug(
                    "Skipping table cache store for %s.%s: %s",
                    app_label,
                    model_label,
                    exc,
                )
        return metadata


class AvailableModelType(graphene.ObjectType):
    """GraphQL type for available models."""

    app_label = graphene.String(required=True, description="App label")
    model_name = graphene.String(required=True, description="Model name")
    graphene.String(required=True, description="Verbose name")


class ModelMetadataQuery(graphene.ObjectType):
    """GraphQL queries for model metadata."""

    available_models = graphene.List(
        AvailableModelType,
        description="List all available models in the project.",
    )

    model_metadata = graphene.Field(
        ModelMetadataType,
        app_name=graphene.String(required=True, description="Django app name"),
        model_name=graphene.String(required=True, description="Model class name"),
        nested_fields=graphene.Boolean(
            default_value=True, description="Include relationship metadata"
        ),
        permissions_included=graphene.Boolean(
            default_value=True, description="Include permission information"
        ),
        max_depth=graphene.Int(
            default_value=0,
            description="Maximum nesting depth for filters (default: 0)",
        ),
        description="Get comprehensive metadata for a Django model",
    )

    model_form_metadata = graphene.Field(
        ModelFormMetadataType,
        app_name=graphene.String(required=True, description="Django app name"),
        model_name=graphene.String(required=True, description="Model class name"),
        nested_fields=graphene.List(
            graphene.String,
            default_value=[],
            description="List of field names to include nested metadata for (depth 1)",
        ),
        exclude=graphene.List(
            graphene.String,
            default_value=[],
            description="List of regular field names to exclude from form metadata",
        ),
        only=graphene.List(
            graphene.String,
            default_value=[],
            description="List of regular field names to exclusively include in form metadata",
        ),
        exclude_relationships=graphene.List(
            graphene.String,
            default_value=[],
            description="Relationship field names to exclude from form metadata",
        ),
        only_relationships=graphene.List(
            graphene.String,
            default_value=[],
            description="Relationship field names to exclusively include in form metadata",
        ),
        description="Get comprehensive form metadata for a Django model",
    )

    model_table = graphene.Field(
        ModelTableType,
        app_name=graphene.String(required=True, description="Django app name"),
        model_name=graphene.String(required=True, description="Model class name"),
        counts=graphene.Boolean(
            default_value=False, description="Show reverse relationship count"
        ),
        exclude=graphene.List(
            graphene.String,
            default_value=[],
            description="List of field names to exclude from filters",
        ),
        only=graphene.List(
            graphene.String,
            default_value=[],
            description="List of field names to exclusively include in filters",
        ),
        include_nested=graphene.Boolean(
            default_value=True,
            description="Whether to include nested filter groups",
        ),
        only_lookup=graphene.List(
            graphene.String,
            default_value=[],
            description="Restrict filter options to these lookup expressions",
        ),
        exclude_lookup=graphene.List(
            graphene.String,
            default_value=[],
            description="Exclude these lookup expressions from filter options",
        ),
        description="Get comprehensive table metadata for a Django model",
    )

    app_models = graphene.List(
        ModelMetadataType,
        app_name=graphene.String(required=True, description="Django app name"),
        nested_fields=graphene.Boolean(
            default_value=True,
            description="Include nested relationship metadata for each model",
        ),
        permissions_included=graphene.Boolean(
            default_value=True,
            description="Include permission metadata when the user is authenticated",
        ),
        max_depth=graphene.Int(
            default_value=1, description="Maximum relationship depth to explore"
        ),
        description="Return the metadata for every model declared in the specified Django app.",
    )

    def resolve_available_models(self, info) -> list[AvailableModelType]:
        """Resolve list of all available models."""
        _require_metadata_access(info)
        available_models = []
        excluded_apps = ["admin", "auth", "contenttypes", "sessions"]

        for app_config in apps.get_app_configs():
            if app_config.label in excluded_apps:
                continue

            for model in app_config.get_models():
                # Filter out Historical models (django-simple-history)
                if model.__name__.startswith("Historical"):
                    continue

                available_models.append(
                    AvailableModelType(
                        app_label=app_config.label,
                        model_name=model.__name__,
                        verbose_name=str(model._meta.verbose_name),
                    )
                )
        return available_models

    def resolve_model_metadata(
        self,
        info,
        app_name: str,
        model_name: str,
        nested_fields: bool = True,
        permissions_included: bool = True,
        max_depth: int = 1,
    ) -> Optional[ModelMetadataType]:
        """
        Resolve model metadata with permission checking and settings validation.

        Args:
            info: GraphQL resolve info
            app_name: Django app name
            model_name: Model name
            nested_fields: Include nested relationship metadata
            permissions_included: Include permission-based field filtering
            max_depth: Maximum nesting depth for filters

        Returns:
            ModelMetadataType or None if not accessible
        """
        user = _require_metadata_access(info)
        selection_names = _get_requested_field_names(info)
        selection_defined = bool(selection_names)
        include_filters = (
            True if not selection_defined else "filters" in selection_names
        )
        include_mutations = (
            True if not selection_defined else "mutations" in selection_names
        )

        # Extract metadata via extractor which handles model lookup
        extractor = ModelMetadataExtractor(max_depth=max_depth)
        try:
            metadata = extractor.extract_model_metadata(
                app_name=app_name,
                model_name=model_name,
                user=user,
                nested_fields=nested_fields,
                permissions_included=permissions_included,
                include_filters=include_filters,
                include_mutations=include_mutations,
            )
        except Exception as exc:
            logger.warning(
                "Failed to extract metadata for %s.%s: %s",
                app_name,
                model_name,
                exc,
            )
            raise GraphQLError("Unable to load model metadata.")
        # Handle extraction error returning None
        if metadata is None:
            raise GraphQLError("Model metadata not available.")

        # Return dataclass directly for Graphene to resolve attributes
        return metadata

    def resolve_model_table(
        self,
        info,
        app_name: str,
        model_name: str,
        counts: bool = False,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        include_nested: bool = True,
        only_lookup: Optional[list[str]] = None,
        exclude_lookup: Optional[list[str]] = None,
    ) -> Optional[ModelTableType]:
        """Resolve comprehensive table metadata for a Django model."""
        user = _require_metadata_access(info)
        extractor = ModelTableExtractor()
        selection_names = _get_requested_field_names(info)
        selection_defined = bool(selection_names)
        include_filters = (
            True if not selection_defined else "filters" in selection_names
        )
        include_mutations = (
            True if not selection_defined else "mutations" in selection_names
        )
        include_pdf_templates = (
            True if not selection_defined else "pdfTemplates" in selection_names
        )
        try:
            metadata = extractor.extract_model_table_metadata(
                app_name=app_name,
                model_name=model_name,
                counts=counts,
                exclude=exclude or [],
                only=only or [],
                include_nested=include_nested,
                only_lookup=only_lookup or [],
                exclude_lookup=exclude_lookup or [],
                include_filters=include_filters,
                include_mutations=include_mutations,
                include_pdf_templates=include_pdf_templates,
                user=user,
            )
        except Exception as exc:
            logger.warning(
                "Failed to extract table metadata for %s.%s: %s",
                app_name,
                model_name,
                exc,
            )
            raise GraphQLError("Unable to load table metadata.")
        if metadata is None:
            raise GraphQLError("Table metadata not available.")
        return metadata

    def resolve_model_form_metadata(
        self,
        info,
        app_name: str,
        model_name: str,
        nested_fields: list[str] = None,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        exclude_relationships: Optional[list[str]] = None,
        only_relationships: Optional[list[str]] = None,
    ) -> Optional[ModelFormMetadataType]:
        """
        Resolve model form metadata for frontend form construction.

        Args:
            info: GraphQL resolve info
            app_name: Django app name
            model_name: Model name
            nested_fields: List of field names to include nested metadata for (depth 1)

        Returns:
            ModelFormMetadataType or None if not accessible
        """
        user = _require_metadata_access(info)

        # Extract form metadata via extractor which handles model lookup
        extractor = ModelFormMetadataExtractor(max_depth=1)
        try:
            metadata = extractor.extract_model_form_metadata(
                app_name=app_name,
                model_name=model_name,
                user=user,
                nested_fields=nested_fields or [],
                exclude=exclude or [],
                only=only or [],
                exclude_relationships=exclude_relationships or [],
                only_relationships=only_relationships or [],
            )
        except Exception as exc:
            logger.warning(
                "Failed to extract form metadata for %s.%s: %s",
                app_name,
                model_name,
                exc,
            )
            raise GraphQLError("Unable to load form metadata.")

        # Handle extraction error returning None
        if metadata is None:
            raise GraphQLError("Form metadata not available.")

        # Return dataclass directly for Graphene to resolve attributes
        return metadata

    def resolve_app_models(
        self,
        info,
        app_name: str,
        nested_fields: bool = True,
        permissions_included: bool = True,
        max_depth: int = 1,
    ) -> list[ModelMetadataType]:
        """
        Resolve metadata for every model inside the provided Django app.

        Args:
            info: GraphQL resolve info
            app_name: Django app label
            nested_fields: Include relationship metadata
            permissions_included: Include permission information when user is authenticated
            max_depth: Maximum relationship depth for related metadata
        """
        user = _require_metadata_access(info)
        selection_names = _get_requested_field_names(info)
        selection_defined = bool(selection_names)
        include_filters = (
            True if not selection_defined else "filters" in selection_names
        )
        include_mutations = (
            True if not selection_defined else "mutations" in selection_names
        )

        try:
            app_config = apps.get_app_config(app_name)
        except LookupError:
            logger.warning("app_models requested for unknown app '%s'", app_name)
            raise GraphQLError("Unknown app requested.")

        extractor = ModelMetadataExtractor(max_depth=max_depth)
        models_metadata: list[ModelMetadataType] = []
        for model in app_config.get_models():
            # Filter out Historical models (django-simple-history)
            if model.__name__.startswith("Historical"):
                continue
            try:
                metadata = extractor.extract_model_metadata(
                    app_name=app_name,
                    model_name=model.__name__,
                    user=user,
                    nested_fields=nested_fields,
                    permissions_included=permissions_included,
                    include_filters=include_filters,
                    include_mutations=include_mutations,
                )
                if metadata is not None:
                    models_metadata.append(metadata)
            except Exception as exc:
                logger.warning(
                    "Failed to load metadata for %s.%s: %s",
                    app_name,
                    model.__name__,
                    exc,
                )
        return models_metadata


# Cache invalidation signals - only invalidate when models actually change
@receiver(post_save, sender=None)
def invalidate_model_metadata_cache_on_save(sender, instance, created, **kwargs):
    """
    Invalidate metadata cache only when model structure changes.

    This is triggered when:
    - New models are created (migrations)
    - Model fields are added/removed (migrations)
    - Model relationships change (migrations)

    Args:
        sender: The model class that was saved
        instance: The model instance
        created: Whether this is a new instance
        **kwargs: Signal arguments
    """
    # Only invalidate cache for model structure changes, not data changes
    # We check if this is likely a migration or model structure change
    if sender and hasattr(sender, "_meta"):
        # Skip cache invalidation for regular data operations
        # Only invalidate during migrations or when model structure changes
        if _is_model_structure_change(sender, instance, created, **kwargs):
            app_name = sender._meta.app_label
            model_name = sender.__name__

            # Invalidate cache for this specific model
            invalidate_metadata_cache(model_name=model_name, app_name=app_name)
            logger.info(
                f"Invalidated metadata cache for {app_name}.{model_name} due to model structure change"
            )


@receiver(post_delete, sender=None)
def invalidate_model_metadata_cache_on_delete(sender, instance, **kwargs):
    """
    Invalidate metadata cache when models are deleted.

    This is more conservative and only invalidates when it's likely
    a model structure change rather than regular data deletion.

    Args:
        sender: The model class that was deleted
        instance: The model instance
        **kwargs: Signal arguments
    """
    if sender and hasattr(sender, "_meta"):
        # Only invalidate for structural changes, not regular deletions
        if _is_model_structure_change(sender, instance, False, **kwargs):
            app_name = sender._meta.app_label
            model_name = sender.__name__

            # Invalidate cache for this specific model
            invalidate_metadata_cache(model_name=model_name, app_name=app_name)
            logger.info(
                f"Invalidated metadata cache for {app_name}.{model_name} due to model deletion"
            )


@receiver(m2m_changed)
def invalidate_m2m_metadata_cache(sender, action, **kwargs):
    """
    Invalidate metadata cache when many-to-many relationships change structurally.

    Only invalidates on structural changes, not data changes.

    Args:
        sender: The through model for the m2m field
        action: The type of m2m change
        **kwargs: Signal arguments
    """
    # Only invalidate on structural changes, not data operations
    if (
        action in ["post_add", "post_remove", "post_clear"]
        and sender
        and hasattr(sender, "_meta")
    ):
        # Check if this is a structural change vs data change
        if _is_m2m_structure_change(sender, action, **kwargs):
            app_name = sender._meta.app_label
            model_name = sender.__name__

            # Invalidate cache for this specific model
            invalidate_metadata_cache(model_name=model_name, app_name=app_name)
            logger.info(
                f"Invalidated m2m metadata cache for {app_name}.{model_name} due to relationship structure change"
            )


def _is_model_structure_change(sender, instance, created, **kwargs):
    """
    Determine if this is a model structure change vs regular data operation.

    Args:
        sender: The model class
        instance: The model instance
        created: Whether this is a new instance
        **kwargs: Signal arguments

    Returns:
        bool: True if this is likely a structure change
    """
    # Check if we're in a migration context
    if _is_in_migration_context():
        return True

    # Check if this is a Django internal model that affects schema
    if sender._meta.app_label in ["contenttypes", "auth", "admin"]:
        # These apps can affect GraphQL schema structure
        return True

    # Check if this model has custom metadata that might affect schema
    if hasattr(sender, "_graphql_metadata_affects_schema"):
        return getattr(sender, "_graphql_metadata_affects_schema", False)

    # For now, be conservative and don't invalidate on regular data operations
    return False


def _is_m2m_structure_change(sender, action, **kwargs):
    """
    Determine if this is an M2M structure change vs regular data operation.

    Args:
        sender: The through model
        action: The M2M action
        **kwargs: Signal arguments

    Returns:
        bool: True if this is likely a structure change
    """
    # Check if we're in a migration context
    if _is_in_migration_context():
        return True

    # For now, be conservative and don't invalidate on regular M2M operations
    return False


def _is_in_migration_context():
    """
    Check if we're currently in a Django migration context.

    Returns:
        bool: True if in migration context
    """
    global _migration_context_cache
    if _migration_context_cache is not None:
        return _migration_context_cache

    import sys

    migration_commands = {"migrate", "makemigrations", "showmigrations"}
    if any(cmd in sys.argv for cmd in migration_commands):
        _migration_context_cache = True
        return True

    _migration_context_cache = False
    return False


# Cache warming functions
def warm_metadata_cache(app_name: str = None, model_name: str = None, user=None):
    """
    Pre-warm metadata cache for specified models.

    Args:
        app_name: Specific app to warm cache for (optional)
        model_name: Specific model to warm cache for (optional)
        user: User context for permission-based caching
    """
    extractor = ModelMetadataExtractor()

    if app_name and model_name:
        # Warm cache for specific model
        try:
            extractor.extract_model_metadata(app_name, model_name, user)
            logger.info(f"Warmed metadata cache for {app_name}.{model_name}")
        except Exception as e:
            logger.error(f"Failed to warm cache for {app_name}.{model_name}: {e}")
    elif app_name:
        # Warm cache for all models in app
        try:
            app_config = apps.get_app_config(app_name)
            for model in app_config.get_models():
                extractor.extract_model_metadata(app_name, model.__name__, user)
            logger.info(f"Warmed metadata cache for app {app_name}")
        except Exception as e:
            logger.error(f"Failed to warm cache for app {app_name}: {e}")
    else:
        # Warm cache for all models
        for app_config in apps.get_app_configs():
            for model in app_config.get_models():
                try:
                    extractor.extract_model_metadata(
                        app_config.label, model.__name__, user
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to warm cache for {app_config.label}.{model.__name__}: {e}"
                    )
        logger.info("Warmed metadata cache for all models")


def get_cache_stats() -> dict[str, Any]:
    """
    Purpose: Return TTL cache statistics for model table metadata.

    Args:
        None

    Returns:
        Dict[str, Any]: Cache statistics including hits, misses, hit rate, sets,
        deletes, invalidations, default timeout, and current cache size.

    Raises:
        None

    Example:
        >>> stats = get_cache_stats()
        >>> stats["hits"]
        0
    """
    # Safely snapshot current stats and size under lock
    with _table_cache_lock:
        stats_snapshot = dict(_table_cache_stats)
        cache_size = len(_table_cache)

    total_requests = stats_snapshot.get("hits", 0) + stats_snapshot.get("misses", 0)
    hit_rate = (
        (stats_snapshot.get("hits", 0) / total_requests) if total_requests else 0.0
    )

    return {
        "hits": stats_snapshot.get("hits", 0),
        "misses": stats_snapshot.get("misses", 0),
        "hit_rate": hit_rate,
        "sets": stats_snapshot.get("sets", 0),
        "deletes": stats_snapshot.get("deletes", 0),
        "invalidations": stats_snapshot.get("invalidations", 0),
        "default_timeout": _get_table_cache_timeout(),
        "size": cache_size,
    }


# Use lazy import to avoid AppRegistryNotReady error

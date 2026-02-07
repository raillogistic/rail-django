"""
Helper functions for Metadata V2.
"""

import hashlib
import time
import uuid
from typing import Any, Optional

from django.core.cache import cache
from django.conf import settings
from django.db import models

# Cache management

DYNAMIC_SCHEMA_KEYS = ("permissions", "mutations", "templates")
OVERLAY_CACHE_TIMEOUT_SECONDS = 3600


def get_model_version(app: str, model: str) -> str:
    """Get the current version token for a model's metadata."""
    key = f"metadata_version:{app}:{model}"
    version = cache.get(key)
    if not version:
        version = str(int(time.time() * 1000))
        cache.set(key, version, timeout=None)
    return str(version)


def _get_static_cache_key(
    app: str,
    model: str,
    version: Optional[str] = None,
) -> str:
    resolved_version = version or get_model_version(app, model)
    return f"metadata_static:{resolved_version}:{app}:{model}"


def _get_overlay_cache_key(
    app: str,
    model: str,
    user_id: Optional[str] = None,
    object_id: Optional[str] = None,
    version: Optional[str] = None,
) -> str:
    """Build cache key for auth-sensitive metadata overlay."""
    resolved_version = version or get_model_version(app, model)
    audience = "public"
    if user_id:
        audience = hashlib.sha1(str(user_id).encode()).hexdigest()[:8]

    key = f"metadata_overlay:{resolved_version}:{app}:{model}:aud:{audience}"

    if object_id:
        key = f"{key}:obj:{object_id}"

    return key


def _get_cache_key(
    app: str, model: str, user_id: Optional[str] = None, object_id: Optional[str] = None
) -> str:
    """
    Backward-compatible cache key helper.

    Returns the overlay key because permission-sensitive sections are now split out
    from the static model schema cache.
    """
    return _get_overlay_cache_key(app, model, user_id=user_id, object_id=object_id)


def _split_schema_payload(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    static_payload = dict(data)
    overlay_payload: dict[str, Any] = {}
    for key in DYNAMIC_SCHEMA_KEYS:
        if key in static_payload:
            overlay_payload[key] = static_payload.pop(key)
    return static_payload, overlay_payload


def _build_denied_permissions() -> dict[str, Any]:
    return {
        "can_list": False,
        "can_retrieve": False,
        "can_create": False,
        "can_update": False,
        "can_delete": False,
        "can_bulk_create": False,
        "can_bulk_update": False,
        "can_bulk_delete": False,
        "can_export": False,
        "denial_reasons": {"cache": "Dynamic metadata overlay unavailable"},
    }


def _merge_schema_payload(
    static_payload: dict[str, Any],
    overlay_payload: Optional[dict[str, Any]],
) -> dict[str, Any]:
    merged = dict(static_payload)
    if overlay_payload:
        merged.update(overlay_payload)
    else:
        merged.setdefault("permissions", _build_denied_permissions())
        merged.setdefault("mutations", [])
        merged.setdefault("templates", [])
    return merged


def get_cached_schema(
    app: str, model: str, user_id: Optional[str] = None, object_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Retrieve schema from cache."""
    # In DEBUG mode, we might want to skip cache for faster iteration
    if getattr(settings, "DEBUG", False):
        return None

    version = get_model_version(app, model)
    static_key = _get_static_cache_key(app, model, version=version)
    static_payload = cache.get(static_key)
    if not static_payload:
        return None

    overlay_key = _get_overlay_cache_key(
        app,
        model,
        user_id=user_id,
        object_id=object_id,
        version=version,
    )
    overlay_payload = cache.get(overlay_key)
    return _merge_schema_payload(static_payload, overlay_payload)


def set_cached_schema(
    app: str,
    model: str,
    data: dict[str, Any],
    user_id: Optional[str] = None,
    object_id: Optional[str] = None
) -> None:
    """Store schema in cache."""
    if getattr(settings, "DEBUG", False):
        return

    version = get_model_version(app, model)
    static_payload, overlay_payload = _split_schema_payload(data)

    static_key = _get_static_cache_key(app, model, version=version)
    cache.set(static_key, static_payload, timeout=OVERLAY_CACHE_TIMEOUT_SECONDS)

    overlay_key = _get_overlay_cache_key(
        app,
        model,
        user_id=user_id,
        object_id=object_id,
        version=version,
    )
    cache.set(overlay_key, overlay_payload, timeout=OVERLAY_CACHE_TIMEOUT_SECONDS)


def invalidate_metadata_cache(app: str = None, model: str = None) -> None:
    """Invalidate metadata v2 cache."""
    if app and model:
        # Bump version for specific model
        key = f"metadata_version:{app}:{model}"
        new_version = str(int(time.time() * 1000))
        cache.set(key, new_version, timeout=None)
    else:
        # For global invalidation, currently we don't have a global prefix.
        # But we can clear the whole cache if needed, though that's drastic.
        # Or we could iterate/broadcast if we had a registry of models.
        # For now, let's just support app/model specific invalidation as that's the primary use case (signals).
        pass

# Backward compatibility for imports
_cache_version = str(int(time.time() * 1000))


# =============================================================================
# Field Classification Helpers
# =============================================================================


def _is_fsm_field(field: Any) -> bool:
    """Check if field is django-fsm FSMField."""
    try:
        from django_fsm import FSMField

        return isinstance(field, FSMField)
    except ImportError:
        return False


def _get_fsm_transitions(
    model: type[models.Model], field_name: str, instance: Optional[models.Model] = None
) -> list[dict]:
    """
    Get FSM transitions for a field.
    If instance is provided, returns only transitions available for that instance.
    """
    try:
        from django_fsm import get_available_FIELD_transitions

        # If instance is provided, get available transitions for it
        available_transitions = set()
        if instance:
            # django-fsm adds get_available_FIELD_transitions method to model instance
            method_name = f"get_available_{field_name}_transitions"
            if hasattr(instance, method_name):
                # This returns the method objects that are valid transitions
                available_methods = getattr(instance, method_name)()
                available_transitions = {m.__name__ for m in available_methods}

        func = getattr(model, f"get_available_{field_name}_transitions", None)
        if not func:
            return []

        transitions = []
        for attr_name in dir(model):
            attr = getattr(model, attr_name, None)
            if hasattr(attr, "_django_fsm"):
                fsm_meta = attr._django_fsm
                if hasattr(fsm_meta, "field") and fsm_meta.field.name == field_name:
                    # Check if this transition is allowed for the instance
                    is_allowed = True
                    if instance:
                        is_allowed = attr_name in available_transitions

                    for source, target in getattr(fsm_meta, "transitions", {}).items():
                        transitions.append(
                            {
                                "name": attr_name,
                                "source": [source] if source != "*" else ["*"],
                                "target": target.target
                                if hasattr(target, "target")
                                else str(target),
                                "label": getattr(
                                    attr, "label", attr_name.replace("_", " ").title()
                                ),
                                "allowed": is_allowed,
                            }
                        )
        return transitions
    except Exception:
        return []


def _classify_field(field: models.Field) -> dict[str, bool]:
    """Return classification flags for a field."""
    field_type = type(field).__name__
    return {
        "is_primary_key": field.primary_key,
        "is_indexed": field.db_index or field.unique or field.primary_key,
        "is_relation": field.is_relation,
        "is_computed": False,
        "is_file": field_type in ("FileField", "FilePathField"),
        "is_image": field_type == "ImageField",
        "is_json": field_type == "JSONField",
        "is_date": field_type == "DateField",
        "is_datetime": field_type in ("DateTimeField", "DateField"),
        "is_time": field_type == "TimeField",
        "is_numeric": field_type
        in (
            "IntegerField",
            "SmallIntegerField",
            "BigIntegerField",
            "PositiveIntegerField",
            "PositiveSmallIntegerField",
            "PositiveBigIntegerField",
            "FloatField",
            "DecimalField",
        ),
        "is_boolean": field_type in ("BooleanField", "NullBooleanField"),
        # NullBooleanField removed in Django 4.0; kept for compatibility

        "is_text": field_type
        in ("CharField", "TextField", "SlugField", "URLField", "EmailField"),
        "is_rich_text": field_type == "TextField",
        "is_fsm_field": _is_fsm_field(field),
        "is_uuid": field_type == "UUIDField",
        "is_ip": field_type in ("IPAddressField", "GenericIPAddressField"),
        "is_duration": field_type == "DurationField",
    }

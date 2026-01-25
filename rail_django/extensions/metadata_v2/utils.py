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

def get_model_version(app: str, model: str) -> str:
    """Get the current version token for a model's metadata."""
    key = f"metadata_v2_version:{app}:{model}"
    version = cache.get(key)
    if not version:
        version = str(int(time.time() * 1000))
        cache.set(key, version, timeout=None)
    return str(version)


def _get_cache_key(
    app: str, model: str, user_id: Optional[str] = None, object_id: Optional[str] = None
) -> str:
    """Build cache key for model schema."""
    version = get_model_version(app, model)
    key = f"metadata_v2:{version}:{app}:{model}"

    if object_id:
        key = f"{key}:obj:{object_id}"

    if user_id:
        # Use a hash of user_id to keep key short/safe
        user_hash = hashlib.sha1(str(user_id).encode()).hexdigest()[:8]
        key = f"{key}:user:{user_hash}"

    return key


def get_cached_schema(
    app: str, model: str, user_id: Optional[str] = None, object_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Retrieve schema from cache."""
    # In DEBUG mode, we might want to skip cache for faster iteration
    if getattr(settings, "DEBUG", False):
        return None

    key = _get_cache_key(app, model, user_id, object_id)
    return cache.get(key)


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

    key = _get_cache_key(app, model, user_id, object_id)
    # Default timeout: 1 hour (3600 seconds)
    # We could make this configurable via settings
    cache.set(key, data, timeout=3600)


def invalidate_metadata_v2_cache(app: str = None, model: str = None) -> None:
    """Invalidate metadata v2 cache."""
    if app and model:
        # Bump version for specific model
        key = f"metadata_v2_version:{app}:{model}"
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

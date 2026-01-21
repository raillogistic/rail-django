"""
Helper functions for Metadata V2.
"""

import hashlib
import time
import uuid
from typing import Any, Optional

from django.db import models

# Cache management
_schema_cache: dict[str, dict[str, Any]] = {}
_cache_version = str(int(time.time() * 1000))


def _generate_version() -> str:
    """Generate a metadata version token."""
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _get_cache_key(app: str, model: str, user_id: Optional[str] = None) -> str:
    """Build cache key for model schema."""
    key = f"v2:{app}:{model}"
    if user_id:
        key = f"{key}:{hashlib.sha1(str(user_id).encode()).hexdigest()[:8]}"
    return key


def invalidate_metadata_v2_cache(app: str = None, model: str = None) -> None:
    """Invalidate metadata v2 cache."""
    global _cache_version
    _cache_version = _generate_version()
    _schema_cache.clear()


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


def _get_fsm_transitions(model: type[models.Model], field_name: str) -> list[dict]:
    """Get FSM transitions for a field."""
    try:
        from django_fsm import get_available_FIELD_transitions

        func = getattr(model, f"get_available_{field_name}_transitions", None)
        if not func:
            return []
        # Return static transition info (without instance)
        transitions = []
        for attr_name in dir(model):
            attr = getattr(model, attr_name, None)
            if hasattr(attr, "_django_fsm"):
                fsm_meta = attr._django_fsm
                if hasattr(fsm_meta, "field") and fsm_meta.field.name == field_name:
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
        "is_text": field_type
        in ("CharField", "TextField", "SlugField", "URLField", "EmailField"),
        "is_rich_text": field_type == "TextField",
        "is_fsm_field": _is_fsm_field(field),
        "is_uuid": field_type == "UUIDField",
        "is_ip": field_type in ("IPAddressField", "GenericIPAddressField"),
        "is_duration": field_type == "DurationField",
    }

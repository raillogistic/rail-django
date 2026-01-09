"""Helpers dedicated to model history serialization.

These utilities transform ``django-simple-history`` entries into JSON friendly
structures that expose which fields changed along with their previous/new
values. They are consumed by the GraphQL schema so that the frontend can
display rich audit logs instead of the raw ``history_*`` columns only.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from django.db import models

HistoryChangeList = List[Dict[str, Any]]


def _to_primitive(value: Any) -> Any:
    """Convert Django/Python values into JSON serialisable primitives."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        # ISO format keeps the timezone information and is understood by TS.
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, models.Model):
        return {
            "id": getattr(value, value._meta.pk.attname, None),
            "label": str(value),
        }
    if isinstance(value, dict):
        return {str(k): _to_primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_primitive(v) for v in value]
    # Fallback to string representation to avoid serialization errors.
    return str(value)


def _build_field_labels(instances: Iterable[Optional[models.Model]]) -> Dict[str, str]:
    """Collect verbose_name for a set of Django model instances."""
    labels: Dict[str, str] = {}
    for instance in instances:
        if instance is None:
            continue
        for field in instance._meta.get_fields():
            field_name = getattr(field, "name", None)
            if not field_name or field_name in labels:
                continue
            verbose = getattr(field, "verbose_name", field_name)
            labels[field_name] = str(verbose or field_name)
    return labels


def _get_choice_display(instance: Optional[models.Model], field_name: str) -> Optional[str]:
    """Return the translated display value for a choice field when available."""
    if instance is None:
        return None
    display_method = getattr(instance, f"get_{field_name}_display", None)
    if callable(display_method):
        try:
            return str(display_method())
        except Exception:
            return None
    value = getattr(instance, field_name, None)
    if isinstance(value, models.Model):
        return str(value)
    if value is None:
        return None
    return str(value)


def serialize_history_changes(history_instance: Any) -> HistoryChangeList:
    """Return the list of diffed fields for a historical entry.

    Args:
        history_instance: Instance emitted by ``django-simple-history``.

    Returns:
        List of dictionaries with the field name, human label and serialized
        previous/new values. When a diff cannot be computed the function
        degrades gracefully and returns an empty list.
    """

    def _safe_prev_record() -> Optional[Any]:
        prev = getattr(history_instance, "prev_record", None)
        if callable(prev):
            try:
                return prev()
            except Exception:
                return None
        return prev

    previous = _safe_prev_record()
    if previous is None:
        return []

    diff_against = getattr(history_instance, "diff_against", None)
    if diff_against is None:
        return []

    try:
        delta = diff_against(previous)
    except Exception:
        return []

    current_instance = getattr(history_instance, "instance", None)
    previous_instance = getattr(previous, "instance", None)
    field_labels = _build_field_labels([current_instance, previous_instance])

    changes: HistoryChangeList = []
    skip_fields = {"history_id", "history_date", "history_change_reason", "history_type", "history_user"}
    for change in getattr(delta, "changes", []):
        field_name = getattr(change, "field", None)
        if not field_name or field_name in skip_fields or field_name.startswith("history_"):
            continue
        label = field_labels.get(field_name, field_name.replace("_", " ").title())
        old_value = _to_primitive(getattr(change, "old", None))
        new_value = _to_primitive(getattr(change, "new", None))
        old_display = _get_choice_display(previous_instance, field_name)
        new_display = _get_choice_display(current_instance, field_name)
        changes.append(
            {
                "field": field_name,
                "label": label,
                "old_value": old_value,
                "new_value": new_value,
                "old_display": old_display,
                "new_display": new_display,
            }
        )
    return changes


__all__ = ["serialize_history_changes"]

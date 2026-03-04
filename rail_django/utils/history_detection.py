"""Helpers for identifying django-simple-history artifacts."""

from __future__ import annotations

from typing import Any


def is_historical_model(model: Any) -> bool:
    """Return True when model looks like a django-simple-history model."""
    try:
        name = getattr(model, "__name__", "")
        module = getattr(model, "__module__", "")
    except Exception:
        return False

    if str(name).startswith("Historical"):
        return True
    return "simple_history" in str(module)


def is_historical_records_attribute(model: Any, attr_name: str) -> bool:
    """Return True when a model attribute is backed by simple-history."""
    try:
        attr = getattr(model, attr_name)
    except Exception:
        return False

    attr_class = getattr(attr, "__class__", None)
    class_name = str(getattr(attr_class, "__name__", "")).lower()
    class_module = str(getattr(attr_class, "__module__", "")).lower()

    if "simple_history" in class_module:
        return True
    if class_name in {"historicalrecords", "historydescriptor"}:
        return True
    return False


def is_historical_relation_field(field: Any) -> bool:
    """Return True when a relation field/accessor targets historical records."""
    field_class = getattr(field, "__class__", None)
    class_module = str(getattr(field_class, "__module__", "")).lower()
    class_name = str(getattr(field_class, "__name__", "")).lower()

    if "simple_history" in class_module:
        return True
    if "historical" in class_name and "rel" in class_name:
        return True

    related_model = getattr(field, "related_model", None)
    if related_model is not None and is_historical_model(related_model):
        return True

    remote_field = getattr(field, "remote_field", None)
    remote_model = getattr(remote_field, "model", None) if remote_field else None
    if remote_model is not None and is_historical_model(remote_model):
        return True

    return False

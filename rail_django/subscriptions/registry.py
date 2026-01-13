"""
Registry for auto-generated GraphQL subscription classes.
"""

from __future__ import annotations

from typing import Dict, Iterator, Optional, Tuple, Type

from django.db import models

_SUBSCRIPTION_REGISTRY: Dict[str, Dict[str, Dict[str, Type]]] = {}


def register_subscription(
    schema_name: str,
    model_label: str,
    event: str,
    subscription_class: Type,
) -> None:
    schema_entry = _SUBSCRIPTION_REGISTRY.setdefault(schema_name, {})
    model_entry = schema_entry.setdefault(model_label, {})
    model_entry[event] = subscription_class

    from .broadcaster import ensure_broadcast_signals

    ensure_broadcast_signals()


def iter_subscriptions_for_model(
    model_class: Type[models.Model],
    event: Optional[str] = None,
) -> Iterator[Tuple[str, Type]]:
    model_label = model_class._meta.label_lower
    for schema_name, models_map in _SUBSCRIPTION_REGISTRY.items():
        events = models_map.get(model_label)
        if not events:
            continue
        if event:
            subscription_class = events.get(event)
            if subscription_class:
                yield schema_name, subscription_class
            continue
        for subscription_class in events.values():
            yield schema_name, subscription_class


def clear_subscription_registry() -> None:
    _SUBSCRIPTION_REGISTRY.clear()

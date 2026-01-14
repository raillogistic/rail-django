"""
Broadcast model events to subscription groups.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from django.db import transaction
from django.db.models.signals import post_delete, post_save

logger = logging.getLogger(__name__)

_SIGNALS_CONNECTED = False


def _snapshot_instance(instance) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        key = getattr(field, "attname", field.name)
        try:
            data[key] = field.value_from_object(instance)
        except Exception:
            data[key] = getattr(instance, key, None)
    return data


def ensure_broadcast_signals() -> None:
    global _SIGNALS_CONNECTED
    if _SIGNALS_CONNECTED:
        return

    post_save.connect(
        _handle_post_save,
        dispatch_uid="rail_django_subscription_post_save",
    )
    post_delete.connect(
        _handle_post_delete,
        dispatch_uid="rail_django_subscription_post_delete",
    )
    _SIGNALS_CONNECTED = True


def _handle_post_save(sender, instance, created: bool, **kwargs) -> None:
    if kwargs.get("raw"):
        return
    event = "created" if created else "updated"
    _schedule_broadcast(instance, event)


def _handle_post_delete(sender, instance, **kwargs) -> None:
    if kwargs.get("raw"):
        return
    _schedule_broadcast(instance, "deleted")


def _schedule_broadcast(instance, event: str) -> None:
    from .registry import iter_subscriptions_for_model

    subscriptions = list(iter_subscriptions_for_model(instance.__class__, event))
    if not subscriptions:
        return

    def _broadcast() -> None:
        payload = {
            "event": event,
            "pk": getattr(instance, "pk", None),
            "snapshot": _snapshot_instance(instance),
        }
        for schema_name, subscription_class in subscriptions:
            try:
                group_name = getattr(subscription_class, "group_name", None)
                subscription_class.broadcast(
                    group=group_name,
                    payload=payload,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to broadcast %s event for %s in schema '%s': %s",
                    event,
                    instance.__class__.__name__,
                    schema_name,
                    exc,
                )

    try:
        transaction.on_commit(_broadcast)
    except Exception:
        _broadcast()

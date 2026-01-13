"""Signal bindings for webhook delivery."""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from django.db import transaction
from django.db.models.signals import post_delete, post_save

from .dispatcher import dispatch_model_event

logger = logging.getLogger(__name__)

_SIGNALS_CONNECTED = False


def ensure_webhook_signals() -> None:
    global _SIGNALS_CONNECTED
    if _SIGNALS_CONNECTED:
        return

    post_save.connect(
        _handle_post_save,
        dispatch_uid="rail_django_webhook_post_save",
    )
    post_delete.connect(
        _handle_post_delete,
        dispatch_uid="rail_django_webhook_post_delete",
    )
    _SIGNALS_CONNECTED = True


def _handle_post_save(
    sender, instance, created: bool, update_fields: Optional[Iterable[str]] = None, **kwargs
) -> None:
    if kwargs.get("raw"):
        return
    event = "created" if created else "updated"
    _schedule_dispatch(instance, event, update_fields)


def _handle_post_delete(sender, instance, **kwargs) -> None:
    if kwargs.get("raw"):
        return
    _schedule_dispatch(instance, "deleted", None)


def _schedule_dispatch(instance, event: str, update_fields: Optional[Iterable[str]]) -> None:
    def _dispatch() -> None:
        try:
            dispatch_model_event(instance, event, update_fields=update_fields)
        except Exception as exc:
            logger.warning("Webhook dispatch failed for %s: %s", instance, exc)

    try:
        transaction.on_commit(_dispatch)
    except Exception:
        _dispatch()

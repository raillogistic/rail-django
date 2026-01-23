"""
Audit logging helpers for data modifications.

Provides a decorator-compatible helper used by mutation generators to emit
security events for create/update/delete operations.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Optional, Type, overload

from django.conf import settings
from django.db import models

from . import security
from .events.types import EventType, Outcome

logger = logging.getLogger(__name__)


def _resolve_event_type(operation: str) -> EventType:
    op = (operation or "").lower()
    if "bulk" in op:
        return EventType.DATA_BULK_OPERATION
    if op.startswith("create") or op == "add":
        return EventType.DATA_CREATE
    if op.startswith("delete") or op == "remove":
        return EventType.DATA_DELETE
    if op.startswith("update") or op == "set" or op == "edit":
        return EventType.DATA_UPDATE
    return EventType.DATA_UPDATE


def _get_request_from_info(info: Any) -> Optional[Any]:
    if info is None:
        return None
    ctx = getattr(info, "context", None)
    if ctx is None:
        return None
    if hasattr(ctx, "META"):
        return ctx
    if hasattr(ctx, "request"):
        return ctx.request
    return None


def _build_context(info: Any, model: Type[models.Model], operation: str) -> dict[str, Any]:
    context: dict[str, Any] = {
        "operation": operation,
        "model": getattr(model._meta, "label", model.__name__),
    }
    field_name = getattr(info, "field_name", None)
    if field_name:
        context["graphql_field"] = field_name
    variables = getattr(info, "variable_values", None)
    if isinstance(variables, dict) and variables:
        context["variable_keys"] = sorted(variables.keys())
    return context


def _emit_data_modification(
    *,
    info: Any,
    model: Type[models.Model],
    operation: str,
    instance: Optional[models.Model] = None,
) -> None:
    if not getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True):
        return

    event_type = _resolve_event_type(operation)
    request = _get_request_from_info(info)
    resource_name = getattr(model._meta, "label", model.__name__)
    resource_id = None
    if instance is not None:
        try:
            resource_id = str(instance.pk)
        except Exception:
            resource_id = None

    security.emit(
        event_type,
        request=request,
        outcome=Outcome.SUCCESS,
        action=f"{operation} {resource_name}",
        resource_type="model",
        resource_name=resource_name,
        resource_id=resource_id,
        context=_build_context(info, model, operation),
    )


@overload
def audit_data_modification(
    model: Type[models.Model],
    operation: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    ...


@overload
def audit_data_modification(
    *,
    info: Any,
    model: Type[models.Model],
    operation: str,
    instance: Optional[models.Model] = None,
) -> None:
    ...


def audit_data_modification(*args, **kwargs):
    """
    Log data modifications.

    Usage:
        audit_data_modification(model, "create")(func)
        audit_data_modification(info=info, model=MyModel, operation="create", instance=obj)
    """
    if len(args) == 2 and not kwargs:
        model, operation = args

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            def wrapper(info: Any, instance: Any = None, *f_args, **f_kwargs):
                result = func(info, instance, *f_args, **f_kwargs)
                try:
                    _emit_data_modification(
                        info=info,
                        model=model,
                        operation=operation,
                        instance=result or instance,
                    )
                except Exception as exc:
                    logger.warning("Audit logging failed: %s", exc)
                return result

            return wrapper

        return decorator

    if kwargs:
        try:
            _emit_data_modification(**kwargs)
        except Exception as exc:
            logger.warning("Audit logging failed: %s", exc)
        return None

    raise TypeError("audit_data_modification requires either (model, operation) or keyword args.")


class _AuditLogger:
    """Simple audit logger adapter for the core services hook."""

    def log_event(self, event: Any) -> None:
        from .events.bus import get_event_bus
        if event is None:
            return
        get_event_bus().emit(event)


audit_logger = _AuditLogger()

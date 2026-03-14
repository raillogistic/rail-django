"""
ABAC decorators for GraphQL resolvers.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from django.db import models
from graphql import GraphQLError


def require_attributes(
    subject_conditions: Optional[dict[str, Any]] = None,
    resource_conditions: Optional[dict[str, Any]] = None,
    environment_conditions: Optional[dict[str, Any]] = None,
    action_conditions: Optional[dict[str, Any]] = None,
    message: str = "Access denied by ABAC policy",
) -> Callable:
    """Require inline ABAC conditions before resolver execution."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            from .manager import abac_manager

            info = _extract_info(args, kwargs)
            if info is None:
                raise GraphQLError("GraphQL info context is required for ABAC checks")

            request_context = getattr(info, "context", None)
            user = getattr(request_context, "user", None)
            if user is None or not getattr(user, "is_authenticated", False):
                raise GraphQLError("Authentication required")

            decision = abac_manager.check_inline_access(
                subject_conditions=subject_conditions,
                resource_conditions=resource_conditions,
                environment_conditions=environment_conditions,
                action_conditions=action_conditions,
                user=user,
                instance=_extract_resource_instance(args, kwargs),
                model_class=_extract_model_class(args, kwargs),
                request=request_context,
                info=info,
                operation=getattr(getattr(info, "operation", None), "operation", None),
            )

            if not decision.allowed:
                raise GraphQLError(message)

            return func(*args, **kwargs)

        return wrapper

    return decorator


def _extract_info(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    info = kwargs.get("info")
    if info is not None:
        return info
    for arg in args:
        if hasattr(arg, "context"):
            return arg
    return None


def _extract_resource_instance(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Optional[Any]:
    for key in ("instance", "obj", "object", "resource"):
        value = kwargs.get(key)
        if value is not None:
            return value

    for arg in args:
        if hasattr(arg, "context"):
            continue
        if isinstance(arg, models.Model):
            return arg
    return None


def _extract_model_class(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Optional[type[models.Model]]:
    model_class = kwargs.get("model_class")
    if model_class is not None:
        return model_class

    instance = _extract_resource_instance(args, kwargs)
    if isinstance(instance, models.Model):
        return instance.__class__
    return None

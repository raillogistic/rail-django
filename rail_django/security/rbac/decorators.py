"""
Permission decorators for GraphQL resolvers.

This module provides decorators for enforcing role and permission requirements
on GraphQL resolver functions.
"""

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Optional, Union

from django.db import models
from graphql import GraphQLError

from .types import PermissionContext

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def _get_role_manager():
    """Lazy import to avoid circular imports."""
    from .manager import role_manager
    return role_manager


def require_role(required_roles: Union[str, list[str]]):
    """
    Decorator to require specific roles for a GraphQL resolver.

    Args:
        required_roles: Single role name or list of role names.

    Raises:
        GraphQLError: If user is not authenticated or lacks required roles.
    """
    if isinstance(required_roles, str):
        required_roles = [required_roles]

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            info = None
            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                    break

            if not info or not hasattr(info.context, "user"):
                raise GraphQLError("Contexte utilisateur non disponible")

            user = info.context.user
            if not user or not user.is_authenticated:
                raise GraphQLError("Authentification requise")

            role_manager = _get_role_manager()
            user_roles = role_manager.get_user_roles(user)

            if not any(role in user_roles for role in required_roles):
                raise GraphQLError(f"Roles requis: {', '.join(required_roles)}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


def _extract_object_instance(args: tuple, kwargs: dict) -> Optional[models.Model]:
    """Extract an object instance from resolver arguments."""
    for key in ("instance", "obj", "object"):
        if key in kwargs and kwargs[key] is not None:
            return kwargs[key]

    for arg in args:
        if hasattr(arg, "context"):
            continue
        if isinstance(arg, models.Model):
            return arg
    return None


def _extract_object_id(kwargs: dict) -> Optional[Any]:
    """Extract an object ID from resolver keyword arguments."""
    for key in ("object_id", "id", "pk"):
        if key in kwargs and kwargs[key] is not None:
            return kwargs[key]

    input_value = kwargs.get("input")
    if isinstance(input_value, dict):
        for key in ("object_id", "id", "pk"):
            if key in input_value and input_value[key] is not None:
                return input_value[key]
    elif input_value is not None:
        for key in ("object_id", "id", "pk"):
            if hasattr(input_value, key):
                value = getattr(input_value, key)
                if value is not None:
                    return value
    return None


def _infer_model_class(info) -> Optional[type[models.Model]]:
    """Infer the Django model class from GraphQL type information."""
    graphql_type = getattr(info, "return_type", None)
    while hasattr(graphql_type, "of_type"):
        graphql_type = graphql_type.of_type

    graphene_type = getattr(graphql_type, "graphene_type", None)
    meta = getattr(graphene_type, "_meta", None)
    model = getattr(meta, "model", None)
    if model is not None:
        return model
    return getattr(graphene_type, "model_class", None)


def _normalize_permission_context(
    context: Any,
    user: "AbstractUser",
    info: Any,
    args: tuple,
    kwargs: dict,
) -> PermissionContext:
    """Normalize various context formats into a PermissionContext."""
    if context is None:
        context = PermissionContext(user=user)
    elif isinstance(context, dict):
        known_keys = {
            "user", "object_instance", "instance", "object", "object_id", "id", "pk",
            "model_class", "operation", "organization_id", "department_id", "project_id",
            "additional_context",
        }
        extra = {key: value for key, value in context.items() if key not in known_keys}
        additional_context = context.get("additional_context") or extra or None

        context = PermissionContext(
            user=user,
            object_instance=(
                context.get("object_instance") or context.get("instance") or context.get("object")
            ),
            object_id=context.get("object_id") or context.get("id") or context.get("pk"),
            model_class=context.get("model_class"),
            operation=context.get("operation"),
            organization_id=context.get("organization_id"),
            department_id=context.get("department_id"),
            project_id=context.get("project_id"),
            additional_context=additional_context,
        )
    elif not isinstance(context, PermissionContext):
        context = PermissionContext(user=user, additional_context={"value": context})

    if context.user is None:
        context.user = user
    if context.additional_context is None:
        context.additional_context = {}
    if info is not None and isinstance(context.additional_context, dict):
        context.additional_context.setdefault("request", getattr(info, "context", None))

    if context.operation is None and info is not None:
        try:
            op_value = info.operation.operation.value if info.operation else None
        except Exception:
            op_value = None
        if op_value:
            if op_value == "query":
                context.operation = "read"
            elif op_value == "mutation":
                context.operation = "write"
            else:
                context.operation = op_value

    if context.object_instance is None:
        context.object_instance = _extract_object_instance(args, kwargs)

    if context.object_instance is not None and context.model_class is None:
        context.model_class = context.object_instance.__class__

    if context.object_id is None:
        context.object_id = _extract_object_id(kwargs)
        if context.object_id is None and context.object_instance is not None:
            context.object_id = getattr(context.object_instance, "pk", None)

    if context.model_class is None:
        context.model_class = _infer_model_class(info)

    return context


def require_permission(permission: str, context_func: Optional[Callable[..., Any]] = None):
    """
    Decorator to require a specific permission for a GraphQL resolver.

    Args:
        permission: The permission string to require (e.g., "project.update").
        context_func: Optional callable to extract context from resolver args.

    Raises:
        GraphQLError: If user is not authenticated or lacks the permission.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            info = None
            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                    break

            if not info or not hasattr(info.context, "user"):
                raise GraphQLError("Contexte utilisateur non disponible")

            user = info.context.user
            if not user or not user.is_authenticated:
                raise GraphQLError("Authentification requise")

            context = None
            if context_func:
                context = context_func(*args, **kwargs)
            context = _normalize_permission_context(context, user, info, args, kwargs)

            role_manager = _get_role_manager()
            if not role_manager.has_permission(user, permission, context):
                raise GraphQLError(f"Permission requise: {permission}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


__all__ = ["require_role", "require_permission"]

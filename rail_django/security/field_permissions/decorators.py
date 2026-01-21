"""
Decorators for field-level permission enforcement.

This module provides decorators that can be applied to GraphQL resolvers
to enforce field-level permissions.
"""

from functools import wraps
from typing import (
    TYPE_CHECKING,
    Callable,
    Optional,
    Type,
    TypeVar,
)

from django.db import models
from graphql import GraphQLError

from .types import (
    ACCESS_LEVEL_HIERARCHY,
    FieldAccessLevel,
    FieldContext,
)

if TYPE_CHECKING:
    pass

F = TypeVar("F", bound=Callable)


def field_permission_required(
    field_name: str,
    access_level: FieldAccessLevel = FieldAccessLevel.READ,
    model_class: Optional[Type[models.Model]] = None,
) -> Callable[[F], F]:
    """
    Decorator to verify field access permissions.

    This decorator checks that the current user has sufficient permissions
    to access a specific field before allowing the resolver to execute.

    Args:
        field_name: Name of the field to check permissions for.
        access_level: Minimum access level required.
        model_class: Optional model class for the permission check.

    Returns:
        Decorator function that enforces the permission check.

    Raises:
        GraphQLError: If user context is not available.
        GraphQLError: If user is not authenticated.
        GraphQLError: If model class cannot be determined.
        GraphQLError: If user has insufficient access level.

    Example:
        >>> @field_permission_required("salary", FieldAccessLevel.READ)
        ... def resolve_salary(root, info):
        ...     return root.salary
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Import here to avoid circular imports
            from .manager import field_permission_manager

            # Extract GraphQL context
            info = None
            instance = None

            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                elif isinstance(arg, models.Model):
                    instance = arg

            if not info or not hasattr(info.context, "user"):
                raise GraphQLError("User context not available")

            user = info.context.user
            if not user or not user.is_authenticated:
                raise GraphQLError("Authentication required")

            resolved_model_class = model_class
            if resolved_model_class is None and instance is not None:
                resolved_model_class = instance.__class__
            if resolved_model_class is None and info is not None:
                try:
                    graphene_type = getattr(info, "return_type", None)
                    meta = getattr(
                        getattr(graphene_type, "graphene_type", None), "_meta", None
                    )
                    resolved_model_class = getattr(meta, "model", None)
                except Exception:
                    resolved_model_class = None
            if resolved_model_class is None:
                raise GraphQLError(
                    "Model class is required for field permission checks"
                )

            context = FieldContext(
                user=user,
                instance=instance,
                field_name=field_name,
                operation_type="read",
                model_class=resolved_model_class,
            )

            user_access_level = field_permission_manager.get_field_access_level(context)

            # Check access level
            if (
                ACCESS_LEVEL_HIERARCHY[user_access_level]
                < ACCESS_LEVEL_HIERARCHY[access_level]
            ):
                raise GraphQLError(f"Insufficient access to field '{field_name}'")

            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def require_field_visibility(
    field_name: str,
    model_class: Optional[Type[models.Model]] = None,
) -> Callable[[F], F]:
    """
    Decorator to check field visibility before resolving.

    Unlike field_permission_required which checks access level, this decorator
    specifically checks visibility and returns None for hidden fields instead
    of raising an error.

    Args:
        field_name: Name of the field to check visibility for.
        model_class: Optional model class for the visibility check.

    Returns:
        Decorator function that enforces visibility.

    Example:
        >>> @require_field_visibility("email")
        ... def resolve_email(root, info):
        ...     return root.email
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            from .manager import field_permission_manager
            from .types import FieldVisibility

            info = None
            instance = None

            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                elif isinstance(arg, models.Model):
                    instance = arg

            if not info or not hasattr(info.context, "user"):
                return None

            user = info.context.user
            if not user:
                return None

            resolved_model_class = model_class
            if resolved_model_class is None and instance is not None:
                resolved_model_class = instance.__class__

            context = FieldContext(
                user=user,
                instance=instance,
                field_name=field_name,
                operation_type="read",
                model_class=resolved_model_class,
            )

            visibility, mask_value = field_permission_manager.get_field_visibility(
                context
            )

            if visibility == FieldVisibility.HIDDEN:
                return None
            elif visibility == FieldVisibility.MASKED:
                return mask_value

            result = func(*args, **kwargs)

            if visibility == FieldVisibility.REDACTED and result:
                if isinstance(result, str) and len(result) > 4:
                    return result[:2] + "*" * (len(result) - 4) + result[-2:]
                return "****"

            return result

        return wrapper  # type: ignore

    return decorator


def check_write_permission(
    field_name: str,
    model_class: Optional[Type[models.Model]] = None,
) -> Callable[[F], F]:
    """
    Decorator to verify write permission for a field.

    This decorator ensures the user has WRITE or ADMIN access level
    before allowing mutation operations on a field.

    Args:
        field_name: Name of the field to check write permission for.
        model_class: Optional model class for the permission check.

    Returns:
        Decorator function that enforces write permission.

    Raises:
        GraphQLError: If user does not have write access.

    Example:
        >>> @check_write_permission("status")
        ... def resolve_update_status(root, info, new_status):
        ...     root.status = new_status
        ...     root.save()
        ...     return root
    """
    return field_permission_required(
        field_name=field_name,
        access_level=FieldAccessLevel.WRITE,
        model_class=model_class,
    )


def check_admin_permission(
    field_name: str,
    model_class: Optional[Type[models.Model]] = None,
) -> Callable[[F], F]:
    """
    Decorator to verify admin permission for a field.

    This decorator ensures the user has ADMIN access level
    before allowing administrative operations on a field.

    Args:
        field_name: Name of the field to check admin permission for.
        model_class: Optional model class for the permission check.

    Returns:
        Decorator function that enforces admin permission.

    Raises:
        GraphQLError: If user does not have admin access.

    Example:
        >>> @check_admin_permission("is_active")
        ... def resolve_deactivate_user(root, info):
        ...     root.is_active = False
        ...     root.save()
        ...     return root
    """
    return field_permission_required(
        field_name=field_name,
        access_level=FieldAccessLevel.ADMIN,
        model_class=model_class,
    )

"""
Utility functions for authentication.

This module provides helper functions for permission handling and
user authentication from JWT tokens.
"""

import logging
from typing import TYPE_CHECKING, Optional, Any

from django.apps import apps
from django.contrib.auth import get_user_model

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

from ...security.rbac import role_manager
from ...extensions.permissions import (
    OperationType,
    PermissionInfo,
    permission_manager,
)

logger = logging.getLogger(__name__)


def _get_effective_permissions(user: "AbstractUser") -> list[str]:
    """
    Return a sorted list of effective permissions for a user.

    This function retrieves all permissions granted to a user through
    their roles and direct assignments, and returns them as a sorted list.

    Args:
        user: The Django user instance to get permissions for.

    Returns:
        A sorted list of permission strings. Returns an empty list if
        the user is None or if permissions cannot be retrieved.
    """
    if not user:
        return []


def _get_user_roles(user: "AbstractUser") -> list[str]:
    """
    Return a sorted list of user roles (RBAC + Django groups).

    Args:
        user: The Django user instance to get roles for.

    Returns:
        A sorted list of role/group names. Returns an empty list if
        the user is None or if roles cannot be retrieved.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if getattr(user, "pk", None) is None:
        return []

    roles: set[str] = set()

    try:
        roles.update(role_manager.get_user_roles(user))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Impossible de recuperer les roles RBAC de %s: %s", user, exc)

    try:
        roles.update(user.groups.values_list("name", flat=True))
    except Exception:
        # ignore group lookup failures
        pass

    # Ensure staff/superuser roles are always included.
    if getattr(user, "is_superuser", False):
        roles.add("superadmin")
    elif getattr(user, "is_staff", False):
        roles.add("admin")

    return sorted(roles)


def _serialize_permission(permission: Any) -> dict[str, str]:
    """
    Normalize a permission object or string into an API-friendly shape.
    """
    if hasattr(permission, "codename") and hasattr(permission, "name"):
        permission_id = getattr(permission, "id", None)
        return {
            "id": str(permission_id) if permission_id is not None else "",
            "name": str(permission.name),
            "codename": str(permission.codename),
        }

    perm_str = str(permission)
    return {
        "id": f"rbac:{perm_str}",
        "name": perm_str,
        "codename": perm_str,
    }


def _get_user_roles_detail(user: "AbstractUser") -> list[dict[str, Any]]:
    """
    Return RBAC roles and Django groups with permissions.

    Each role includes its name and a list of permissions in a normalized shape.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if getattr(user, "pk", None) is None:
        return []

    roles: dict[str, dict[str, Any]] = {}

    try:
        for group in user.groups.all():
            role = roles.setdefault(
                group.name,
                {"id": f"group:{group.id}", "name": group.name, "permissions": []},
            )
            if role.get("id", "").startswith("rbac:"):
                role["id"] = f"group:{group.id}"
            for perm in group.permissions.all():
                role["permissions"].append(_serialize_permission(perm))
    except Exception:
        pass

    try:
        role_names = role_manager.get_user_roles(user)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Impossible de recuperer les roles RBAC de %s: %s", user, exc)
        role_names = []

    for role_name in role_names:
        role = roles.setdefault(
            role_name,
            {"id": f"rbac:{role_name}", "name": role_name, "permissions": []},
        )
        role_def = role_manager.get_role_definition(role_name)
        if role_def:
            for perm in role_def.permissions:
                role["permissions"].append(_serialize_permission(perm))

    for role in roles.values():
        seen: set[str] = set()
        unique_permissions = []
        for perm in role.get("permissions", []):
            perm_id = str(perm.get("id", ""))
            if perm_id in seen:
                continue
            seen.add(perm_id)
            unique_permissions.append(perm)
        role["permissions"] = unique_permissions

    return list(roles.values())

    try:
        permissions = role_manager.get_effective_permissions(user)
        return sorted(permissions)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Impossible de recuperer les permissions de %s: %s", user, exc)
        return []


def _build_model_permission_snapshot(user: "AbstractUser") -> list[PermissionInfo]:
    """
    Return model-level CRUD permissions for a user.

    This function iterates through all registered Django models and
    checks which CRUD operations the user is allowed to perform on each.

    Args:
        user: The Django user instance to check permissions for.

    Returns:
        A list of PermissionInfo objects, one for each registered model,
        containing the user's CRUD permissions for that model. Returns
        an empty list if the user is None or not authenticated.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return []

    permissions: list[PermissionInfo] = []
    for model in apps.get_models():
        model_label = model._meta.label_lower
        permissions.append(
            PermissionInfo(
                model_name=model_label,
                verbose_name=str(model._meta.verbose_name),
                can_create=permission_manager.check_operation_permission(
                    user, model_label, OperationType.CREATE
                ).allowed,
                can_read=permission_manager.check_operation_permission(
                    user, model_label, OperationType.READ
                ).allowed,
                can_update=permission_manager.check_operation_permission(
                    user, model_label, OperationType.UPDATE
                ).allowed,
                can_delete=permission_manager.check_operation_permission(
                    user, model_label, OperationType.DELETE
                ).allowed,
                can_list=permission_manager.check_operation_permission(
                    user, model_label, OperationType.LIST
                ).allowed,
            )
        )

    return permissions


def get_user_from_token(token: str) -> Optional["AbstractUser"]:
    """
    Retrieve a user from a JWT token.

    This function verifies the provided JWT token and returns the
    corresponding user instance if the token is valid.

    Args:
        token: The JWT access token string.

    Returns:
        The User instance if the token is valid and the user exists,
        None otherwise.
    """
    # Import here to avoid circular imports
    from .jwt import JWTManager

    payload = JWTManager.verify_token(token, expected_type="access")
    if not payload:
        return None

    try:
        User = get_user_model()
        return User.objects.get(id=payload["user_id"])
    except User.DoesNotExist:
        return None


def authenticate_request(info) -> Optional["AbstractUser"]:
    """
    Authenticate a GraphQL request from the token in headers.

    This function extracts the JWT token from the Authorization header
    of the request and returns the authenticated user if valid.

    Args:
        info: The GraphQL resolve info object containing the request context.

    Returns:
        The User instance if authentication succeeds, None otherwise.

    Example:
        def resolve_protected_data(self, info):
            user = authenticate_request(info)
            if not user:
                raise PermissionDenied("Authentication required")
            return get_data_for_user(user)
    """
    request = info.context

    # Retrieve token from headers
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    return get_user_from_token(token)

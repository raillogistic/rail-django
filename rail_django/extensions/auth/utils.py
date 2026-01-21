"""
Utility functions for authentication.

This module provides helper functions for permission handling and
user authentication from JWT tokens.
"""

import logging
from typing import TYPE_CHECKING, Optional

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

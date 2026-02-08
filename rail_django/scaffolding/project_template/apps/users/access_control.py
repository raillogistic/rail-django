"""Roles and guards for user management."""

from typing import Dict, List

from rail_django.core.meta import GraphQLMeta

from apps.access_control import (
    build_operation_guards,
)

USER_ROLES: Dict[str, GraphQLMeta.Role] = {
    "user_viewer": GraphQLMeta.Role(
        name="user_viewer",
        description="Lecture seule des fiches utilisateurs.",
        role_type="functional",
        permissions=["users.read"],
    ),
    "user_manager": GraphQLMeta.Role(
        name="user_manager",
        description="Gère les comptes standards et profils.",
        role_type="functional",
        parent_roles=["user_viewer"],
        permissions=["users.manage"],
    ),
    "user_admin": GraphQLMeta.Role(
        name="user_admin",
        description="Administre les accès sensibles et peut supprimer.",
        role_type="business",
        parent_roles=["user_manager"],
        permissions=["users.admin"],
    ),
}

USER_READ_ROLES: List[str] = [
    "user_viewer",
    "user_manager",
    "user_admin",
]
USER_MANAGER_ROLES: List[str] = ["user_manager", "user_admin"]
USER_ADMIN_ROLES: List[str] = ["user_admin"]


def _decode_global_id(value: object) -> str:
    raw = "" if value is None else str(value)
    try:
        from graphql_relay import from_global_id

        _, decoded = from_global_id(raw)
        return str(decoded or raw)
    except Exception:
        return raw


def can_update_own_user(**kwargs) -> bool:
    """Allow authenticated users to update only their own User record."""
    user = kwargs.get("user")
    instance = kwargs.get("instance")
    if not user or not getattr(user, "is_authenticated", False):
        return False
    user_pk = str(getattr(user, "pk", "") or "")
    if not user_pk:
        return False

    if instance is not None and str(getattr(instance, "pk", "") or "") == user_pk:
        return True

    info = kwargs.get("info")
    if info is not None:
        variables = getattr(info, "variable_values", None) or {}
        if isinstance(variables, dict):
            raw_id = variables.get("id")
            if raw_id is not None and _decode_global_id(raw_id) == user_pk:
                return True

    return False


def user_operations():
    """Operations to control User objects."""

    return build_operation_guards(
        read_roles=USER_READ_ROLES,
        create_roles=USER_MANAGER_ROLES,
        delete_roles=USER_ADMIN_ROLES,
        extra={
            "update": GraphQLMeta.OperationGuard(
                roles=USER_MANAGER_ROLES,
                condition=can_update_own_user,
                match="any",
                deny_message="Operation 'update' is not permitted on User.",
            )
        },
    )


def profile_operations():
    """Operations to control UserProfile objects."""

    return build_operation_guards(
        read_roles=USER_READ_ROLES,
        create_roles=USER_MANAGER_ROLES,
        update_roles=USER_MANAGER_ROLES,
        delete_roles=USER_MANAGER_ROLES,
    )


def settings_operations():
    """Operations to control UserSettings objects."""

    return build_operation_guards(
        read_roles=USER_READ_ROLES,
        create_roles=USER_MANAGER_ROLES,
        update_roles=USER_MANAGER_ROLES,
        delete_roles=USER_MANAGER_ROLES,
    )

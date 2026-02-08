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


def can_update_own_user(**kwargs) -> bool:
    """Allow authenticated users to update only their own User record."""
    user = kwargs.get("user")
    instance = kwargs.get("instance")
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if instance is None:
        return False
    return getattr(instance, "pk", None) == getattr(user, "pk", None)


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

"""Roles and guards for user domain models."""

from typing import Dict, List

from rail_django.core.meta import GraphQLMeta

from apps.access_control import build_operation_guards


USER_ROLES: Dict[str, GraphQLMeta.Role] = {
    "user_viewer": GraphQLMeta.Role(
        name="user_viewer",
        description="Read-only access to users.",
        role_type="functional",
        permissions=["users.read"],
    ),
    "user_manager": GraphQLMeta.Role(
        name="user_manager",
        description="Manage user and profile records.",
        role_type="functional",
        parent_roles=["user_viewer"],
        permissions=["users.manage"],
    ),
    "user_admin": GraphQLMeta.Role(
        name="user_admin",
        description="Full control over user records.",
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


def user_operations():
    """Operations to control User objects."""

    return build_operation_guards(
        read_roles=USER_READ_ROLES,
        create_roles=USER_MANAGER_ROLES,
        update_roles=USER_MANAGER_ROLES,
        delete_roles=USER_ADMIN_ROLES,
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

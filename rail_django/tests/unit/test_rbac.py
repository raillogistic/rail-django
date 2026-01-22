"""
Unit tests for RBAC helpers and decorators.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from graphql import GraphQLError

from rail_django.security.rbac import (
    PermissionContext,
    RoleDefinition,
    RoleManager,
    RoleType,
    require_permission,
    require_role,
    role_manager,
)
from rail_django.security.policies import AccessPolicy, PolicyEffect, policy_manager
from test_app.models import Category

pytestmark = pytest.mark.unit


class _InfoStub:
    def __init__(self, user):
        self.context = SimpleNamespace(user=user)


@pytest.mark.django_db
def test_assign_role_to_user_adds_group_and_permissions():
    user = User.objects.create_user(username="rbac_user", password="pass12345")
    role_manager.assign_role_to_user(user, "manager")

    roles = role_manager.get_user_roles(user)
    assert "manager" in roles
    assert role_manager.has_permission(user, "project.create") is True


@pytest.mark.django_db
def test_assign_role_respects_max_users():
    role_name = "limited_role"
    role_manager.register_role(
        RoleDefinition(
            name=role_name,
            description="Limited role",
            role_type=RoleType.BUSINESS,
            permissions=["project.read"],
            max_users=1,
        )
    )

    user_one = User.objects.create_user(username="limited_one", password="pass12345")
    user_two = User.objects.create_user(username="limited_two", password="pass12345")

    role_manager.assign_role_to_user(user_one, role_name)
    with pytest.raises(ValueError):
        role_manager.assign_role_to_user(user_two, role_name)


@pytest.mark.django_db
def test_require_role_decorator_blocks_missing_role():
    user = User.objects.create_user(username="plain_user", password="pass12345")
    info = _InfoStub(user)

    @require_role("admin")
    def _secured(_, info):
        return "ok"

    with pytest.raises(GraphQLError):
        _secured(None, info)


@pytest.mark.django_db
def test_require_permission_decorator_allows_with_role_permission():
    user = User.objects.create_user(username="perm_user", password="pass12345")
    role_manager.assign_role_to_user(user, "manager")
    info = _InfoStub(user)

    @require_permission("project.read")
    def _secured(_, info):
        return "ok"

    assert _secured(None, info) == "ok"


@pytest.mark.django_db
def test_contextual_permission_requires_permission_and_owner():
    manager = RoleManager()
    role_name = "context_owner_role"
    manager.register_role(
        RoleDefinition(
            name=role_name,
            description="Owner-only role",
            role_type=RoleType.BUSINESS,
            permissions=["project.update_own"],
        )
    )

    user = User.objects.create_user(username="owner_user", password="pass12345")
    other_user = User.objects.create_user(
        username="other_user", password="pass12345"
    )
    manager.assign_role_to_user(user, role_name)

    owned_object = SimpleNamespace(owner=user)
    context = PermissionContext(user=user, object_instance=owned_object)
    assert manager.has_permission(user, "project.update_own", context) is True

    not_owned_object = SimpleNamespace(owner=other_user)
    context_not_owner = PermissionContext(
        user=user, object_instance=not_owned_object
    )
    assert manager.has_permission(
        user, "project.update_own", context_not_owner
    ) is False

    no_role_user = User.objects.create_user(
        username="no_role_user", password="pass12345"
    )
    no_role_context = PermissionContext(
        user=no_role_user, object_instance=SimpleNamespace(owner=no_role_user)
    )
    assert manager.has_permission(
        no_role_user, "project.update_own", no_role_context
    ) is False


@pytest.mark.django_db
def test_contextual_permission_requires_assignment():
    manager = RoleManager()
    role_name = "context_assigned_role"
    manager.register_role(
        RoleDefinition(
            name=role_name,
            description="Assigned-only role",
            role_type=RoleType.BUSINESS,
            permissions=["task.update_assigned"],
        )
    )

    user = User.objects.create_user(username="assigned_user", password="pass12345")
    other_user = User.objects.create_user(
        username="unassigned_user", password="pass12345"
    )
    manager.assign_role_to_user(user, role_name)

    assigned_object = SimpleNamespace(assigned_to=user)
    context = PermissionContext(user=user, object_instance=assigned_object)
    assert manager.has_permission(user, "task.update_assigned", context) is True

    unassigned_object = SimpleNamespace(assigned_to=other_user)
    context_unassigned = PermissionContext(
        user=user, object_instance=unassigned_object
    )
    assert manager.has_permission(
        user, "task.update_assigned", context_unassigned
    ) is False


@pytest.mark.django_db
def test_role_hierarchy_cycle_guard():
    manager = RoleManager()
    manager.register_role(
        RoleDefinition(
            name="cycle_role_a",
            description="Cycle role A",
            role_type=RoleType.BUSINESS,
            permissions=["cycle.a"],
            parent_roles=["cycle_role_b"],
        )
    )
    manager.register_role(
        RoleDefinition(
            name="cycle_role_b",
            description="Cycle role B",
            role_type=RoleType.BUSINESS,
            permissions=["cycle.b"],
            parent_roles=["cycle_role_a"],
        )
    )

    user = User.objects.create_user(username="cycle_user", password="pass12345")
    manager.assign_role_to_user(user, "cycle_role_a")

    permissions = manager.get_effective_permissions(user)
    assert "cycle.a" in permissions
    assert "cycle.b" in permissions


@pytest.mark.django_db
def test_policy_deny_overrides_role_permission():
    policy_manager.clear_policies()
    try:
        role_name = "policy_deny_role"
        role_manager.register_role(
            RoleDefinition(
                name=role_name,
                description="Policy deny role",
                role_type=RoleType.BUSINESS,
                permissions=["project.read"],
            )
        )

        user = User.objects.create_user(
            username="policy_user", password="pass12345"
        )
        role_manager.assign_role_to_user(user, role_name)

        policy_manager.register_policy(
            AccessPolicy(
                name="deny_project_read",
                effect=PolicyEffect.DENY,
                permissions=["project.read"],
                priority=10,
            )
        )

        assert role_manager.has_permission(user, "project.read") is False
    finally:
        policy_manager.clear_policies()


@pytest.mark.django_db
def test_owner_resolver_override_allows_contextual_access():
    manager = RoleManager()
    role_name = "resolver_owner_role"
    manager.register_role(
        RoleDefinition(
            name=role_name,
            description="Owner resolver role",
            role_type=RoleType.BUSINESS,
            permissions=["category.update_own"],
        )
    )

    user = User.objects.create_user(username="resolver_user", password="pass12345")
    manager.assign_role_to_user(user, role_name)

    category = Category.objects.create(name="Secure", description="Secured")
    context = PermissionContext(user=user, object_instance=category)

    assert manager.has_permission(user, "category.update_own", context) is False

    manager.register_owner_resolver(Category, lambda ctx: True)

    assert manager.has_permission(user, "category.update_own", context) is True



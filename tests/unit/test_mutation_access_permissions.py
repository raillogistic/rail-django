from types import SimpleNamespace

import pytest
from django.db import models

from rail_django.core.meta.config import OperationGuardConfig
from rail_django.core.meta.graphql_meta import GraphQLMeta, get_model_graphql_meta
from rail_django.core.mutation_permissions import evaluate_mutation_access


pytestmark = pytest.mark.unit


class _RoleManagerStub:
    def __init__(self, permissions):
        self.permissions = set(permissions)

    def get_effective_permissions(self, user):
        return set(self.permissions)

    def _permission_in_effective_permissions(self, permission, effective_permissions):
        return permission in effective_permissions

    def get_user_roles(self, user):
        return []


def _user_without_django_perm():
    user = SimpleNamespace()
    user.is_authenticated = True
    user.is_superuser = False
    user.has_perm = lambda _permission: False
    return user


def test_evaluate_mutation_access_accepts_role_derived_permissions(monkeypatch):
    monkeypatch.setattr(
        "rail_django.core.mutation_permissions._resolve_role_manager",
        lambda: _RoleManagerStub({"operations.validate_restitution"}),
    )

    decision = evaluate_mutation_access(
        {"permissions": ["operations.validate_restitution"]},
        user=_user_without_django_perm(),
    )

    assert decision["allowed"] is True


def test_operation_guard_accepts_role_derived_permissions(monkeypatch):
    monkeypatch.setattr(
        "rail_django.core.meta.api.load_security_components",
        lambda: {
            "role_manager": _RoleManagerStub({"operations.validate_restitution"})
        },
    )

    class DummyModel(models.Model):
        class Meta:
            app_label = "test_app"

        class GraphQLMeta:
            access = GraphQLMeta.AccessControl(
                operations={
                    "update": OperationGuardConfig(
                        name="update",
                        permissions=["operations.validate_restitution"],
                        require_authentication=True,
                    )
                }
            )

    try:
        meta = get_model_graphql_meta(DummyModel)
        guard_state = meta.describe_operation_guard(
            "update",
            user=_user_without_django_perm(),
        )

        assert guard_state["allowed"] is True
    finally:
        if hasattr(DummyModel, "_graphql_meta_instance"):
            delattr(DummyModel, "_graphql_meta_instance")

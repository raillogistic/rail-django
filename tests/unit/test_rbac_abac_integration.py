"""Unit tests for RBAC core integration with hybrid ABAC decisions."""

import pytest
from django.contrib.auth.models import User

from rail_django.security.abac import ABACPolicy, ConditionOperator, MatchCondition, abac_engine
from rail_django.security.hybrid.engine import HybridDecision
from rail_django.security.hybrid.strategies import CombinationStrategy
from rail_django.security.rbac import RoleDefinition, RoleManager, RoleType

pytestmark = pytest.mark.unit


def _patch_abac_enabled(monkeypatch):
    def _eval_get_setting(key, default=None, schema_name=None):
        if key == "security_settings.enable_abac":
            return True
        return default

    def _hybrid_get_setting(key, default=None, schema_name=None):
        if key == "security_settings.enable_abac":
            return True
        if key == "security_settings.hybrid_strategy":
            return "rbac_and_abac"
        if key == "security_settings.abac_default_effect":
            return "deny"
        return default

    monkeypatch.setattr("rail_django.security.rbac.evaluation.get_setting", _eval_get_setting)
    monkeypatch.setattr("rail_django.security.hybrid.engine.get_setting", _hybrid_get_setting)


@pytest.mark.django_db
def test_role_manager_has_permission_applies_abac_when_enabled(monkeypatch):
    _patch_abac_enabled(monkeypatch)
    abac_engine.clear_policies()
    try:
        manager = RoleManager()
        manager._permission_cache_enabled = False

        role_name = "rbac_abac_role"
        manager.register_role(
            RoleDefinition(
                name=role_name,
                description="Role with read access",
                role_type=RoleType.BUSINESS,
                permissions=["test.read"],
            )
        )
        user = User.objects.create_user(username="rbac_abac_user", password="pass12345")
        manager.assign_role_to_user(user, role_name)

        abac_engine.register_policy(
            ABACPolicy(
                name="deny_authenticated_users",
                effect="deny",
                subject_conditions={
                    "authenticated": MatchCondition(ConditionOperator.EQ, value=True)
                },
            )
        )

        assert manager.has_permission(user, "test.read") is False
    finally:
        abac_engine.clear_policies()


@pytest.mark.django_db
def test_role_manager_does_not_cache_hybrid_abac_decisions(monkeypatch):
    _patch_abac_enabled(monkeypatch)
    manager = RoleManager()

    role_name = "rbac_abac_uncached_role"
    manager.register_role(
        RoleDefinition(
            name=role_name,
            description="Role with read access",
            role_type=RoleType.BUSINESS,
            permissions=["test.read"],
        )
    )
    user = User.objects.create_user(
        username="rbac_abac_uncached_user",
        password="pass12345",
    )
    manager.assign_role_to_user(user, role_name)

    decisions = iter(
        [
            HybridDecision(
                allowed=False,
                rbac_allowed=True,
                abac_allowed=False,
                strategy=CombinationStrategy.RBAC_AND_ABAC,
                reason="first",
            ),
            HybridDecision(
                allowed=True,
                rbac_allowed=True,
                abac_allowed=True,
                strategy=CombinationStrategy.RBAC_AND_ABAC,
                reason="second",
            ),
        ]
    )
    monkeypatch.setattr(
        "rail_django.security.hybrid.engine.hybrid_engine.has_permission",
        lambda *args, **kwargs: next(decisions),
    )

    assert manager.has_permission(user, "test.read") is False
    assert manager.has_permission(user, "test.read") is True

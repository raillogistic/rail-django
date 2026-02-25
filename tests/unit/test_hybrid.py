"""Unit tests for hybrid RBAC + ABAC decisions."""

import pytest
from django.contrib.auth.models import User

from rail_django.security.abac import ABACEngine, ABACPolicy, MatchCondition, ConditionOperator
from rail_django.security.abac.manager import ABACManager
from rail_django.security.hybrid.engine import HybridPermissionEngine
from rail_django.security.hybrid.strategies import CombinationStrategy
from rail_django.security.rbac import RoleDefinition, RoleManager, RoleType

pytestmark = pytest.mark.unit


def _mock_abac_enabled(monkeypatch, strategy: CombinationStrategy):
    def _get_setting(key, default=None, schema_name=None):
        if key == "security_settings.enable_abac":
            return True
        if key == "security_settings.hybrid_strategy":
            return strategy.value
        if key == "security_settings.abac_default_effect":
            return "deny"
        return default

    monkeypatch.setattr("rail_django.security.hybrid.engine.get_setting", _get_setting)


@pytest.mark.django_db
class TestHybridStrategies:
    def _setup(self, strategy: CombinationStrategy, monkeypatch):
        _mock_abac_enabled(monkeypatch, strategy)
        rbac = RoleManager()
        abac_engine = ABACEngine()
        abac = ABACManager(engine=abac_engine)
        engine = HybridPermissionEngine(rbac=rbac, abac=abac, strategy=strategy)
        return rbac, abac_engine, engine

    def test_rbac_and_abac_both_must_allow(self, monkeypatch):
        rbac, abac_engine, engine = self._setup(
            CombinationStrategy.RBAC_AND_ABAC, monkeypatch
        )
        user = User.objects.create_user("hybrid_and", password="pass12345")
        rbac.register_role(
            RoleDefinition(
                name="tester",
                role_type=RoleType.BUSINESS,
                description="Test role",
                permissions=["test.read"],
            )
        )
        rbac.assign_role_to_user(user, "tester")

        abac_engine.register_policy(
            ABACPolicy(
                name="deny_authenticated",
                effect="deny",
                subject_conditions={
                    "authenticated": MatchCondition(ConditionOperator.EQ, value=True)
                },
            )
        )
        decision = engine.has_permission(user, "test.read")
        assert decision.rbac_allowed is True
        assert decision.allowed is False

    def test_rbac_or_abac_one_suffices(self, monkeypatch):
        rbac, abac_engine, engine = self._setup(
            CombinationStrategy.RBAC_OR_ABAC, monkeypatch
        )
        user = User.objects.create_user("hybrid_or", password="pass12345")
        abac_engine.register_policy(
            ABACPolicy(
                name="allow_authenticated",
                effect="allow",
                subject_conditions={
                    "authenticated": MatchCondition(ConditionOperator.EQ, value=True)
                },
            )
        )
        decision = engine.has_permission(user, "test.read")
        assert decision.rbac_allowed is False
        assert decision.abac_allowed is True
        assert decision.allowed is True

    def test_abac_override_ignores_rbac(self, monkeypatch):
        rbac, abac_engine, engine = self._setup(
            CombinationStrategy.ABAC_OVERRIDE, monkeypatch
        )
        user = User.objects.create_user("hybrid_override", password="pass12345")
        rbac.register_role(
            RoleDefinition(
                name="override_role",
                role_type=RoleType.BUSINESS,
                description="Override role",
                permissions=["test.read"],
            )
        )
        rbac.assign_role_to_user(user, "override_role")
        abac_engine.register_policy(
            ABACPolicy(
                name="deny_override",
                effect="deny",
                subject_conditions={
                    "authenticated": MatchCondition(ConditionOperator.EQ, value=True)
                },
            )
        )
        decision = engine.has_permission(user, "test.read")
        assert decision.rbac_allowed is True
        assert decision.abac_allowed is False
        assert decision.allowed is False

    def test_no_active_abac_policy_falls_back_to_rbac(self, monkeypatch):
        rbac, _abac_engine, engine = self._setup(
            CombinationStrategy.RBAC_THEN_ABAC, monkeypatch
        )
        user = User.objects.create_user("hybrid_no_policy", password="pass12345")
        rbac.register_role(
            RoleDefinition(
                name="rbac_only_role",
                role_type=RoleType.BUSINESS,
                description="RBAC role",
                permissions=["test.read"],
            )
        )
        rbac.assign_role_to_user(user, "rbac_only_role")

        decision = engine.has_permission(user, "test.read")
        assert decision.rbac_allowed is True
        assert decision.abac_allowed is None
        assert decision.allowed is True

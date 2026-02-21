"""Unit tests for ABAC engine and manager behavior."""

import pytest

from rail_django.security.abac import (
    ABACContext,
    ABACEngine,
    ABACPolicy,
    AttributeSet,
    ConditionOperator,
    MatchCondition,
)

pytestmark = pytest.mark.unit


class TestABACConditions:
    def test_eq_operator_match(self):
        engine = ABACEngine()
        engine.register_policy(
            ABACPolicy(
                name="eq_allow",
                effect="allow",
                subject_conditions={
                    "role": MatchCondition(ConditionOperator.EQ, value="admin")
                },
            )
        )
        context = ABACContext(
            subject=AttributeSet(static_attributes={"role": "admin"})
        )
        decision = engine.evaluate(context)
        assert decision is not None
        assert decision.allowed is True

    def test_in_operator_match(self):
        engine = ABACEngine()
        engine.register_policy(
            ABACPolicy(
                name="in_allow",
                effect="allow",
                action_conditions={
                    "type": MatchCondition(
                        ConditionOperator.IN, value=["query", "mutation"]
                    )
                },
            )
        )
        context = ABACContext(action=AttributeSet(static_attributes={"type": "query"}))
        decision = engine.evaluate(context)
        assert decision is not None
        assert decision.allowed is True

    def test_between_operator_match(self):
        engine = ABACEngine()
        engine.register_policy(
            ABACPolicy(
                name="between_allow",
                effect="allow",
                environment_conditions={
                    "hour": MatchCondition(ConditionOperator.BETWEEN, value=[8, 18])
                },
            )
        )
        context = ABACContext(environment=AttributeSet(static_attributes={"hour": 12}))
        decision = engine.evaluate(context)
        assert decision is not None
        assert decision.allowed is True

    def test_dynamic_target_resolution(self):
        engine = ABACEngine()
        engine.register_policy(
            ABACPolicy(
                name="department_match",
                effect="allow",
                subject_conditions={
                    "department": MatchCondition(
                        ConditionOperator.EQ, target="resource.department"
                    )
                },
            )
        )
        context = ABACContext(
            subject=AttributeSet(static_attributes={"department": "engineering"}),
            resource=AttributeSet(static_attributes={"department": "engineering"}),
        )
        decision = engine.evaluate(context)
        assert decision is not None
        assert decision.allowed is True


class TestABACPolicySelection:
    def test_deny_wins_on_same_priority(self):
        engine = ABACEngine()
        engine.register_policy(
            ABACPolicy(
                name="allow_all",
                effect="allow",
                priority=10,
                subject_conditions={
                    "authenticated": MatchCondition(ConditionOperator.EQ, value=True)
                },
            )
        )
        engine.register_policy(
            ABACPolicy(
                name="deny_all",
                effect="deny",
                priority=10,
                subject_conditions={
                    "authenticated": MatchCondition(ConditionOperator.EQ, value=True)
                },
            )
        )
        context = ABACContext(
            subject=AttributeSet(static_attributes={"authenticated": True})
        )
        decision = engine.evaluate(context)
        assert decision is not None
        assert decision.allowed is False
        assert decision.matched_policy is not None
        assert decision.matched_policy.name == "deny_all"

    def test_any_combination_mode(self):
        engine = ABACEngine()
        engine.register_policy(
            ABACPolicy(
                name="any_policy",
                effect="allow",
                combine_conditions="any",
                subject_conditions={
                    "role": MatchCondition(ConditionOperator.EQ, value="admin")
                },
                environment_conditions={
                    "is_business_hours": MatchCondition(
                        ConditionOperator.EQ, value=True
                    )
                },
            )
        )
        context = ABACContext(
            subject=AttributeSet(static_attributes={"role": "admin"}),
            environment=AttributeSet(static_attributes={"is_business_hours": False}),
        )
        decision = engine.evaluate(context)
        assert decision is not None
        assert decision.allowed is True


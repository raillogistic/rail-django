"""
ABAC evaluation engine.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from .types import ABACContext, ABACDecision, ABACPolicy, ConditionOperator, MatchCondition

logger = logging.getLogger(__name__)


class ABACEngine:
    """Evaluate ABAC policies against an ABAC context."""

    def __init__(self) -> None:
        self._policies: list[ABACPolicy] = []
        self._version = 0

    def register_policy(self, policy: ABACPolicy) -> None:
        """Register or replace one policy by name."""
        replaced = False
        for index, existing in enumerate(self._policies):
            if existing.name == policy.name:
                self._policies[index] = policy
                replaced = True
                break
        if not replaced:
            self._policies.append(policy)
        self._version += 1

    def register_policies(self, policies: list[ABACPolicy]) -> None:
        for policy in policies:
            self.register_policy(policy)

    def remove_policy(self, name: str) -> bool:
        before = len(self._policies)
        self._policies = [policy for policy in self._policies if policy.name != name]
        if len(self._policies) < before:
            self._version += 1
            return True
        return False

    def clear_policies(self) -> None:
        self._policies = []
        self._version += 1

    def list_policies(self) -> list[ABACPolicy]:
        return list(self._policies)

    def get_version(self) -> int:
        return int(self._version)

    def evaluate(self, context: ABACContext) -> Optional[ABACDecision]:
        start = time.monotonic()
        active = [policy for policy in self._policies if policy.enabled]
        if not active:
            return None

        matches: list[tuple[ABACPolicy, dict[str, bool]]] = []
        for policy in active:
            matched, condition_detail = self._policy_matches(policy, context)
            if matched:
                matches.append((policy, condition_detail))

        elapsed_ms = (time.monotonic() - start) * 1000
        if not matches:
            return ABACDecision(
                allowed=False,
                reason="no_matching_policy",
                evaluated_policies=len(active),
                evaluation_time_ms=elapsed_ms,
            )

        matches.sort(
            key=lambda item: (-int(item[0].priority), 0 if item[0].effect == "deny" else 1)
        )
        selected_policy, matched_conditions = matches[0]

        return ABACDecision(
            allowed=selected_policy.effect == "allow",
            matched_policy=selected_policy,
            reason=f"policy:{selected_policy.name}",
            evaluated_policies=len(active),
            matched_conditions=matched_conditions,
            evaluation_time_ms=elapsed_ms,
        )

    def _policy_matches(
        self, policy: ABACPolicy, context: ABACContext
    ) -> tuple[bool, dict[str, bool]]:
        groups = [
            ("subject", policy.subject_conditions, context.subject),
            ("resource", policy.resource_conditions, context.resource),
            ("environment", policy.environment_conditions, context.environment),
            ("action", policy.action_conditions, context.action),
        ]
        matches: list[bool] = []
        detail: dict[str, bool] = {}

        for category, conditions, attr_set in groups:
            if not conditions:
                continue
            for attr_name, condition in conditions.items():
                actual = attr_set.get(attr_name)
                expected = (
                    context.resolve_reference(condition.target)
                    if condition.target
                    else condition.value
                )
                result = self._evaluate_condition(condition, actual, expected)
                detail[f"{category}.{attr_name}"] = result
                matches.append(result)

        if not matches:
            return True, detail

        mode = (policy.combine_conditions or "all").lower()
        return (any(matches) if mode == "any" else all(matches)), detail

    def _evaluate_condition(
        self, condition: MatchCondition, actual: Any, expected: Any
    ) -> bool:
        try:
            result = self._apply_operator(condition.operator, actual, expected, condition)
        except Exception:
            result = False
        return (not result) if condition.negate else bool(result)

    def _apply_operator(
        self,
        operator: ConditionOperator,
        actual: Any,
        expected: Any,
        condition: MatchCondition,
    ) -> bool:
        if isinstance(operator, str):
            try:
                operator = ConditionOperator(operator.lower())
            except Exception:
                operator = ConditionOperator.EQ
        if operator == ConditionOperator.EQ:
            return actual == expected
        if operator == ConditionOperator.NEQ:
            return actual != expected
        if operator == ConditionOperator.IN:
            return actual in (expected or [])
        if operator == ConditionOperator.NOT_IN:
            return actual not in (expected or [])
        if operator == ConditionOperator.CONTAINS:
            return expected in actual if actual is not None else False
        if operator == ConditionOperator.STARTS_WITH:
            return str(actual or "").startswith(str(expected or ""))
        if operator == ConditionOperator.GT:
            return actual is not None and expected is not None and actual > expected
        if operator == ConditionOperator.GTE:
            return actual is not None and expected is not None and actual >= expected
        if operator == ConditionOperator.LT:
            return actual is not None and expected is not None and actual < expected
        if operator == ConditionOperator.LTE:
            return actual is not None and expected is not None and actual <= expected
        if operator == ConditionOperator.BETWEEN:
            if not isinstance(expected, (list, tuple)) or len(expected) != 2:
                return False
            return actual is not None and expected[0] <= actual <= expected[1]
        if operator == ConditionOperator.MATCHES:
            pattern = str(expected or "")
            return bool(re.match(pattern, str(actual or "")))
        if operator == ConditionOperator.EXISTS:
            return actual is not None
        if operator == ConditionOperator.IS_SUBSET:
            return set(actual or []).issubset(set(expected or []))
        if operator == ConditionOperator.INTERSECTS:
            return bool(set(actual or []).intersection(set(expected or [])))
        if operator == ConditionOperator.CUSTOM:
            if not callable(condition.custom_func):
                return False
            return bool(condition.custom_func(actual, expected))
        return False


abac_engine = ABACEngine()

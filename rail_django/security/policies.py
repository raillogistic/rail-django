"""
Access policy engine for explicit allow/deny decisions.

Policies are evaluated by priority (higher wins). When priorities tie, deny wins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Set, Type

from django.db import models

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class PolicyEffect(Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class PolicyContext:
    user: "AbstractUser"
    permission: Optional[str] = None
    model_class: Optional[Type[models.Model]] = None
    field_name: Optional[str] = None
    operation: Optional[str] = None
    object_instance: Optional[models.Model] = None
    object_id: Optional[str] = None
    classifications: Optional[Set[str]] = None
    additional_context: Optional[Dict[str, Any]] = None
    request: Optional[Any] = None


@dataclass
class AccessPolicy:
    name: str
    effect: PolicyEffect
    priority: int = 0
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    models: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    operations: List[str] = field(default_factory=list)
    classifications: List[str] = field(default_factory=list)
    condition: Optional[Callable[[PolicyContext], bool]] = None
    access_level: Optional[Any] = None
    visibility: Optional[Any] = None
    mask_value: Any = None
    reason: Optional[str] = None


@dataclass
class PolicyDecision:
    allowed: bool
    effect: PolicyEffect
    policy: AccessPolicy
    reason: Optional[str] = None


@dataclass
class PolicyExplanation:
    decision: Optional[PolicyDecision]
    matches: List[AccessPolicy] = field(default_factory=list)


class PolicyManager:
    def __init__(self) -> None:
        self._policies: List[AccessPolicy] = []
        self._version = 0

    def register_policy(self, policy: AccessPolicy) -> None:
        self._policies.append(policy)
        self._version += 1

    def register_policies(self, policies: Sequence[AccessPolicy]) -> None:
        for policy in policies:
            self.register_policy(policy)

    def register_classification_bundle(
        self, tag: str, policies: Sequence[AccessPolicy]
    ) -> None:
        for policy in policies:
            if not policy.classifications:
                policy.classifications = [tag]
            self.register_policy(policy)

    def list_policies(self) -> List[AccessPolicy]:
        return list(self._policies)

    def clear_policies(self) -> None:
        self._policies = []
        self._version += 1

    def get_version(self) -> int:
        return self._version

    def evaluate(self, context: PolicyContext) -> Optional[PolicyDecision]:
        matches = [policy for policy in self._policies if self._policy_applies(policy, context)]
        if not matches:
            return None

        matches.sort(
            key=lambda policy: (
                -int(policy.priority),
                0 if policy.effect == PolicyEffect.DENY else 1,
            )
        )
        selected = matches[0]
        return PolicyDecision(
            allowed=selected.effect == PolicyEffect.ALLOW,
            effect=selected.effect,
            policy=selected,
            reason=selected.reason,
        )

    def explain(self, context: PolicyContext) -> PolicyExplanation:
        matches = [policy for policy in self._policies if self._policy_applies(policy, context)]
        decision = None
        if matches:
            matches.sort(
                key=lambda policy: (
                    -int(policy.priority),
                    0 if policy.effect == PolicyEffect.DENY else 1,
                )
            )
            selected = matches[0]
            decision = PolicyDecision(
                allowed=selected.effect == PolicyEffect.ALLOW,
                effect=selected.effect,
                policy=selected,
                reason=selected.reason,
            )
        return PolicyExplanation(decision=decision, matches=matches)

    def _policy_applies(self, policy: AccessPolicy, context: PolicyContext) -> bool:
        if policy.roles:
            user_roles = self._get_user_roles(context)
            if not user_roles.intersection(policy.roles):
                return False

        if policy.permissions:
            if not context.permission:
                return False
            if not any(self._match_pattern(context.permission, perm) for perm in policy.permissions):
                return False

        if policy.models:
            model_tokens = self._get_model_tokens(context)
            if not any(self._match_pattern(token, pattern) for pattern in policy.models for token in model_tokens):
                return False

        if policy.fields:
            if not context.field_name:
                return False
            if not any(self._match_pattern(context.field_name, pattern) for pattern in policy.fields):
                return False

        if policy.operations:
            if not context.operation:
                return False
            if not any(self._match_pattern(context.operation, pattern) for pattern in policy.operations):
                return False

        if policy.classifications:
            tags = context.classifications or set()
            if not tags.intersection(policy.classifications):
                return False

        if policy.condition:
            try:
                if not policy.condition(context):
                    return False
            except Exception as exc:
                logger.warning("Policy condition failed (%s): %s", policy.name, exc)
                return False

        return True

    def _get_user_roles(self, context: PolicyContext) -> Set[str]:
        try:
            from .rbac import role_manager

            return set(role_manager.get_user_roles(context.user))
        except Exception:
            return set()

    def _get_model_tokens(self, context: PolicyContext) -> List[str]:
        model = context.model_class
        if model is None and context.object_instance is not None:
            model = context.object_instance.__class__
        tokens: List[str] = ["*"]
        if model is not None:
            tokens.append(model.__name__)
            tokens.append(model._meta.label_lower)
        return tokens

    @staticmethod
    def _match_pattern(value: str, pattern: str) -> bool:
        if pattern == "*" or pattern == value:
            return True
        if "*" in pattern:
            fragment = pattern.replace("*", "")
            return fragment in value
        return False


policy_manager = PolicyManager()

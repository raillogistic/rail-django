"""
ABAC manager that builds evaluation context from providers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from django.db import models

from rail_django.config_proxy import get_setting

from .attributes import (
    ActionAttributeProvider,
    BaseAttributeProvider,
    EnvironmentAttributeProvider,
    ResourceAttributeProvider,
    SubjectAttributeProvider,
)
from .engine import ABACEngine, abac_engine
from .types import (
    ABACContext,
    ABACDecision,
    ABACPolicy,
    ConditionOperator,
    MatchCondition,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class ABACManager:
    """Central manager for ABAC checks."""

    def __init__(self, engine: Optional[ABACEngine] = None) -> None:
        self._engine = engine or abac_engine
        self._subject_provider = SubjectAttributeProvider()
        self._resource_provider = ResourceAttributeProvider()
        self._environment_provider = EnvironmentAttributeProvider()
        self._action_provider = ActionAttributeProvider()
        self._custom_providers: dict[str, BaseAttributeProvider] = {}

    def register_provider(self, name: str, provider: BaseAttributeProvider) -> None:
        self._custom_providers[name] = provider

    def register_policy(self, policy: ABACPolicy) -> None:
        self._engine.register_policy(policy)

    def register_graphql_meta_policies(
        self, model_label: str, policy_defs: list[dict[str, Any]]
    ) -> None:
        if not model_label or not policy_defs:
            return
        prefix = model_label.replace(".", "_")
        for raw in policy_defs:
            policy = self._coerce_policy(raw, prefix)
            if policy is not None:
                self._engine.register_policy(policy)

    def build_context(
        self,
        user: "AbstractUser" = None,
        instance: Optional[models.Model] = None,
        model_class: Optional[type[models.Model]] = None,
        request: "HttpRequest" = None,
        operation: Optional[str] = None,
        permission: Optional[str] = None,
        info: Any = None,
        **extra: Any,
    ) -> ABACContext:
        context = ABACContext(
            subject=self._subject_provider.collect(user=user),
            resource=self._resource_provider.collect(
                instance=instance, model_class=model_class
            ),
            environment=self._environment_provider.collect(request=request),
            action=self._action_provider.collect(
                operation=operation,
                permission=permission,
                info=info,
            ),
        )

        for name, provider in self._custom_providers.items():
            try:
                data = provider.collect(
                    user=user,
                    instance=instance,
                    model_class=model_class,
                    request=request,
                    operation=operation,
                    permission=permission,
                    info=info,
                    **extra,
                )
            except Exception as exc:
                logger.warning("ABAC custom provider '%s' failed: %s", name, exc)
                continue
            if data is None:
                continue
            for key, value in data.resolve_all().items():
                context.environment.static_attributes[f"{name}.{key}"] = value

        return context

    def check_access(self, **kwargs: Any) -> Optional[ABACDecision]:
        schema_name = kwargs.get("schema_name")
        context = self.build_context(**kwargs)
        decision = self._engine.evaluate(context)
        if decision is None:
            return None
        if bool(
            get_setting(
                "security_settings.abac_audit_decisions",
                False,
                schema_name=schema_name,
            )
        ):
            logger.info(
                "ABAC decision allowed=%s reason=%s policy=%s",
                decision.allowed,
                decision.reason,
                getattr(decision.matched_policy, "name", None),
            )
        return decision

    def check_inline_access(
        self,
        *,
        subject_conditions: Optional[dict[str, Any]] = None,
        resource_conditions: Optional[dict[str, Any]] = None,
        environment_conditions: Optional[dict[str, Any]] = None,
        action_conditions: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ABACDecision:
        policy = ABACPolicy(
            name="__inline_policy__",
            effect="allow",
            subject_conditions=self._coerce_conditions(subject_conditions or {}),
            resource_conditions=self._coerce_conditions(resource_conditions or {}),
            environment_conditions=self._coerce_conditions(
                environment_conditions or {}
            ),
            action_conditions=self._coerce_conditions(action_conditions or {}),
        )
        temp_engine = ABACEngine()
        temp_engine.register_policy(policy)
        context = self.build_context(**kwargs)
        decision = temp_engine.evaluate(context)
        if decision is None:
            return ABACDecision(allowed=False, reason="inline_policy_missing")
        return decision

    def _coerce_policy(self, raw: dict[str, Any], namespace: str) -> Optional[ABACPolicy]:
        name = str(raw.get("name") or "").strip()
        if not name:
            return None
        namespaced_name = f"{namespace}:{name}"
        return ABACPolicy(
            name=namespaced_name,
            description=str(raw.get("description") or ""),
            effect=str(raw.get("effect") or "allow").lower(),
            priority=int(raw.get("priority") or 0),
            subject_conditions=self._coerce_conditions(
                raw.get("subject_conditions") or {}
            ),
            resource_conditions=self._coerce_conditions(
                raw.get("resource_conditions") or {}
            ),
            environment_conditions=self._coerce_conditions(
                raw.get("environment_conditions") or {}
            ),
            action_conditions=self._coerce_conditions(raw.get("action_conditions") or {}),
            combine_conditions=str(raw.get("combine_conditions") or "all"),
            enabled=bool(raw.get("enabled", True)),
            tags=[str(tag) for tag in raw.get("tags", []) if tag is not None],
        )

    def _coerce_conditions(
        self, conditions: dict[str, Any]
    ) -> dict[str, MatchCondition]:
        coerced: dict[str, MatchCondition] = {}
        for attr_name, value in conditions.items():
            if isinstance(value, MatchCondition):
                coerced[attr_name] = value
                continue
            if not isinstance(value, dict):
                coerced[attr_name] = MatchCondition(
                    operator=ConditionOperator.EQ,
                    value=value,
                )
                continue
            operator_raw = str(value.get("operator") or "eq").lower()
            try:
                operator = ConditionOperator(operator_raw)
            except Exception:
                operator = ConditionOperator.EQ
            custom_func = value.get("custom_func")
            coerced[attr_name] = MatchCondition(
                operator=operator,
                value=value.get("value"),
                target=value.get("target"),
                custom_func=custom_func if callable(custom_func) else None,
                negate=bool(value.get("negate", False)),
            )
        return coerced


abac_manager = ABACManager()

# ABAC Integration Plan — Hybrid RBAC + ABAC Permission System

> **Target Module:** `rail_django.security.abac`
> **Compatibility:** Works in synergy with `rail_django.security.rbac` and `rail_django.security.policies`

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Hybrid Permission Engine                              │
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │   RBAC        │    │   ABAC        │    │   Policy Engine          │  │
│  │  (existing)   │    │  (new)        │    │   (existing)             │  │
│  │              │    │              │    │                          │  │
│  │ RoleManager  │    │ ABACEngine   │    │ PolicyManager            │  │
│  │ Roles/Perms  │    │ Attributes   │    │ AccessPolicy             │  │
│  │ Hierarchy    │    │ Conditions   │    │ Conditions               │  │
│  └──────┬───────┘    └──────┬───────┘    └────────────┬─────────────┘  │
│         │                   │                         │                 │
│         └───────────────────┼─────────────────────────┘                 │
│                             ▼                                           │
│              ┌──────────────────────────┐                              │
│              │  HybridPermissionEngine   │                              │
│              │  • Configurable strategy  │                              │
│              │  • Evaluation chain       │                              │
│              │  • Unified cache          │                              │
│              │  • Centralized audit      │                              │
│              └──────────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Hybrid Evaluation Flow

```
Request → Middleware → HybridPermissionEngine
                           │
                           ├─ 1. Policy Engine (High priority, deny-first)
                           │     └─ If explicit decision → return
                           │
                           ├─ 2. RBAC Check
                           │     └─ Verify roles + effective permissions
                           │
                           ├─ 3. ABAC Check
                           │     └─ Evaluate subject/resource/env/action attributes
                           │
                           └─ 4. Combine according to configured strategy
                                 └─ RBAC_AND_ABAC | RBAC_OR_ABAC | ABAC_OVERRIDE
```

---

## 2. Impacted Existing Components

| File                                       | Modification                          |
| ------------------------------------------ | ------------------------------------- |
| `security/__init__.py`                     | Add ABAC + Hybrid exports             |
| `security/config.py`                       | Add `get_abac_config()`               |
| `security/rbac/evaluation.py`              | Hook for optional hybrid call         |
| `security/policies.py`                     | Add `AttributeCondition` helper       |
| `generators/pipeline/steps/permissions.py` | Add `ABACPermissionStep`              |
| `extensions/permissions/manager.py`        | Integrate ABAC checkers               |
| `core/meta/security_loader.py`             | Load ABAC policies from `GraphQLMeta` |

---

## 3. New Files — `security/abac/` Package Structure

### 3.1 `security/abac/__init__.py`

```python
"""
Attribute-Based Access Control (ABAC) for Django GraphQL.

This package provides a comprehensive ABAC system:
- Definition of attribute-based policies
- Extensible attribute providers (subject, resource, environment, action)
- Condition evaluation engine
- Hybrid integration with the existing RBAC system

Example:
    >>> from rail_django.security.abac import abac_engine, ABACPolicy
    >>>
    >>> policy = ABACPolicy(
    ...     name="edit_own_department",
    ...     description="Authorize modification within own department",
    ...     effect=PolicyEffect.ALLOW,
    ...     subject_conditions={"department": MatchCondition("eq", target="resource.department")},
    ...     action_conditions={"type": MatchCondition("in", ["update", "create"])},
    ... )
    >>> abac_engine.register_policy(policy)
"""

from .types import (
    ABACPolicy, ABACDecision, ABACContext,
    AttributeSet, MatchCondition, ConditionOperator,
)
from .engine import ABACEngine, abac_engine
from .attributes import (
    BaseAttributeProvider, SubjectAttributeProvider,
    ResourceAttributeProvider, EnvironmentAttributeProvider,
    ActionAttributeProvider,
)
from .decorators import require_attributes
from .manager import ABACManager, abac_manager

__all__ = [
    "ABACPolicy", "ABACDecision", "ABACContext",
    "AttributeSet", "MatchCondition", "ConditionOperator",
    "ABACEngine", "abac_engine",
    "BaseAttributeProvider", "SubjectAttributeProvider",
    "ResourceAttributeProvider", "EnvironmentAttributeProvider",
    "ActionAttributeProvider",
    "require_attributes",
    "ABACManager", "abac_manager",
]
```

### 3.2 `security/abac/types.py`

```python
"""
Types and data structures for the ABAC system.

Attributes:
    ConditionOperator: Comparison operators Enum
    MatchCondition: Match condition for an attribute
    AttributeSet: Set of typed key-value attributes
    ABACPolicy: ABAC policy definition
    ABACContext: ABAC evaluation context
    ABACDecision: ABAC policy evaluation result
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Union
from django.db import models


class ConditionOperator(Enum):
    """Comparison operators for ABAC conditions."""
    EQ = "eq"                    # Strict equality
    NEQ = "neq"                  # Different from
    IN = "in"                    # Value in a list
    NOT_IN = "not_in"            # Value not in a list
    CONTAINS = "contains"        # Contains (string or list)
    STARTS_WITH = "starts_with"  # Starts with
    GT = "gt"                    # Greater than
    GTE = "gte"                  # Greater than or equal
    LT = "lt"                    # Less than
    LTE = "lte"                  # Less than or equal
    BETWEEN = "between"          # Between two values
    MATCHES = "matches"          # Regular expression
    EXISTS = "exists"            # Attribute exists
    IS_SUBSET = "is_subset"      # Subset
    INTERSECTS = "intersects"    # Non-empty intersection
    CUSTOM = "custom"            # Custom function


@dataclass
class MatchCondition:
    """
    Match condition for an attribute.

    Attributes:
        operator: Comparison operator
        value: Reference value (static)
        target: Dynamic reference (e.g., "resource.department", "subject.org_id")
        custom_func: Custom function for CUSTOM operator
        negate: Negate the result
    """
    operator: ConditionOperator
    value: Any = None
    target: Optional[str] = None
    custom_func: Optional[Callable[..., bool]] = None
    negate: bool = False


@dataclass
class AttributeSet:
    """
    Set of attributes for an evaluation context.

    Attributes:
        static_attributes: Statically defined attributes
        dynamic_resolvers: Functions to resolve attributes dynamically
    """
    static_attributes: dict[str, Any] = field(default_factory=dict)
    dynamic_resolvers: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.static_attributes:
            return self.static_attributes[key]
        if key in self.dynamic_resolvers:
            return self.dynamic_resolvers[key]()
        return default

    def resolve_all(self) -> dict[str, Any]:
        result = dict(self.static_attributes)
        for key, resolver in self.dynamic_resolvers.items():
            if key not in result:
                try:
                    result[key] = resolver()
                except Exception:
                    result[key] = None
        return result


@dataclass
class ABACContext:
    """
    Complete context for ABAC evaluation.

    Attributes:
        subject: Subject attributes (the user)
        resource: Resource attributes (the object)
        environment: Environment attributes (time, IP, etc.)
        action: Action attributes (type, concerned fields)
    """
    subject: AttributeSet = field(default_factory=AttributeSet)
    resource: AttributeSet = field(default_factory=AttributeSet)
    environment: AttributeSet = field(default_factory=AttributeSet)
    action: AttributeSet = field(default_factory=AttributeSet)

    def resolve_reference(self, ref: str) -> Any:
        """Resolve a dynamic reference (e.g., 'resource.department')."""
        parts = ref.split(".", 1)
        if len(parts) != 2:
            return None
        category, key = parts
        attr_set = getattr(self, category, None)
        if attr_set is None:
            return None
        return attr_set.get(key)


@dataclass
class ABACPolicy:
    """
    ABAC policy definition.

    Attributes:
        name: Unique policy name
        description: Description in English
        effect: Effect (ALLOW or DENY)
        priority: Priority (higher = evaluated first)
        subject_conditions: Conditions on subject attributes
        resource_conditions: Conditions on resource attributes
        environment_conditions: Conditions on environment attributes
        action_conditions: Conditions on action attributes
        combine_conditions: Combination mode ("all" = AND, "any" = OR)
        enabled: Whether the policy is active
        tags: Tags for grouping/filtering
    """
    name: str
    description: str = ""
    effect: str = "allow"  # "allow" or "deny"
    priority: int = 0
    subject_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    resource_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    environment_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    action_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    combine_conditions: str = "all"  # "all" (AND) or "any" (OR)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class ABACDecision:
    """
    ABAC policy evaluation result.

    Attributes:
        allowed: Final decision
        matched_policy: Policy that produced the decision
        reason: Textual reason
        evaluated_policies: Number of evaluated policies
        matched_conditions: Detail of satisfied conditions
        evaluation_time_ms: Evaluation time in milliseconds
    """
    allowed: bool
    matched_policy: Optional[ABACPolicy] = None
    reason: Optional[str] = None
    evaluated_policies: int = 0
    matched_conditions: dict[str, bool] = field(default_factory=dict)
    evaluation_time_ms: float = 0.0
```

### 3.3 `security/abac/attributes.py`

```python
"""
Attribute providers for the ABAC system.

Each provider extracts attributes from a specific category
(subject, resource, environment, action) from the request context.

Classes:
    BaseAttributeProvider: Abstract base class
    SubjectAttributeProvider: User attributes (roles, department, etc.)
    ResourceAttributeProvider: Django resource attributes
    EnvironmentAttributeProvider: Environment attributes (time, IP, etc.)
    ActionAttributeProvider: GraphQL action attributes
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from django.db import models

from .types import AttributeSet

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class BaseAttributeProvider(ABC):
    """Base class for attribute providers."""

    @abstractmethod
    def collect(self, **kwargs) -> AttributeSet:
        """Collect attributes from context."""
        ...


class SubjectAttributeProvider(BaseAttributeProvider):
    """
    Subject (user) attribute provider.

    Extracted attributes:
        - user_id, username, email
        - is_staff, is_superuser, is_active
        - roles (from Django groups)
        - department, organization (from profile if available)
        - date_joined, last_login
        - effective Django permissions
    """

    def collect(self, user: "AbstractUser" = None, **kwargs) -> AttributeSet:
        if user is None or not getattr(user, "is_authenticated", False):
            return AttributeSet(static_attributes={"authenticated": False})

        attrs = {
            "authenticated": True,
            "user_id": user.pk,
            "username": user.username,
            "email": getattr(user, "email", ""),
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "is_active": user.is_active,
            "roles": list(user.groups.values_list("name", flat=True)),
            "date_joined": user.date_joined,
            "last_login": user.last_login,
        }

        # Optional profile attributes
        profile = getattr(user, "profile", None)
        if profile:
            for attr in ("department", "organization", "team", "location", "level"):
                if hasattr(profile, attr):
                    attrs[attr] = getattr(profile, attr)

        return AttributeSet(
            static_attributes=attrs,
            dynamic_resolvers={
                "permissions": lambda: set(user.get_all_permissions()),
            },
        )


class ResourceAttributeProvider(BaseAttributeProvider):
    """
    Resource (Django object) attribute provider.

    Extracted attributes:
        - model_name, app_label, model_label
        - All instance fields (except M2M relations)
        - owner_id (if owner/created_by field exists)
        - classification/sensitivity (from GraphQLMeta if available)
    """

    def collect(
        self,
        instance: Optional[models.Model] = None,
        model_class: Optional[type[models.Model]] = None,
        **kwargs,
    ) -> AttributeSet:
        model = model_class or (instance.__class__ if instance else None)
        if model is None:
            return AttributeSet()

        attrs = {
            "model_name": model._meta.model_name,
            "app_label": model._meta.app_label,
            "model_label": model._meta.label_lower,
        }

        if instance is not None:
            for f in model._meta.get_fields():
                if hasattr(f, "attname") and hasattr(instance, f.attname):
                    attrs[f.name] = getattr(instance, f.attname)

            for attr in ("owner", "created_by", "user"):
                if hasattr(instance, f"{attr}_id"):
                    attrs["owner_id"] = getattr(instance, f"{attr}_id")
                    break

        graphql_meta = getattr(model, "GraphQLMeta", None)
        if graphql_meta:
            attrs["classification"] = getattr(graphql_meta, "classification", None)
            attrs["sensitivity"] = getattr(graphql_meta, "sensitivity", None)

        return AttributeSet(static_attributes=attrs)


class EnvironmentAttributeProvider(BaseAttributeProvider):
    """
    Environment attribute provider.

    Extracted attributes:
        - current_time, current_date, day_of_week, hour
        - client_ip, user_agent
        - is_secure (HTTPS)
        - request_method, request_path
    """

    def collect(self, request: "HttpRequest" = None, **kwargs) -> AttributeSet:
        now = datetime.now(timezone.utc)
        attrs = {
            "current_time": now,
            "current_date": now.date(),
            "day_of_week": now.strftime("%A").lower(),
            "hour": now.hour,
            "is_business_hours": 8 <= now.hour <= 18,
        }

        if request is not None:
            attrs["client_ip"] = self._get_client_ip(request)
            attrs["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:500]
            attrs["is_secure"] = request.is_secure()
            attrs["request_method"] = request.method
            attrs["request_path"] = request.path

        return AttributeSet(static_attributes=attrs)

    @staticmethod
    def _get_client_ip(request: "HttpRequest") -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("HTTP_X_REAL_IP", request.META.get("REMOTE_ADDR", "unknown"))


class ActionAttributeProvider(BaseAttributeProvider):
    """
    GraphQL action attribute provider.

    Extracted attributes:
        - type (query, mutation, subscription)
        - operation_name
        - fields_requested
        - is_introspection
    """

    def collect(
        self,
        operation: Optional[str] = None,
        operation_name: Optional[str] = None,
        info: Any = None,
        **kwargs,
    ) -> AttributeSet:
        attrs = {
            "type": operation or "unknown",
            "operation_name": operation_name or "",
        }

        if info is not None:
            try:
                op = info.operation
                if op:
                    attrs["type"] = op.operation.value
                    attrs["operation_name"] = getattr(op, "name", {})
                    if hasattr(op.name, "value"):
                        attrs["operation_name"] = op.name.value
            except Exception:
                pass

        return AttributeSet(static_attributes=attrs)
```

### 3.4 `security/abac/engine.py`

```python
"""
ABAC evaluation engine.

This module contains the main engine that evaluates ABAC policies
by resolving conditions on context attributes.

Classes:
    ABACEngine: ABAC policy evaluation engine
    abac_engine: Global singleton instance
"""

import logging
import time
from typing import Optional

from .types import (
    ABACContext, ABACDecision, ABACPolicy,
    ConditionOperator, MatchCondition,
)

logger = logging.getLogger(__name__)


class ABACEngine:
    """
    ABAC policy evaluation engine.

    Evaluates registered policies against an attribute context.
    Policies are sorted by priority (desc), deny-first in case of equality.
    """

    def __init__(self):
        self._policies: list[ABACPolicy] = []
        self._version: int = 0

    def register_policy(self, policy: ABACPolicy) -> None:
        """Register an ABAC policy."""
        self._policies.append(policy)
        self._version += 1

    def remove_policy(self, name: str) -> bool:
        """Remove a policy by name."""
        before = len(self._policies)
        self._policies = [p for p in self._policies if p.name != name]
        if len(self._policies) < before:
            self._version += 1
            return True
        return False

    def clear_policies(self) -> None:
        """Remove all policies."""
        self._policies.clear()
        self._version += 1

    def get_version(self) -> int:
        return self._version

    def evaluate(self, context: ABACContext) -> Optional[ABACDecision]:
        """Evaluate all active policies against the context."""
        start = time.monotonic()
        active = [p for p in self._policies if p.enabled]
        if not active:
            return None

        matches = []
        for policy in active:
            if self._policy_matches(policy, context):
                matches.append(policy)

        if not matches:
            return ABACDecision(
                allowed=False,
                reason="no_matching_policy",
                evaluated_policies=len(active),
                evaluation_time_ms=(time.monotonic() - start) * 1000,
            )

        # Sort: priority desc, deny first
        matches.sort(key=lambda p: (-p.priority, 0 if p.effect == "deny" else 1))
        selected = matches[0]

        return ABACDecision(
            allowed=selected.effect == "allow",
            matched_policy=selected,
            reason=f"policy_{selected.name}",
            evaluated_policies=len(active),
            evaluation_time_ms=(time.monotonic() - start) * 1000,
        )

    def _policy_matches(self, policy: ABACPolicy, context: ABACContext) -> bool:
        """Check if a policy matches the context."""
        condition_groups = [
            ("subject", policy.subject_conditions, context.subject),
            ("resource", policy.resource_conditions, context.resource),
            ("environment", policy.environment_conditions, context.environment),
            ("action", policy.action_conditions, context.action),
        ]

        results = []
        for category, conditions, attr_set in condition_groups:
            if not conditions:
                continue
            for attr_name, condition in conditions.items():
                actual = attr_set.get(attr_name)
                expected = condition.value
                if condition.target:
                    expected = context.resolve_reference(condition.target)
                matched = self._evaluate_condition(condition, actual, expected)
                results.append(matched)

        if not results:
            return True

        if policy.combine_conditions == "any":
            return any(results)
        return all(results)

    def _evaluate_condition(
        self, condition: MatchCondition, actual: any, expected: any
    ) -> bool:
        """Evaluate an individual condition."""
        op = condition.operator
        result = False

        if op == ConditionOperator.EQ:
            result = actual == expected
        elif op == ConditionOperator.NEQ:
            result = actual != expected
        elif op == ConditionOperator.IN:
            result = actual in (expected or [])
        elif op == ConditionOperator.NOT_IN:
            result = actual not in (expected or [])
        elif op == ConditionOperator.CONTAINS:
            result = expected in actual if actual else False
        elif op == ConditionOperator.GT:
            result = actual > expected if actual is not None else False
        elif op == ConditionOperator.GTE:
            result = actual >= expected if actual is not None else False
        elif op == ConditionOperator.LT:
            result = actual < expected if actual is not None else False
        elif op == ConditionOperator.LTE:
            result = actual <= expected if actual is not None else False
        elif op == ConditionOperator.BETWEEN:
            if isinstance(expected, (list, tuple)) and len(expected) == 2:
                result = expected[0] <= actual <= expected[1] if actual is not None else False
        elif op == ConditionOperator.EXISTS:
            result = actual is not None
        elif op == ConditionOperator.INTERSECTS:
            result = bool(set(actual or []) & set(expected or []))
        elif op == ConditionOperator.IS_SUBSET:
            result = set(actual or []).issubset(set(expected or []))
        elif op == ConditionOperator.CUSTOM:
            if condition.custom_func:
                result = condition.custom_func(actual, expected)
        elif op == ConditionOperator.STARTS_WITH:
            result = str(actual or "").startswith(str(expected or ""))
        elif op == ConditionOperator.MATCHES:
            import re
            result = bool(re.match(str(expected or ""), str(actual or "")))

        return not result if condition.negate else result


abac_engine = ABACEngine()
```

### 3.5 `security/abac/decorators.py`

```python
"""
ABAC decorators for GraphQL resolvers.

Provides require_attributes to check ABAC attributes
on GraphQL resolvers.
"""

from functools import wraps
from typing import Any, Callable, Optional
from graphql import GraphQLError


def require_attributes(
    subject_conditions: Optional[dict] = None,
    resource_conditions: Optional[dict] = None,
    environment_conditions: Optional[dict] = None,
    action_conditions: Optional[dict] = None,
    message: str = "Access denied by ABAC policy",
):
    """
    Decorator to check ABAC attributes on a GraphQL resolver.

    Args:
        subject_conditions: Conditions on subject attributes
        resource_conditions: Conditions on resource attributes
        environment_conditions: Conditions on environment attributes
        action_conditions: Conditions on action attributes
        message: Error message in case of refusal
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            from .manager import abac_manager

            info = None
            for arg in args:
                if hasattr(arg, "context"):
                    info = arg
                    break

            if not info or not hasattr(info.context, "user"):
                raise GraphQLError("User context not available")

            user = info.context.user
            if not user or not user.is_authenticated:
                raise GraphQLError("Authentication required")

            request = getattr(info, "context", None)
            decision = abac_manager.check_access(
                user=user,
                request=request,
                info=info,
            )

            if decision and not decision.allowed:
                raise GraphQLError(message)

            return func(*args, **kwargs)
        return wrapper
    return decorator
```

### 3.6 `security/abac/manager.py`

```python
"""
Centralized ABAC manager.

Orchestrates attribute providers and the evaluation engine.

Classes:
    ABACManager: Main manager
    abac_manager: Singleton instance
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from django.db import models

from .attributes import (
    ActionAttributeProvider, BaseAttributeProvider,
    EnvironmentAttributeProvider, ResourceAttributeProvider,
    SubjectAttributeProvider,
)
from .engine import ABACEngine, abac_engine
from .types import ABACContext, ABACDecision

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class ABACManager:
    """
    Centralized manager for the ABAC system.

    Coordinates attribute collection via providers
    and evaluation via the ABAC engine.
    """

    def __init__(self, engine: Optional[ABACEngine] = None):
        self._engine = engine or abac_engine
        self._subject_provider = SubjectAttributeProvider()
        self._resource_provider = ResourceAttributeProvider()
        self._environment_provider = EnvironmentAttributeProvider()
        self._action_provider = ActionAttributeProvider()
        self._custom_providers: dict[str, BaseAttributeProvider] = {}

    def register_provider(self, name: str, provider: BaseAttributeProvider) -> None:
        """Register a custom attribute provider."""
        self._custom_providers[name] = provider

    def build_context(
        self,
        user: "AbstractUser" = None,
        instance: Optional[models.Model] = None,
        model_class: Optional[type[models.Model]] = None,
        request: "HttpRequest" = None,
        operation: Optional[str] = None,
        info: Any = None,
        **extra,
    ) -> ABACContext:
        """Build a complete ABAC context from parameters."""
        return ABACContext(
            subject=self._subject_provider.collect(user=user),
            resource=self._resource_provider.collect(
                instance=instance, model_class=model_class,
            ),
            environment=self._environment_provider.collect(request=request),
            action=self._action_provider.collect(
                operation=operation, info=info,
            ),
        )

    def check_access(self, **kwargs) -> Optional[ABACDecision]:
        """Check ABAC access."""
        context = self.build_context(**kwargs)
        return self._engine.evaluate(context)


abac_manager = ABACManager()
```

---

## 4. Hybrid Engine — `security/hybrid/`

### 4.1 `security/hybrid/__init__.py`

```python
"""
Hybrid RBAC + ABAC permission engine.

Combines RBAC and ABAC decisions according to a configurable strategy.
"""

from .engine import HybridPermissionEngine, hybrid_engine
from .strategies import CombinationStrategy

__all__ = ["HybridPermissionEngine", "hybrid_engine", "CombinationStrategy"]
```

### 4.2 `security/hybrid/strategies.py`

```python
"""
Combination strategies for RBAC and ABAC decisions.
"""

from enum import Enum


class CombinationStrategy(Enum):
    """RBAC + ABAC combination strategies."""
    RBAC_AND_ABAC = "rbac_and_abac"       # Both must authorize
    RBAC_OR_ABAC = "rbac_or_abac"         # Either one is sufficient
    ABAC_OVERRIDE = "abac_override"       # ABAC takes precedence over RBAC
    RBAC_THEN_ABAC = "rbac_then_abac"     # RBAC first, ABAC if permitted
    MOST_RESTRICTIVE = "most_restrictive" # Most restrictive wins
```

### 4.3 `security/hybrid/engine.py`

```python
"""
Hybrid RBAC + ABAC evaluation engine.

Orchestrates sequential evaluation and combination
of decisions from both systems.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from django.db import models

from rail_django.config_proxy import get_setting
from ..abac.manager import ABACManager, abac_manager
from ..abac.types import ABACDecision
from ..rbac.manager import RoleManager, role_manager
from ..rbac.types import PermissionContext
from .strategies import CombinationStrategy

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


@dataclass
class HybridDecision:
    """
    Hybrid evaluation result.

    Attributes:
        allowed: Final decision
        rbac_allowed: RBAC decision
        abac_allowed: ABAC decision (None if not evaluated)
        strategy: Used strategy
        reason: Textual reason
        abac_decision: ABAC decision detail
    """
    allowed: bool
    rbac_allowed: Optional[bool] = None
    abac_allowed: Optional[bool] = None
    strategy: Optional[CombinationStrategy] = None
    reason: str = ""
    abac_decision: Optional[ABACDecision] = None


class HybridPermissionEngine:
    """
    Hybrid RBAC + ABAC permission engine.

    Combines the two systems according to the configured strategy.
    """

    def __init__(
        self,
        rbac: Optional[RoleManager] = None,
        abac: Optional[ABACManager] = None,
        strategy: Optional[CombinationStrategy] = None,
    ):
        self._rbac = rbac or role_manager
        self._abac = abac or abac_manager
        self._strategy = strategy or CombinationStrategy(
            get_setting(
                "security_settings.hybrid_strategy",
                CombinationStrategy.RBAC_THEN_ABAC.value,
            )
        )
        self._abac_enabled = bool(
            get_setting("security_settings.enable_abac", False)
        )

    def has_permission(
        self,
        user: "AbstractUser",
        permission: str,
        context: Optional[PermissionContext] = None,
        instance: Optional[models.Model] = None,
        request: Any = None,
        **kwargs,
    ) -> HybridDecision:
        """Check permission via the hybrid system."""
        # 1. RBAC evaluation
        rbac_allowed = self._rbac.has_permission(user, permission, context)

        # 2. If ABAC disabled, return RBAC alone
        if not self._abac_enabled:
            return HybridDecision(
                allowed=rbac_allowed,
                rbac_allowed=rbac_allowed,
                reason="rbac_only",
            )

        # 3. ABAC evaluation
        model_class = None
        if context:
            model_class = context.model_class
            if not instance:
                instance = context.object_instance

        abac_decision = self._abac.check_access(
            user=user,
            instance=instance,
            model_class=model_class,
            request=request,
            operation=context.operation if context else None,
        )

        abac_allowed = abac_decision.allowed if abac_decision else None

        # 4. Combine according to strategy
        return self._combine(rbac_allowed, abac_allowed, abac_decision)

    def _combine(
        self,
        rbac: bool,
        abac: Optional[bool],
        abac_decision: Optional[ABACDecision],
    ) -> HybridDecision:
        """Combine decisions according to strategy."""
        strategy = self._strategy

        if abac is None:
            return HybridDecision(
                allowed=rbac, rbac_allowed=rbac,
                strategy=strategy, reason="abac_no_decision",
                abac_decision=abac_decision,
            )

        if strategy == CombinationStrategy.RBAC_AND_ABAC:
            allowed = rbac and abac
        elif strategy == CombinationStrategy.RBAC_OR_ABAC:
            allowed = rbac or abac
        elif strategy == CombinationStrategy.ABAC_OVERRIDE:
            allowed = abac
        elif strategy == CombinationStrategy.RBAC_THEN_ABAC:
            allowed = abac if rbac else False
        elif strategy == CombinationStrategy.MOST_RESTRICTIVE:
            allowed = rbac and abac
        else:
            allowed = rbac and abac

        return HybridDecision(
            allowed=allowed,
            rbac_allowed=rbac,
            abac_allowed=abac,
            strategy=strategy,
            reason=f"{strategy.value}:rbac={rbac},abac={abac}",
            abac_decision=abac_decision,
        )


hybrid_engine = HybridPermissionEngine()
```

---

## 5. Integrations in Existing Code

### 5.1 Update `security/config.py`

Add to `SecurityConfig`:

```python
@staticmethod
def get_abac_config() -> dict[str, Any]:
    """Returns the ABAC configuration."""
    return {
        "enabled": getattr(settings, "ABAC_ENABLED", False),
        "hybrid_strategy": getattr(
            settings, "ABAC_HYBRID_STRATEGY", "rbac_then_abac"
        ),
        "cache_attributes": getattr(settings, "ABAC_CACHE_ATTRIBUTES", True),
        "cache_ttl_seconds": getattr(settings, "ABAC_CACHE_TTL", 60),
        "audit_decisions": getattr(settings, "ABAC_AUDIT_DECISIONS", True),
        "default_effect": getattr(settings, "ABAC_DEFAULT_EFFECT", "deny"),
    }
```

### 5.2 Update `generators/pipeline/steps/permissions.py`

Add after `OperationGuardStep`:

```python
class ABACPermissionStep(MutationStep):
    """
    ABAC permission check in the mutation pipeline.

    Evaluates ABAC policies using the hybrid engine
    if ABAC is enabled in the configuration.
    """
    order = 27
    name = "abac_permission"

    def execute(self, ctx: MutationContext) -> MutationContext:
        from rail_django.config_proxy import get_setting

        if not get_setting("security_settings.enable_abac", False):
            return ctx

        from rail_django.security.hybrid import hybrid_engine
        from rail_django.security.rbac.types import PermissionContext

        user = ctx.user
        if user is None:
            return ctx

        permission = ctx.get_permission_codename()
        perm_context = PermissionContext(
            user=user,
            object_instance=ctx.instance,
            model_class=ctx.model_class,
            operation=ctx.operation,
        )

        decision = hybrid_engine.has_permission(
            user, permission, context=perm_context,
            instance=ctx.instance,
        )

        if not decision.allowed:
            ctx.add_error(
                f"Access denied by hybrid RBAC+ABAC policy: {decision.reason}"
            )

        return ctx
```

### 5.3 Update `security/__init__.py`

Add ABAC and Hybrid exports:

```python
# ABAC
from .abac import (
    ABACPolicy, ABACDecision, ABACContext, ABACEngine, ABACManager,
    AttributeSet, MatchCondition, ConditionOperator,
    abac_engine, abac_manager, require_attributes,
)

# Hybrid
from .hybrid import HybridPermissionEngine, hybrid_engine, CombinationStrategy
```

### 5.4 Django Configuration

```python
# settings.py
RAIL_DJANGO = {
    "security_settings": {
        # Existing RBAC
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
        "enable_policy_engine": True,

        # New ABAC
        "enable_abac": True,
        "hybrid_strategy": "rbac_then_abac",  # or rbac_and_abac, abac_override
        "abac_cache_ttl": 60,
        "abac_audit_decisions": True,
    }
}
```

### 5.5 `GraphQLMeta` — Per-model ABAC Policies

```python
class Document(models.Model):
    department = models.CharField(max_length=100)
    classification = models.CharField(max_length=50)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    class GraphQLMeta:
        # Existing RBAC
        access = GraphQLMetaConfig.Access(
            operations={
                "list": GraphQLMetaConfig.OperationAccess(roles=["viewer"]),
            }
        )

        # New ABAC
        abac_policies = [
            {
                "name": "department_isolation",
                "effect": "allow",
                "subject_conditions": {
                    "department": {"operator": "eq", "target": "resource.department"},
                },
            },
            {
                "name": "business_hours_only",
                "effect": "deny",
                "environment_conditions": {
                    "is_business_hours": {"operator": "eq", "value": False},
                },
                "action_conditions": {
                    "type": {"operator": "in", "value": ["mutation"]},
                },
            },
        ]
```

---

## 6. Test Plan

### 6.1 Unit Tests — `tests/unit/test_abac.py`

```python
"""Unit tests for the ABAC engine."""

import pytest
from rail_django.security.abac import (
    ABACContext, ABACEngine, ABACPolicy, AttributeSet,
    ConditionOperator, MatchCondition,
)


class TestConditionOperators:
    """Tests for each condition operator."""

    def test_eq_match(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_eq", effect="allow",
            subject_conditions={"role": MatchCondition(ConditionOperator.EQ, value="admin")},
        ))
        ctx = ABACContext(subject=AttributeSet(static_attributes={"role": "admin"}))
        decision = engine.evaluate(ctx)
        assert decision.allowed is True

    def test_eq_no_match(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_eq", effect="allow",
            subject_conditions={"role": MatchCondition(ConditionOperator.EQ, value="admin")},
        ))
        ctx = ABACContext(subject=AttributeSet(static_attributes={"role": "viewer"}))
        decision = engine.evaluate(ctx)
        assert decision.allowed is False

    def test_in_operator(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_in", effect="allow",
            action_conditions={"type": MatchCondition(ConditionOperator.IN, value=["query", "mutation"])},
        ))
        ctx = ABACContext(action=AttributeSet(static_attributes={"type": "query"}))
        assert engine.evaluate(ctx).allowed is True

    def test_between_operator(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_between", effect="allow",
            environment_conditions={"hour": MatchCondition(ConditionOperator.BETWEEN, value=[8, 18])},
        ))
        ctx = ABACContext(environment=AttributeSet(static_attributes={"hour": 12}))
        assert engine.evaluate(ctx).allowed is True

    def test_intersects_operator(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_intersects", effect="allow",
            subject_conditions={"roles": MatchCondition(ConditionOperator.INTERSECTS, value=["admin", "manager"])},
        ))
        ctx = ABACContext(subject=AttributeSet(static_attributes={"roles": ["manager", "viewer"]}))
        assert engine.evaluate(ctx).allowed is True

    def test_negate_condition(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_negate", effect="allow",
            subject_conditions={"role": MatchCondition(ConditionOperator.EQ, value="admin", negate=True)},
        ))
        ctx = ABACContext(subject=AttributeSet(static_attributes={"role": "viewer"}))
        assert engine.evaluate(ctx).allowed is True

    def test_dynamic_target_resolution(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_target", effect="allow",
            subject_conditions={
                "department": MatchCondition(ConditionOperator.EQ, target="resource.department"),
            },
        ))
        ctx = ABACContext(
            subject=AttributeSet(static_attributes={"department": "engineering"}),
            resource=AttributeSet(static_attributes={"department": "engineering"}),
        )
        assert engine.evaluate(ctx).allowed is True


class TestPolicyPriority:
    """Tests for policy priority."""

    def test_deny_wins_on_same_priority(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="allow_all", effect="allow", priority=10,
            subject_conditions={"authenticated": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        engine.register_policy(ABACPolicy(
            name="deny_all", effect="deny", priority=10,
            subject_conditions={"authenticated": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        ctx = ABACContext(subject=AttributeSet(static_attributes={"authenticated": True}))
        assert engine.evaluate(ctx).allowed is False

    def test_higher_priority_wins(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="low_deny", effect="deny", priority=1,
            subject_conditions={"authenticated": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        engine.register_policy(ABACPolicy(
            name="high_allow", effect="allow", priority=100,
            subject_conditions={"authenticated": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        ctx = ABACContext(subject=AttributeSet(static_attributes={"authenticated": True}))
        assert engine.evaluate(ctx).allowed is True


class TestABACPolicyCombination:
    """Tests for AND/OR condition combination."""

    def test_all_conditions_must_match(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_all", effect="allow", combine_conditions="all",
            subject_conditions={"role": MatchCondition(ConditionOperator.EQ, value="admin")},
            environment_conditions={"is_business_hours": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        ctx = ABACContext(
            subject=AttributeSet(static_attributes={"role": "admin"}),
            environment=AttributeSet(static_attributes={"is_business_hours": False}),
        )
        assert engine.evaluate(ctx).allowed is False

    def test_any_condition_suffices(self):
        engine = ABACEngine()
        engine.register_policy(ABACPolicy(
            name="test_any", effect="allow", combine_conditions="any",
            subject_conditions={"role": MatchCondition(ConditionOperator.EQ, value="admin")},
            environment_conditions={"is_business_hours": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        ctx = ABACContext(
            subject=AttributeSet(static_attributes={"role": "admin"}),
            environment=AttributeSet(static_attributes={"is_business_hours": False}),
        )
        assert engine.evaluate(ctx).allowed is True
```

### 6.2 Unit Tests — `tests/unit/test_hybrid.py`

```python
"""Unit tests for the hybrid RBAC+ABAC engine."""

import pytest
from django.contrib.auth.models import User
from rail_django.security.abac import ABACEngine, ABACPolicy, MatchCondition, ConditionOperator
from rail_django.security.abac.manager import ABACManager
from rail_django.security.hybrid.engine import HybridPermissionEngine, HybridDecision
from rail_django.security.hybrid.strategies import CombinationStrategy
from rail_django.security.rbac import RoleDefinition, RoleManager, RoleType

pytestmark = pytest.mark.unit


@pytest.mark.django_db
class TestHybridStrategies:

    def _setup(self, strategy):
        rbac = RoleManager()
        abac_engine = ABACEngine()
        abac = ABACManager(engine=abac_engine)
        engine = HybridPermissionEngine(rbac=rbac, abac=abac, strategy=strategy)
        engine._abac_enabled = True
        return rbac, abac_engine, engine

    def test_rbac_and_abac_both_must_allow(self):
        rbac, abac_eng, engine = self._setup(CombinationStrategy.RBAC_AND_ABAC)
        user = User.objects.create_user("hybrid_test", password="pass12345")
        rbac.register_role(RoleDefinition(
            name="tester", role_type=RoleType.BUSINESS,
            description="Test", permissions=["test.read"],
        ))
        rbac.assign_role_to_user(user, "tester")
        # RBAC allows, ABAC denies → denied
        abac_eng.register_policy(ABACPolicy(
            name="deny_test", effect="deny",
            subject_conditions={"authenticated": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        decision = engine.has_permission(user, "test.read")
        assert decision.allowed is False
        assert decision.rbac_allowed is True

    def test_rbac_or_abac_one_suffices(self):
        rbac, abac_eng, engine = self._setup(CombinationStrategy.RBAC_OR_ABAC)
        user = User.objects.create_user("hybrid_or", password="pass12345")
        # RBAC denies (no role), ABAC allows
        abac_eng.register_policy(ABACPolicy(
            name="allow_all", effect="allow",
            subject_conditions={"authenticated": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        decision = engine.has_permission(user, "test.read")
        assert decision.allowed is True

    def test_abac_override_ignores_rbac(self):
        rbac, abac_eng, engine = self._setup(CombinationStrategy.ABAC_OVERRIDE)
        user = User.objects.create_user("hybrid_override", password="pass12345")
        rbac.register_role(RoleDefinition(
            name="override_role", role_type=RoleType.BUSINESS,
            description="Test", permissions=["test.read"],
        ))
        rbac.assign_role_to_user(user, "override_role")
        abac_eng.register_policy(ABACPolicy(
            name="deny_override", effect="deny",
            subject_conditions={"authenticated": MatchCondition(ConditionOperator.EQ, value=True)},
        ))
        decision = engine.has_permission(user, "test.read")
        assert decision.allowed is False  # ABAC deny overrides RBAC allow
```

### 6.3 Integration Tests — `tests/integration/test_abac_graphql.py`

Test `require_attributes` decorators on real GraphQL resolvers, verify that the mutation pipeline with `ABACPermissionStep` works, and validate attribute providers with real Django models.

---

## 7. Documentation Plan

### 7.1 `rail_django/docs/library/security/abac.md`

Comprehensive ABAC system documentation covering:

- Architecture and concepts (subject, resource, environment, action)
- Quick start guide
- API reference for each class/type
- Common policy examples (department isolation, business hours, classification)
- Django configuration
- `GraphQLMeta` integration

### 7.2 `rail_django/docs/library/security/hybrid.md`

Hybrid engine documentation:

- Available combination strategies
- Evaluation flow
- Configuration
- Scenario examples

### 7.3 Update Existing Files

| File                             | Modification                   |
| -------------------------------- | ------------------------------ |
| `docs/library/security/index.md` | Add links to ABAC and Hybrid   |
| `docs/library/security/rbac.md`  | Add "ABAC Integration" section |
| `docs/reference/security.md`     | Add ABAC reference             |

---

## 8. Implementation Order

| Phase  | Task                 | Files                                       | Est. |
| ------ | -------------------- | ------------------------------------------- | ---- |
| **1**  | ABAC Types           | `security/abac/types.py`                    | 1h   |
| **2**  | Attribute Providers  | `security/abac/attributes.py`               | 2h   |
| **3**  | ABAC Engine          | `security/abac/engine.py`                   | 2h   |
| **4**  | ABAC Manager         | `security/abac/manager.py`                  | 1h   |
| **5**  | ABAC Decorators      | `security/abac/decorators.py`               | 1h   |
| **6**  | Package init         | `security/abac/__init__.py`                 | 0.5h |
| **7**  | Hybrid Strategies    | `security/hybrid/strategies.py`             | 0.5h |
| **8**  | Hybrid Engine        | `security/hybrid/engine.py`                 | 2h   |
| **9**  | Hybrid Package init  | `security/hybrid/__init__.py`               | 0.5h |
| **10** | Config Integration   | `security/config.py`                        | 0.5h |
| **11** | Pipeline Integration | `generators/pipeline/steps/permissions.py`  | 1h   |
| **12** | Update Exports       | `security/__init__.py`                      | 0.5h |
| **13** | ABAC Unit Tests      | `tests/unit/test_abac.py`                   | 2h   |
| **14** | Hybrid Unit Tests    | `tests/unit/test_hybrid.py`                 | 2h   |
| **15** | Integration Tests    | `tests/integration/test_abac_graphql.py`    | 2h   |
| **16** | ABAC Documentation   | `docs/library/security/abac.md`             | 1h   |
| **17** | Hybrid Documentation | `docs/library/security/hybrid.md`           | 1h   |
| **18** | Update existing docs | `docs/library/security/index.md`, `rbac.md` | 0.5h |

**Estimated Total: ~21 hours**

---

## 9. Usage Examples

### Department Isolation Policy

```python
from rail_django.security.abac import abac_engine, ABACPolicy, MatchCondition, ConditionOperator

abac_engine.register_policy(ABACPolicy(
    name="department_isolation",
    description="Users only see resources from their own department",
    effect="allow",
    priority=50,
    subject_conditions={
        "department": MatchCondition(
            ConditionOperator.EQ,
            target="resource.department",
        ),
    },
))
```

### Business Hours Restriction for Mutations

```python
abac_engine.register_policy(ABACPolicy(
    name="business_hours_mutations",
    description="Mutations are forbidden outside of business hours",
    effect="deny",
    priority=100,
    environment_conditions={
        "is_business_hours": MatchCondition(ConditionOperator.EQ, value=False),
    },
    action_conditions={
        "type": MatchCondition(ConditionOperator.EQ, value="mutation"),
    },
))
```

### Document Classification Access

```python
abac_engine.register_policy(ABACPolicy(
    name="confidential_access",
    description="Only managers access confidential documents",
    effect="deny",
    priority=90,
    resource_conditions={
        "classification": MatchCondition(ConditionOperator.EQ, value="confidential"),
    },
    subject_conditions={
        "roles": MatchCondition(
            ConditionOperator.INTERSECTS,
            value=["manager", "admin", "superadmin"],
            negate=True,
        ),
    },
))
```

### Hybrid Engine Usage

```python
from rail_django.security.hybrid import hybrid_engine
from rail_django.security.rbac import PermissionContext

context = PermissionContext(
    user=request.user,
    object_instance=document,
    operation="update",
)

decision = hybrid_engine.has_permission(
    request.user,
    "documents.change_document",
    context=context,
    request=request,
)

if not decision.allowed:
    raise PermissionDenied(f"Access denied: {decision.reason}")
```

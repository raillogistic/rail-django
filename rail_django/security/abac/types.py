"""
Types and data structures for ABAC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class ConditionOperator(Enum):
    """Supported ABAC condition operators."""

    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    MATCHES = "matches"
    EXISTS = "exists"
    IS_SUBSET = "is_subset"
    INTERSECTS = "intersects"
    CUSTOM = "custom"


@dataclass
class MatchCondition:
    """Condition definition for one attribute."""

    operator: ConditionOperator
    value: Any = None
    target: Optional[str] = None
    custom_func: Optional[Callable[..., bool]] = None
    negate: bool = False


@dataclass
class AttributeSet:
    """Static and dynamic attributes for one context category."""

    static_attributes: dict[str, Any] = field(default_factory=dict)
    dynamic_resolvers: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.static_attributes:
            return self.static_attributes[key]
        resolver = self.dynamic_resolvers.get(key)
        if resolver is None:
            return default
        try:
            return resolver()
        except Exception:
            return default

    def resolve_all(self) -> dict[str, Any]:
        resolved = dict(self.static_attributes)
        for key, resolver in self.dynamic_resolvers.items():
            if key in resolved:
                continue
            try:
                resolved[key] = resolver()
            except Exception:
                resolved[key] = None
        return resolved


@dataclass
class ABACContext:
    """Complete ABAC evaluation context."""

    subject: AttributeSet = field(default_factory=AttributeSet)
    resource: AttributeSet = field(default_factory=AttributeSet)
    environment: AttributeSet = field(default_factory=AttributeSet)
    action: AttributeSet = field(default_factory=AttributeSet)

    def resolve_reference(self, ref: str) -> Any:
        parts = (ref or "").split(".", 1)
        if len(parts) != 2:
            return None
        category, key = parts
        attr_set = getattr(self, category, None)
        if attr_set is None:
            return None
        return attr_set.get(key)


@dataclass
class ABACPolicy:
    """ABAC policy definition."""

    name: str
    description: str = ""
    effect: str = "allow"
    priority: int = 0
    subject_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    resource_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    environment_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    action_conditions: dict[str, MatchCondition] = field(default_factory=dict)
    combine_conditions: str = "all"
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class ABACDecision:
    """ABAC decision result."""

    allowed: bool
    matched_policy: Optional[ABACPolicy] = None
    reason: Optional[str] = None
    evaluated_policies: int = 0
    matched_conditions: dict[str, bool] = field(default_factory=dict)
    evaluation_time_ms: float = 0.0


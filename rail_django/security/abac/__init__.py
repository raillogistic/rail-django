"""
Attribute-Based Access Control (ABAC) package.
"""

from .attributes import (
    ActionAttributeProvider,
    BaseAttributeProvider,
    EnvironmentAttributeProvider,
    ResourceAttributeProvider,
    SubjectAttributeProvider,
)
from .decorators import require_attributes
from .engine import ABACEngine, abac_engine
from .manager import ABACManager, abac_manager
from .types import (
    ABACContext,
    ABACDecision,
    ABACPolicy,
    AttributeSet,
    ConditionOperator,
    MatchCondition,
)

__all__ = [
    "ABACPolicy",
    "ABACDecision",
    "ABACContext",
    "AttributeSet",
    "MatchCondition",
    "ConditionOperator",
    "ABACEngine",
    "abac_engine",
    "BaseAttributeProvider",
    "SubjectAttributeProvider",
    "ResourceAttributeProvider",
    "EnvironmentAttributeProvider",
    "ActionAttributeProvider",
    "require_attributes",
    "ABACManager",
    "abac_manager",
]


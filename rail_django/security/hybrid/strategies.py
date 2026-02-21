"""
Hybrid decision combination strategies.
"""

from enum import Enum


class CombinationStrategy(Enum):
    """RBAC + ABAC combination strategies."""

    RBAC_AND_ABAC = "rbac_and_abac"
    RBAC_OR_ABAC = "rbac_or_abac"
    ABAC_OVERRIDE = "abac_override"
    RBAC_THEN_ABAC = "rbac_then_abac"
    MOST_RESTRICTIVE = "most_restrictive"


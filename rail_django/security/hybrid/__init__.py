"""
Hybrid RBAC + ABAC permission package.
"""

from .engine import HybridDecision, HybridPermissionEngine, hybrid_engine
from .strategies import CombinationStrategy

__all__ = [
    "HybridDecision",
    "HybridPermissionEngine",
    "hybrid_engine",
    "CombinationStrategy",
]


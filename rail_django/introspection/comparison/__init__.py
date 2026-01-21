"""
Schema comparison package.
"""

from .comparator import SchemaComparator
from .types import (
    BreakingChangeLevel,
    ChangeType,
    SchemaChange,
    SchemaComparison,
)

__all__ = [
    "SchemaComparator",
    "SchemaComparison",
    "SchemaChange",
    "ChangeType",
    "BreakingChangeLevel",
]

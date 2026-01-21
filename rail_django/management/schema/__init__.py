"""
Schema management package.

This package provides comprehensive schema lifecycle management including
registration, updates, versioning, and administrative operations.
"""

from .health import SchemaHealth
from .lifecycle import (
    SchemaLifecycleEvent,
    SchemaMetadata,
    SchemaOperation,
    SchemaStatus,
)
from .manager import SchemaManager

__all__ = [
    "SchemaManager",
    "SchemaOperation",
    "SchemaStatus",
    "SchemaLifecycleEvent",
    "SchemaMetadata",
    "SchemaHealth",
]

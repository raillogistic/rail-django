"""
Nested Operations System for Django GraphQL Auto-Generation

This module provides advanced nested create/update operations with comprehensive
validation, transaction management, and cascade handling for related objects.

NOTE: This module has been refactored into the `nested` package for better
maintainability. This file now re-exports from that package for backwards
compatibility.
"""

# Re-export from the new nested package for backwards compatibility
from .nested import (
    NestedOperationHandler,
    NestedOperationHandlerBase,
    NestedCreateMixin,
    NestedUpdateMixin,
    NestedDeleteMixin,
)

__all__ = [
    "NestedOperationHandler",
    "NestedOperationHandlerBase",
    "NestedCreateMixin",
    "NestedUpdateMixin",
    "NestedDeleteMixin",
]

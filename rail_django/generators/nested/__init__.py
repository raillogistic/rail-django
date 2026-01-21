"""
Nested Operations Package

This package provides the NestedOperationHandler for handling complex nested
operations in GraphQL mutations, including nested creates, updates, and
cascade delete operations.

The handler is split into multiple mixins for maintainability:
- NestedOperationHandlerBase: Core utility methods
- NestedCreateMixin: Nested create operation handling
- NestedUpdateMixin: Nested update operation handling
- NestedDeleteMixin: Cascade delete and validation

Usage:
    from rail_django.generators.nested import NestedOperationHandler

    handler = NestedOperationHandler(schema_name="default")
    instance = handler.handle_nested_create(Model, input_data, info=info)
"""

from .handler import NestedOperationHandler
from .handler import NestedOperationHandlerBase
from .create import NestedCreateMixin
from .update import NestedUpdateMixin
from .delete import NestedDeleteMixin

__all__ = [
    "NestedOperationHandler",
    "NestedOperationHandlerBase",
    "NestedCreateMixin",
    "NestedUpdateMixin",
    "NestedDeleteMixin",
]

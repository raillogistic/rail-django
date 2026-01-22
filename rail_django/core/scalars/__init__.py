"""
Custom GraphQL scalars package.

This package implements various custom scalar types for use in GraphQL schemas.
"""

from .ast_utils import (
    _BOOLEAN_VALUE_TYPES,
    _FLOAT_VALUE_TYPES,
    _INT_VALUE_TYPES,
    _LIST_VALUE_TYPES,
    _NULL_VALUE_TYPES,
    _OBJECT_VALUE_TYPES,
    _STRING_VALUE_TYPES,
    _UNDEFINED,
)
from .binary import Binary
from .common import URL, UUID, Decimal, Email, Phone
from .json_scalar import JSON
from .registry import (
    CUSTOM_SCALARS,
    get_custom_scalar,
    get_enabled_scalars,
    register_custom_scalar,
)
from .temporal import Date, DateTime, Time

__all__ = [
    # Scalars
    "DateTime",
    "Date",
    "Time",
    "JSON",
    "UUID",
    "Email",
    "URL",
    "Phone",
    "Decimal",
    "Binary",
    # Registry functions
    "CUSTOM_SCALARS",
    "get_custom_scalar",
    "register_custom_scalar",
    "get_enabled_scalars",
    # AST types
    "_STRING_VALUE_TYPES",
    "_OBJECT_VALUE_TYPES",
    "_LIST_VALUE_TYPES",
    "_BOOLEAN_VALUE_TYPES",
    "_INT_VALUE_TYPES",
    "_FLOAT_VALUE_TYPES",
    "_NULL_VALUE_TYPES",
    "_UNDEFINED",
]

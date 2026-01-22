"""
Custom GraphQL scalars module.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.core.scalars` package.

DEPRECATION NOTICE:
    Importing from `rail_django.core.scalars` module is deprecated.
    Please update your imports to use `rail_django.core.scalars` package instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.core.scalars' module is deprecated. "
    "Use 'rail_django.core.scalars' package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .scalars import (
    CUSTOM_SCALARS,
    _BOOLEAN_VALUE_TYPES,
    _FLOAT_VALUE_TYPES,
    _INT_VALUE_TYPES,
    _LIST_VALUE_TYPES,
    _NULL_VALUE_TYPES,
    _OBJECT_VALUE_TYPES,
    _STRING_VALUE_TYPES,
    _UNDEFINED,
    Binary,
    Date,
    DateTime,
    Decimal,
    Email,
    JSON,
    Phone,
    Time,
    URL,
    UUID,
    get_custom_scalar,
    get_enabled_scalars,
    register_custom_scalar,
)

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
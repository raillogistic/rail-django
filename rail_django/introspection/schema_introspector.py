"""
Schema introspection module.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.introspection.schema_introspector` package.

DEPRECATION NOTICE:
    Importing from `rail_django.introspection.schema_introspector` module is deprecated.
    Please update your imports to use `rail_django.introspection.schema_introspector` package instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.introspection.schema_introspector' module is deprecated. "
    "Use 'rail_django.introspection.schema_introspector' package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .schema_introspector.analyzer import SchemaIntrospector
from .schema_introspector.types import (
    DirectiveInfo,
    FieldInfo,
    SchemaComplexity,
    SchemaIntrospection,
    TypeInfo,
)

__all__ = [
    "SchemaIntrospector",
    "SchemaIntrospection",
    "TypeInfo",
    "FieldInfo",
    "DirectiveInfo",
    "SchemaComplexity",
]
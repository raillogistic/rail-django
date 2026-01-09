"""
Schema introspection module.

This module provides comprehensive introspection capabilities for GraphQL schemas,
including schema analysis, comparison, documentation generation, and metadata extraction.
"""

from .documentation_generator import DocumentationGenerator
from .schema_comparator import BreakingChangeLevel, ChangeType, SchemaComparator, SchemaComparison
from .schema_introspector import SchemaIntrospection, SchemaIntrospector

__all__ = [
    'SchemaIntrospector',
    'SchemaIntrospection',
    'SchemaComparator',
    'SchemaComparison',
    'DocumentationGenerator',
    'ChangeType',
    'BreakingChangeLevel',
]

"""
Multi-schema GraphQL views for handling multiple GraphQL schemas with different configurations.
"""

from .multi_schema import MultiSchemaGraphQLView
from .schema_list import SchemaListView

__all__ = [
    "MultiSchemaGraphQLView",
    "SchemaListView",
]

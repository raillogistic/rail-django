"""
Multi-schema GraphQL view package.
"""

from .view import MultiSchemaGraphQLView, SchemaRegistryUnavailable

__all__ = [
    "MultiSchemaGraphQLView",
    "SchemaRegistryUnavailable",
]

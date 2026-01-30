"""
Schema Builder Package for rail-django library.

This package provides the SchemaBuilder class, which is responsible for assembling
the unified GraphQL schema from all registered Django apps and models.

Re-exports:
    - SchemaBuilder: Main schema builder class
    - AutoSchemaGenerator: Builder for explicit model lists
    - get_schema: Get schema by name
    - get_schema_builder: Get schema builder by name
    - clear_all_schemas: Clear all schema instances
    - get_all_schema_names: Get list of all schema names
"""

import logging
from typing import List, Optional, Type

import graphene
from django.db import models

from .auto_generator import AutoSchemaGenerator
from .builder import SchemaBuilderCore
from .extensions import ExtensionsMixin
from .query_builder import QueryBuilderMixin
from .query_integration import QueryIntegrationMixin
from .registration import RegistrationMixin

logger = logging.getLogger(__name__)


class SchemaBuilder(
    QueryBuilderMixin,
    QueryIntegrationMixin,
    RegistrationMixin,
    ExtensionsMixin,
    SchemaBuilderCore,
):
    """
    Builds and manages the unified GraphQL schema, combining queries and mutations
    from all registered Django apps and models.

    This class supports:
    - Multiple schema configurations
    - Schema-specific settings
    - Automatic model discovery
    - Dynamic schema rebuilding
    - Integration with the schema registry

    The class is composed of several mixins:
    - SchemaBuilderCore: Core initialization and settings management
    - QueryBuilderMixin: Query, mutation, and subscription generation
    - QueryIntegrationMixin: Security, health, and metadata query integration
    - RegistrationMixin: App and model registration methods
    - ExtensionsMixin: Extension integration and rebuild_schema method
    """

    pass


# Global schema management functions


def get_schema_builder(schema_name: str = "default") -> SchemaBuilder:
    """
    Get or create a schema builder instance for the given schema name.

    Args:
        schema_name: Name of the schema (defaults to "default")

    Returns:
        SchemaBuilder: Schema builder instance
    """
    from ..registry import schema_registry

    schema_registry.discover_schemas()
    # The registry manages caching of builders now
    return schema_registry.get_schema_builder(schema_name)


def get_schema(schema_name: str = "default") -> graphene.Schema:
    """
    Get the GraphQL schema for the given schema name.

    Args:
        schema_name: Name of the schema (defaults to "default")

    Returns:
        graphene.Schema: The GraphQL schema
    """
    return get_schema_builder(schema_name).get_schema()


def register_mutation(mutation_class: Type[graphene.Mutation], name: Optional[str] = None, schema_name: str = "default") -> None:
    """
    Register a custom mutation class to the given schema.

    Args:
        mutation_class: Graphene mutation class
        name: Optional field name
        schema_name: Target schema name
    """
    get_schema_builder(schema_name).register_mutation(mutation_class, name)


def clear_all_schemas() -> None:
    """Clear all schema builder instances."""
    from ..registry import schema_registry
    
    schema_registry.clear_builders()
    logger.info("All schemas cleared")


def get_all_schema_names() -> List[str]:
    """
    Get all registered schema names.

    Returns:
        List[str]: List of schema names
    """
    from ..registry import schema_registry
    return schema_registry.get_schema_names()


# Public API
__all__ = [
    "SchemaBuilder",
    "AutoSchemaGenerator",
    "get_schema",
    "get_schema_builder",
    "register_mutation",
    "clear_all_schemas",
    "get_all_schema_names",
]

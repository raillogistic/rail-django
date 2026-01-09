"""
Generator modules for rail-django library

This package contains all the generator classes responsible for creating
GraphQL types, queries, and mutations from Django models.

The generators support:
- Type generation with customizable naming conventions
- Query generation with filtering and pagination
- Mutation generation with validation and permissions
- Nested operations
- Custom scalars
- Model inheritance
"""

from typing import TYPE_CHECKING

# Lazy imports to avoid circular dependencies
if TYPE_CHECKING:
    from .introspector import ModelIntrospector
    from .mutations import MutationGenerator
    from .queries import QueryGenerator
    from .types import TypeGenerator

__all__ = [
    "TypeGenerator",
    "QueryGenerator",
    "MutationGenerator",
    "ModelIntrospector",
    "get_type_generator",
    "get_query_generator",
    "get_mutation_generator",
    "get_model_introspector",
]


def get_type_generator(settings=None, schema_name: str = "default"):
    """
    Get a TypeGenerator instance with optional settings.

    Args:
        settings: Type generator settings or None for defaults
        schema_name: Name of the schema (for multi-schema support)

    Returns:
        TypeGenerator: Type generator instance
    """
    from .types import TypeGenerator

    return TypeGenerator(settings=settings, schema_name=schema_name)


def get_query_generator(
    type_generator=None, settings=None, schema_name: str = "default"
):
    """
    Get a QueryGenerator instance with optional settings.

    Args:
        type_generator: TypeGenerator instance or None for default
        settings: Query generator settings or None for defaults
        schema_name: Name of the schema (for multi-schema support)

    Returns:
        QueryGenerator: Query generator instance
    """
    from .queries import QueryGenerator

    if type_generator is None:
        type_generator = get_type_generator(schema_name=schema_name)
    return QueryGenerator(type_generator, settings=settings, schema_name=schema_name)


def get_mutation_generator(
    type_generator=None, settings=None, schema_name: str = "default"
):
    """
    Get a MutationGenerator instance with optional settings.

    Args:
        type_generator: TypeGenerator instance or None for default
        settings: Mutation generator settings or None for defaults
        schema_name: Name of the schema (for multi-schema support)

    Returns:
        MutationGenerator: Mutation generator instance
    """
    from .mutations import MutationGenerator

    if type_generator is None:
        type_generator = get_type_generator(schema_name=schema_name)
    return MutationGenerator(type_generator, settings=settings, schema_name=schema_name)


def get_model_introspector():
    """
    Get a ModelIntrospector instance.

    Returns:
        ModelIntrospector: Model introspector instance
    """
    from .introspector import ModelIntrospector

    return ModelIntrospector()

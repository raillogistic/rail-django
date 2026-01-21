"""
Schema Registry System for rail-django library.

This package provides a centralized registry for managing multiple GraphQL schemas,
their configurations, and automatic discovery mechanisms.
"""

from typing import Any, Callable, Optional
from django.apps import apps
from django.utils.module_loading import import_string

from .builders import get_schema_builder, get_schema_instance
from .discovery import (
    add_discovery_hook,
    auto_discover_schemas,
    discover_schemas,
    remove_discovery_hook,
)
from .info import SchemaInfo
from .registry import SchemaRegistry

__all__ = [
    "SchemaInfo",
    "SchemaRegistry",
    "schema_registry",
    "register_schema",
    "get_schema",
    "get_schema_builder",
    "list_schemas",
    "apps",
    "import_string",
]

# Global schema registry instance
schema_registry = SchemaRegistry()


# Convenience functions
def register_schema(*args, **kwargs) -> SchemaInfo:
    """Register a schema using the global registry."""
    return schema_registry.register_schema(*args, **kwargs)


def get_schema(name: str) -> Optional[SchemaInfo]:
    """Get schema info using the global registry."""
    return schema_registry.get_schema(name)


def get_schema_builder(name: str):
    """Get schema builder using the global registry."""
    return schema_registry.get_schema_builder(name)


def list_schemas(enabled_only: bool = False) -> list[SchemaInfo]:
    """List schemas using the global registry."""
    return schema_registry.list_schemas(enabled_only)
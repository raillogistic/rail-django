"""
Rail Django GraphQL - Automatic GraphQL schema generation for Django.

This library provides tools for automatically generating GraphQL schemas
from Django models with advanced features for security, permissions,
and performance optimization.
"""

__version__ = "1.1.4"
__author__ = "Rail Logistic Team"
__email__ = "contact@raillogistic.com"
__title__ = "rail-django"
__description__ = (
    "Automatic GraphQL schema generation for Django with advanced features"
)
__url__ = "https://github.com/raillogistic/rail-django"
__license__ = "MIT"

# Django app configuration - handle deprecation of default_app_config
try:
    import django

    if django.VERSION < (3, 2):
        # For Django < 3.2, explicitly set default_app_config
        default_app_config = "rail_django.apps.AppConfig"
except ImportError:
    # Django not available, skip configuration
    pass

# Import check for Django
try:
    import django

    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False

# Library metadata
LIBRARY_VERSION = __version__
LIBRARY_NAME = __title__


# Lazy imports to avoid circular dependencies and improve startup time
def get_settings():
    """Get library settings with lazy import."""
    from .config_proxy import settings_proxy

    return settings_proxy


def get_schema_settings(schema_name: str):
    """Get settings for a specific schema with lazy import."""
    from .config_proxy import get_settings_for_schema

    return get_settings_for_schema(schema_name)


def configure_schema(**overrides):
    """Configure schema settings with lazy import."""
    from .config_proxy import configure_schema_settings

    return configure_schema_settings


def get_type_generator():
    """Get TypeGenerator class with lazy import."""
    from .generators.types import TypeGenerator

    return TypeGenerator


def get_query_generator():
    """Get QueryGenerator class with lazy import."""
    from .generators.queries import QueryGenerator

    return QueryGenerator


def get_mutation_generator():
    """Get MutationGenerator class with lazy import."""
    from .generators.mutations import MutationGenerator

    return MutationGenerator


def get_model_introspector():
    """Get ModelIntrospector class with lazy import."""
    from .generators.introspector import ModelIntrospector

    return ModelIntrospector


def get_schema_builder():
    """Get SchemaBuilder class with lazy import."""
    from .core.schema import SchemaBuilder

    return SchemaBuilder


def get_config_loader():
    """Get ConfigLoader class with lazy import."""
    from .core.config_loader import ConfigLoader

    return ConfigLoader


# Direct imports for main classes (lazy loaded)
def __getattr__(name):
    """Lazy import for main classes."""
    if name == "TypeGenerator":
        from .generators.types import TypeGenerator

        return TypeGenerator
    elif name == "QueryGenerator":
        from .generators.queries import QueryGenerator

        return QueryGenerator
    elif name == "MutationGenerator":
        from .generators.mutations import MutationGenerator

        return MutationGenerator
    elif name == "ModelIntrospector":
        from .generators.introspector import ModelIntrospector

        return ModelIntrospector
    elif name == "SchemaBuilder":
        from .core.schema import SchemaBuilder

        return SchemaBuilder
    elif name == "ConfigLoader":
        from .core.config_loader import ConfigLoader

        return ConfigLoader
    elif name == "settings":
        # Export the hierarchical SettingsProxy as 'settings'
        from .config_proxy import settings_proxy

        return settings_proxy
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# Public API exports
__all__ = [
    # Version and metadata
    "__version__",
    "__author__",
    "__title__",
    "__description__",
    "__url__",
    "__license__",
    "LIBRARY_VERSION",
    "LIBRARY_NAME",
    "DJANGO_AVAILABLE",
    # Configuration
    "get_settings",
    "get_schema_settings",
    "configure_schema",
    "settings",
    # Core components
    "SchemaBuilder",
    "ConfigLoader",
    "get_schema_builder",
    "get_config_loader",
    # Generators
    "TypeGenerator",
    "QueryGenerator",
    "MutationGenerator",
    "ModelIntrospector",
    "get_type_generator",
    "get_query_generator",
    "get_mutation_generator",
    "get_model_introspector",
]

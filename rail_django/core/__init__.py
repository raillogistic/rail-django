"""Core module for Django GraphQL Auto-Generation.

This module contains the core functionality for automatic GraphQL schema generation,
including configuration management, schema building, error handling, debugging,
and core utilities.
"""

from .config_loader import ConfigLoader
from .debug import (
    GraphQLPerformanceMiddleware,
    GraphQLPerformanceView,
    PerformanceAggregator,
    PerformanceAlert,
    RequestMetrics,
    get_performance_aggregator,
    monitor_performance,
    setup_performance_monitoring,
)
from .exceptions import (
    AuthenticationError,
    ErrorCode,
    ErrorHandler,
    FileUploadError,
    GraphQLAutoError,
    PermissionError,
    QueryComplexityError,
    QueryDepthError,
    RateLimitError,
    ResourceNotFoundError,
    SecurityError,
    ValidationError,
    error_handler,
    handle_graphql_error,
)
from .schema import SchemaBuilder
from .settings import (
    GraphQLAutoConfig,
    MutationGeneratorSettings,
    QueryGeneratorSettings,
    SchemaSettings,
    TypeGeneratorSettings,
)

__all__ = [
    # Configuration et schéma
    "ConfigLoader",
    "SchemaBuilder",
    "TypeGeneratorSettings",
    "QueryGeneratorSettings",
    "MutationGeneratorSettings",
    "SchemaSettings",
    "GraphQLAutoConfig",
    # Gestion d'erreurs
    "GraphQLAutoError",
    "ValidationError",
    "AuthenticationError",
    "PermissionError",
    "ResourceNotFoundError",
    "SecurityError",
    "RateLimitError",
    "QueryComplexityError",
    "QueryDepthError",
    "FileUploadError",
    "ErrorCode",
    "ErrorHandler",
    "error_handler",
    "handle_graphql_error",
    # Debug et profilage
    "RequestMetrics",
    "PerformanceAlert",
    "PerformanceAggregator",
    "GraphQLPerformanceMiddleware",
    "GraphQLPerformanceView",
    "get_performance_aggregator",
    "setup_performance_monitoring",
    "monitor_performance",
]

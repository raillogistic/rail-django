"""Core module for Django GraphQL Auto-Generation.

This module contains the core functionality for automatic GraphQL schema generation,
including configuration management, schema building, error handling, debugging,
and core utilities.
"""

from .config import ConfigLoader
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
    FilteringSettings,
    GraphQLAutoConfig,
    MutationGeneratorSettings,
    QueryGeneratorSettings,
    SchemaSettings,
    SubscriptionGeneratorSettings,
    TypeGeneratorSettings,
)

__all__ = [
    # Configuration and schema
    "ConfigLoader",
    "SchemaBuilder",
    "TypeGeneratorSettings",
    "QueryGeneratorSettings",
    "MutationGeneratorSettings",
    "SchemaSettings",
    "GraphQLAutoConfig",
    # Error handling
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
    # Debug and profiling
    "RequestMetrics",
    "PerformanceAlert",
    "PerformanceAggregator",
    "GraphQLPerformanceMiddleware",
    "GraphQLPerformanceView",
    "get_performance_aggregator",
    "setup_performance_monitoring",
    "monitor_performance",
]

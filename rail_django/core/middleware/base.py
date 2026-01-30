"""
Base middleware classes for Rail Django GraphQL.

This module provides the foundation classes for all GraphQL middleware,
including configuration management via MiddlewareSettings.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class MiddlewareSettings:
    """Settings for GraphQL middleware.

    Attributes:
        enable_authentication_middleware: Enable user authentication middleware.
        enable_logging_middleware: Enable operation logging middleware.
        enable_performance_middleware: Enable performance monitoring middleware.
        enable_error_handling_middleware: Enable error handling middleware.
        enable_rate_limiting_middleware: Enable rate limiting middleware.
        enable_validation_middleware: Enable input validation middleware.
        enable_field_permission_middleware: Enable field permission middleware.
        enable_cors_middleware: Enable CORS handling middleware.
        log_queries: Log query operations.
        log_mutations: Log mutation operations.
        log_introspection: Log introspection queries.
        log_errors: Log errors that occur during resolution.
        log_performance: Log performance warnings for slow operations.
        performance_threshold_ms: Threshold in milliseconds for slow operation warnings.
        enable_query_complexity_middleware: Enable query complexity analysis.
    """

    enable_authentication_middleware: bool = True
    enable_logging_middleware: bool = True
    enable_performance_middleware: bool = True
    enable_error_handling_middleware: bool = True
    enable_rate_limiting_middleware: bool = True
    enable_validation_middleware: bool = True
    enable_field_permission_middleware: bool = True
    enable_cors_middleware: bool = True
    log_queries: bool = True
    log_mutations: bool = True
    log_introspection: bool = False
    log_errors: bool = True
    log_performance: bool = True
    performance_threshold_ms: int = 1000
    enable_query_complexity_middleware: bool = True

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "MiddlewareSettings":
        """Create MiddlewareSettings from schema configuration.

        Args:
            schema_name: Optional schema name for schema-specific settings.

        Returns:
            MiddlewareSettings instance with merged configuration.
        """
        from rail_django.config.defaults import LIBRARY_DEFAULTS
        from django.conf import settings as django_settings

        defaults = LIBRARY_DEFAULTS.get("middleware_settings", {})

        # Allow Django settings to override defaults
        django_mw_settings = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {}).get(
            "middleware_settings", {}
        )

        merged_settings = {**defaults, **django_mw_settings}

        # Filter to only include valid fields
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {k: v for k, v in merged_settings.items() if k in valid_fields}

        return cls(**filtered_settings)


class BaseMiddleware:
    """Base class for GraphQL middleware.

    All middleware classes should inherit from this base class and override
    the resolve method to implement custom middleware logic.

    Attributes:
        schema_name: The name of the schema this middleware is associated with.
        settings: MiddlewareSettings instance for this middleware.
    """

    def __init__(self, schema_name: Optional[str] = None):
        """Initialize the middleware.

        Args:
            schema_name: Optional schema name for schema-specific behavior.
        """
        self.schema_name = schema_name
        self.settings = MiddlewareSettings.from_schema(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Middleware resolve method.

        This method is called for each field resolution. Override this method
        to implement custom middleware logic.

        Args:
            next_resolver: Next resolver in the chain to call.
            root: Root value passed to the resolver.
            info: GraphQL resolve info containing context and field information.
            **kwargs: Additional arguments passed to the resolver.

        Returns:
            The result from the resolver chain.
        """
        return next_resolver(root, info, **kwargs)

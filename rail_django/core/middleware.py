"""
GraphQL middleware for Rail Django GraphQL.

This module implements middleware functionality defined in LIBRARY_DEFAULTS
including authentication, logging, performance monitoring, and error handling.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from ..conf import get_setting
from .performance import get_complexity_analyzer
from .security import get_auth_manager, get_input_validator, get_rate_limiter

logger = logging.getLogger(__name__)


@dataclass
class MiddlewareSettings:
    """Settings for GraphQL middleware."""

    enable_authentication_middleware: bool = True
    enable_logging_middleware: bool = True
    enable_performance_middleware: bool = True
    enable_error_handling_middleware: bool = True
    enable_rate_limiting_middleware: bool = True
    enable_validation_middleware: bool = True
    enable_cors_middleware: bool = True
    log_queries: bool = True
    log_mutations: bool = True
    log_errors: bool = True
    log_performance: bool = True
    performance_threshold_ms: int = 1000
    enable_query_complexity_middleware: bool = True

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "MiddlewareSettings":
        """Create MiddlewareSettings from schema configuration."""
        from ..defaults import LIBRARY_DEFAULTS
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

        # No caching middleware in project

        return cls(**filtered_settings)


class BaseMiddleware:
    """Base class for GraphQL middleware."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = MiddlewareSettings.from_schema(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """
        Middleware resolve method.

        Args:
            next_resolver: Next resolver in the chain
            root: Root value
            info: GraphQL resolve info
            **kwargs: Additional arguments

        Returns:
            Resolver result
        """
        return next_resolver(root, info, **kwargs)


class AuthenticationMiddleware(BaseMiddleware):
    """Middleware for handling authentication."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.auth_manager = get_auth_manager(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Authenticate user and add to context."""
        if not self.settings.enable_authentication_middleware:
            return next_resolver(root, info, **kwargs)

        # Authenticate user if not already done
        if not hasattr(info.context, 'user'):
            user = self.auth_manager.authenticate_user(info.context)
            info.context.user = user

        return next_resolver(root, info, **kwargs)


class LoggingMiddleware(BaseMiddleware):
    """Middleware for logging GraphQL operations."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Log GraphQL operations."""
        if not self.settings.enable_logging_middleware:
            return next_resolver(root, info, **kwargs)

        operation_type = info.operation.operation.value if info.operation else "unknown"
        field_name = info.field_name

        # Log query/mutation start
        should_log = (
            (operation_type == "query" and self.settings.log_queries) or
            (operation_type == "mutation" and self.settings.log_mutations)
        )

        if should_log:
            user = getattr(info.context, 'user', AnonymousUser())
            user_id = user.id if hasattr(user, 'id') and user.id else "anonymous"

            logger.info(
                f"GraphQL {operation_type} started: {field_name} "
                f"(user: {user_id}, schema: {self.schema_name or 'default'})"
            )

        start_time = time.time()

        try:
            result = next_resolver(root, info, **kwargs)

            # Log successful completion
            if should_log:
                duration = (time.time() - start_time) * 1000
                logger.info(
                    f"GraphQL {operation_type} completed: {field_name} "
                    f"(duration: {duration:.2f}ms)"
                )

            return result

        except Exception as e:
            # Log errors
            if self.settings.log_errors:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    f"GraphQL {operation_type} failed: {field_name} "
                    f"(duration: {duration:.2f}ms, error: {str(e)})"
                )

            raise


class PerformanceMiddleware(BaseMiddleware):
    """Middleware for performance monitoring."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Monitor performance of GraphQL operations."""
        if not self.settings.enable_performance_middleware:
            return next_resolver(root, info, **kwargs)

        start_time = time.time()

        try:
            result = next_resolver(root, info, **kwargs)

            # Check performance threshold
            duration_ms = (time.time() - start_time) * 1000

            if duration_ms > self.settings.performance_threshold_ms and self.settings.log_performance:
                operation_type = info.operation.operation.value if info.operation else "unknown"
                field_name = info.field_name

                logger.warning(
                    f"Slow GraphQL {operation_type}: {field_name} "
                    f"(duration: {duration_ms:.2f}ms, threshold: {self.settings.performance_threshold_ms}ms)"
                )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"GraphQL operation failed after {duration_ms:.2f}ms: {str(e)}")
            raise


class RateLimitingMiddleware(BaseMiddleware):
    """Middleware for rate limiting."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.rate_limiter = get_rate_limiter(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Apply rate limiting to GraphQL operations."""
        if not self.settings.enable_rate_limiting_middleware:
            return next_resolver(root, info, **kwargs)

        # Check rate limits
        identifier = self.rate_limiter.get_client_identifier(info.context)

        if not self.rate_limiter.check_rate_limit(identifier, "minute"):
            raise PermissionError("Rate limit exceeded (per minute)")

        if not self.rate_limiter.check_rate_limit(identifier, "hour"):
            raise PermissionError("Rate limit exceeded (per hour)")

        return next_resolver(root, info, **kwargs)


## CachingMiddleware removed: caching is not supported in this project.


class ValidationMiddleware(BaseMiddleware):
    """Middleware for input validation."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.input_validator = get_input_validator(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Validate GraphQL inputs."""
        if not self.settings.enable_validation_middleware:
            return next_resolver(root, info, **kwargs)

        # Validate input arguments
        if kwargs:
            validation_errors = self.input_validator.validate_input(kwargs)
            if validation_errors:
                raise ValueError(f"Input validation failed: {'; '.join(validation_errors)}")

        return next_resolver(root, info, **kwargs)


class ErrorHandlingMiddleware(BaseMiddleware):
    """Middleware for error handling."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Handle and format GraphQL errors."""
        if not self.settings.enable_error_handling_middleware:
            return next_resolver(root, info, **kwargs)

        try:
            return next_resolver(root, info, **kwargs)

        except PermissionError as e:
            # Handle permission errors
            logger.warning(f"Permission denied: {str(e)}")
            raise

        except ValueError as e:
            # Handle validation errors
            logger.warning(f"Validation error: {str(e)}")
            raise

        except Exception as e:
            # Handle unexpected errors
            operation_type = info.operation.operation.value if info.operation else "unknown"
            field_name = info.field_name

            logger.error(
                f"Unexpected error in GraphQL {operation_type} {field_name}: {str(e)}",
                exc_info=True
            )

            # Re-raise the original exception
            raise


class QueryComplexityMiddleware(BaseMiddleware):
    """Middleware for query complexity analysis."""

    def __init__(self, schema_name: Optional[str] = None):
        super().__init__(schema_name)
        self.complexity_analyzer = get_complexity_analyzer(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Analyze and limit query complexity."""
        if not self.settings.enable_query_complexity_middleware:
            return next_resolver(root, info, **kwargs)

        # Only analyze queries
        operation_type = info.operation.operation.value if info.operation else "unknown"
        if operation_type != "query":
            return next_resolver(root, info, **kwargs)

        # Analyze query complexity
        query_string = str(info.operation)
        validation_errors = self.complexity_analyzer.validate_query_limits(query_string)

        if validation_errors:
            raise ValueError(f"Query complexity validation failed: {'; '.join(validation_errors)}")

        return next_resolver(root, info, **kwargs)


class CORSMiddleware(BaseMiddleware):
    """Middleware for CORS handling."""

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Handle CORS for GraphQL requests."""
        if not self.settings.enable_cors_middleware:
            return next_resolver(root, info, **kwargs)

        # CORS headers are typically handled at the HTTP level
        # This middleware can add additional CORS-related logic if needed

        return next_resolver(root, info, **kwargs)


# Default middleware stack
DEFAULT_MIDDLEWARE = [
    AuthenticationMiddleware,
    RateLimitingMiddleware,
    ValidationMiddleware,
    QueryComplexityMiddleware,
    CachingMiddleware,
    PerformanceMiddleware,
    LoggingMiddleware,
    ErrorHandlingMiddleware,
    CORSMiddleware,
]


def get_middleware_stack(schema_name: Optional[str] = None) -> List[BaseMiddleware]:
    """
    Get the middleware stack for a schema.

    Args:
        schema_name: Schema name (optional)

    Returns:
        List of middleware instances
    """
    middleware_stack = []

    for middleware_class in DEFAULT_MIDDLEWARE:
        middleware_instance = middleware_class(schema_name)
        middleware_stack.append(middleware_instance)

    return middleware_stack


def create_middleware_resolver(middleware_stack: List[BaseMiddleware]) -> Callable:
    """
    Create a resolver that applies middleware stack.

    Args:
        middleware_stack: List of middleware instances

    Returns:
        Middleware resolver function
    """
    def middleware_resolver(next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Apply middleware stack to resolver."""

        def apply_middleware(index: int) -> Any:
            if index >= len(middleware_stack):
                return next_resolver(root, info, **kwargs)

            middleware = middleware_stack[index]

            def next_middleware_resolver(r, i, **kw):
                return apply_middleware(index + 1)

            return middleware.resolve(next_middleware_resolver, root, info, **kwargs)

        return apply_middleware(0)

    return middleware_resolver

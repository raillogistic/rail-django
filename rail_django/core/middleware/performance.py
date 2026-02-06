"""
Performance middleware for Rail Django GraphQL.

This module provides middleware for performance monitoring, query complexity
analysis, and rate limiting for GraphQL operations.
"""

import logging
import time
from typing import Any, Callable, Optional

from graphql import DocumentNode

from .base import BaseMiddleware
from ..performance import get_complexity_analyzer
from ..services import get_rate_limiter

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseMiddleware):
    """Middleware for performance monitoring.

    This middleware tracks the execution time of GraphQL operations
    and logs warnings for operations that exceed the configured threshold.
    """

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Monitor performance of GraphQL operations.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.
        """
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


class QueryComplexityMiddleware(BaseMiddleware):
    """Middleware for query complexity analysis.

    This middleware analyzes the complexity of GraphQL queries and
    rejects queries that exceed configured limits for depth or complexity.
    """

    def __init__(self, schema_name: Optional[str] = None):
        """Initialize query complexity middleware.

        Args:
            schema_name: Optional schema name for schema-specific limits.
        """
        super().__init__(schema_name)
        self.complexity_analyzer = get_complexity_analyzer(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Analyze and limit query complexity.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.

        Raises:
            ValueError: If query complexity validation fails.
        """
        if not self.settings.enable_query_complexity_middleware:
            return next_resolver(root, info, **kwargs)

        # Only analyze queries
        operation_type = info.operation.operation.value if info.operation else "unknown"
        if operation_type != "query":
            return next_resolver(root, info, **kwargs)

        # Analyze query complexity
        query_string = str(info.operation)
        fragments = list(getattr(info, "fragments", {}).values())
        document = (
            DocumentNode(definitions=[info.operation] + fragments)
            if info.operation is not None
            else None
        )
        try:
            depth, complexity = self.complexity_analyzer.analyze_query(query_string)
            metrics = getattr(info.context, "_graphql_metrics", None)
            if metrics is not None:
                metrics.query_depth = depth
                metrics.query_complexity = complexity
        except Exception:
            pass
        validation_errors = self.complexity_analyzer.validate_query_limits(
            query_string,
            schema=getattr(info, "schema", None),
            document=document,
            user=getattr(getattr(info, "context", None), "user", None),
        )

        if validation_errors:
            raise ValueError(f"Query complexity validation failed: {'; '.join(validation_errors)}")

        return next_resolver(root, info, **kwargs)


class RateLimitingMiddleware(BaseMiddleware):
    """Middleware for rate limiting.

    This middleware enforces rate limits on GraphQL operations to prevent
    abuse and ensure fair resource usage.
    """

    def __init__(self, schema_name: Optional[str] = None):
        """Initialize rate limiting middleware.

        Args:
            schema_name: Optional schema name for schema-specific limits.
        """
        super().__init__(schema_name)
        self.rate_limiter = get_rate_limiter(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Apply rate limiting to GraphQL operations.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.

        Raises:
            PermissionError: If rate limit is exceeded.
        """
        if not self.settings.enable_rate_limiting_middleware:
            return next_resolver(root, info, **kwargs)

        if not self._is_root_field(info):
            return next_resolver(root, info, **kwargs)

        result = self.rate_limiter.check("graphql", request=info.context)
        if not result.allowed:
            raise PermissionError("Rate limit exceeded")

        if self._is_login_field(info):
            login_result = self.rate_limiter.check("graphql_login", request=info.context)
            if not login_result.allowed:
                raise PermissionError("Rate limit exceeded (login)")

        return next_resolver(root, info, **kwargs)

    @staticmethod
    def _is_root_field(info: Any) -> bool:
        """Check if this is a root field resolution."""
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _is_login_field(info: Any) -> bool:
        """Check if this is a login field."""
        field_name = getattr(info, "field_name", "") or ""
        return field_name.lower() == "login"

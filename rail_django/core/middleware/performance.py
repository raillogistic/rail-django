"""
Performance middleware for Rail Django GraphQL.

This module provides middleware for performance monitoring, query complexity
analysis, and rate limiting for GraphQL operations.
"""

import logging
import time
from typing import Any, Callable, Optional

from graphql import DocumentNode

from ...config_proxy import get_setting
from .base import BaseMiddleware
from ..performance import get_complexity_analyzer
from ..services import get_rate_limiter

logger = logging.getLogger(__name__)


def _normalize_query_selector_list(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return set()
    normalized: set[str] = set()
    for value in values:
        if value is None:
            continue
        item = str(value).strip().lower()
        if item:
            normalized.add(item)
    return normalized


class PerformanceMiddleware(BaseMiddleware):
    """Middleware for performance monitoring.

    This middleware tracks the execution time of **root-level** GraphQL
    operations only.  Nested/scalar field resolutions are passed through
    with zero overhead to avoid thousands of ``time.time()`` calls per
    request.
    """

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Monitor performance of root-level GraphQL operations.

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

        # ── Performance: skip nested fields (only measure root queries) ──
        path = getattr(info, "path", None)
        if path is not None and getattr(path, "prev", None) is not None:
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

        Only runs on **root-level** field resolutions to avoid redundant
        AST parsing on every nested field.

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

        # ── Performance: only analyze at root level ──
        path = getattr(info, "path", None)
        if path is not None and getattr(path, "prev", None) is not None:
            return next_resolver(root, info, **kwargs)

        # Only analyze queries
        operation_type = info.operation.operation.value if info.operation else "unknown"
        if operation_type != "query":
            return next_resolver(root, info, **kwargs)
        if not self._should_limit_query(info):
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

    def _should_limit_query(self, info: Any) -> bool:
        """Apply query limits only to queries explicitly listed in settings."""
        selectors = _normalize_query_selector_list(
            get_setting(
                "security_settings.limited_query_fields",
                [],
                schema_name=self.schema_name,
            )
        )
        if not selectors:
            return False

        field_name = str(getattr(info, "field_name", "") or "").strip().lower()
        operation = getattr(info, "operation", None)
        name_node = getattr(operation, "name", None)
        operation_name = ""
        if name_node and getattr(name_node, "value", None):
            operation_name = str(name_node.value).strip().lower()
        return field_name in selectors or operation_name in selectors


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

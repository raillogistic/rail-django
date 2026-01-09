"""
Compatibility wrapper for the legacy performance_middleware module.
"""

import logging
import time
from typing import Optional

from ..extensions.performance_metrics import performance_collector
from .performance import (
    GraphQLPerformanceMiddleware,
    GraphQLPerformanceView,
    get_performance_aggregator,
    monitor_performance,
    setup_performance_monitoring,
)

logger = logging.getLogger(__name__)


class GraphQLExecutionMiddleware:
    """GraphQL execution middleware to record per-field timing metrics."""

    def __init__(self):
        self.slow_query_threshold = 1.0

    def resolve(self, next_resolver, root, info, **args):
        start_time = time.time()

        try:
            result = next_resolver(root, info, **args)
            execution_time = time.time() - start_time

            if info.path and len(info.path.as_list()) == 1:
                self._record_field_metrics(info, execution_time)

            return result
        except Exception as exc:
            execution_time = time.time() - start_time
            if info.path and len(info.path.as_list()) == 1:
                self._record_field_metrics(info, execution_time, str(exc))
            raise

    def _record_field_metrics(
        self, info, execution_time: float, error_message: Optional[str] = None
    ):
        try:
            field_name = info.field_name
            query_text = f"query {{ {field_name} }}"

            user_id = None
            if hasattr(info.context, "user") and info.context.user.is_authenticated:
                user_id = str(info.context.user.id)

            performance_collector.record_query_execution(
                query_text=query_text,
                execution_time=execution_time,
                user_id=user_id,
                database_queries=0,
                cache_hits=0,
                cache_misses=0,
                memory_usage_mb=0.0,
                error_message=error_message,
            )
        except Exception as exc:
            logger.debug("Failed to record field metrics: %s", exc)


graphql_execution_middleware = GraphQLExecutionMiddleware()


def get_performance_middleware_config():
    """Return the recommended middleware configuration snippet."""
    return {
        "middleware_class": "rail_django.middleware.performance.GraphQLPerformanceMiddleware",
        "settings": {
            "GRAPHQL_PERFORMANCE_ENABLED": False,
            "GRAPHQL_SLOW_QUERY_THRESHOLD": 1.0,
            "GRAPHQL_PERFORMANCE_HEADERS": False,
        },
    }


__all__ = [
    "GraphQLPerformanceMiddleware",
    "GraphQLPerformanceView",
    "get_performance_aggregator",
    "setup_performance_monitoring",
    "monitor_performance",
    "GraphQLExecutionMiddleware",
    "graphql_execution_middleware",
    "get_performance_middleware_config",
]

"""
Performance monitor for tracking query execution metrics.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db import connection

from .config import QueryOptimizationConfig

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for query execution."""

    execution_time: float = 0.0
    query_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    complexity_score: int = 0
    memory_usage: int = 0


class PerformanceMonitor:
    """Monitors and tracks GraphQL query performance."""

    def __init__(self, config: QueryOptimizationConfig):
        self.config = config
        self.metrics: dict[str, list[PerformanceMetrics]] = defaultdict(list)

    def start_monitoring(self, query_name: str) -> dict[str, Any]:
        """Start monitoring a query execution."""
        if not self.config.enable_performance_monitoring:
            return {}

        return {
            "start_time": time.time(),
            "initial_query_count": len(connection.queries),
            "query_name": query_name,
        }

    def end_monitoring(self, context: dict[str, Any]) -> PerformanceMetrics:
        """End monitoring and record metrics."""
        if not self.config.enable_performance_monitoring or not context:
            return PerformanceMetrics()

        end_time = time.time()
        execution_time = end_time - context["start_time"]
        query_count = len(connection.queries) - context["initial_query_count"]

        metrics = PerformanceMetrics(
            execution_time=execution_time, query_count=query_count
        )

        # Store metrics
        query_name = context["query_name"]
        self.metrics[query_name].append(metrics)

        # Log slow queries
        if (
            self.config.log_slow_queries
            and execution_time > self.config.slow_query_threshold
        ):
            logger.warning(
                f"Slow query detected: {query_name} took {execution_time:.2f}s "
                f"with {query_count} database queries"
            )

        return metrics

    def record_query_performance(
        self,
        query_name: str,
        execution_time: float,
        cache_hit: bool = False,
        error: str = None,
        query_count: int = None,
    ) -> None:
        """Record query performance metrics."""
        if not self.config.enable_performance_monitoring:
            return

        # Create performance metrics
        metrics = PerformanceMetrics(
            execution_time=execution_time,
            query_count=query_count or 0,
            cache_hits=1 if cache_hit else 0,
            cache_misses=0 if cache_hit else 1,
        )

        # Store metrics
        self.metrics[query_name].append(metrics)

        # Log slow queries
        if (
            self.config.log_slow_queries
            and execution_time > self.config.slow_query_threshold
        ):
            logger.warning(
                f"Slow query detected: {query_name} took {execution_time:.2f}s"
                + (f" (cache hit)" if cache_hit else "")
                + (f" - Error: {error}" if error else "")
            )

        # Log errors
        if error:
            logger.error(f"xQuery error in {query_name}: {error}", exc_info=True)

    def get_performance_stats(self, query_name: str = None) -> dict[str, Any]:
        """Get performance statistics."""
        if query_name:
            query_metrics = self.metrics.get(query_name, [])
            if not query_metrics:
                return {}

            return {
                "query_name": query_name,
                "total_executions": len(query_metrics),
                "avg_execution_time": sum(m.execution_time for m in query_metrics)
                / len(query_metrics),
                "avg_query_count": sum(m.query_count for m in query_metrics)
                / len(query_metrics),
                "max_execution_time": max(m.execution_time for m in query_metrics),
                "min_execution_time": min(m.execution_time for m in query_metrics),
            }
        else:
            # Return overall stats
            all_metrics = []
            for metrics_list in self.metrics.values():
                all_metrics.extend(metrics_list)

            if not all_metrics:
                return {}

            return {
                "total_queries": len(all_metrics),
                "avg_execution_time": sum(m.execution_time for m in all_metrics)
                / len(all_metrics),
                "avg_query_count": sum(m.query_count for m in all_metrics)
                / len(all_metrics),
                "slow_queries": len(
                    [
                        m
                        for m in all_metrics
                        if m.execution_time > self.config.slow_query_threshold
                    ]
                ),
            }


_performance_monitor = PerformanceMonitor(QueryOptimizationConfig())
_monitor_by_schema: dict[str, PerformanceMonitor] = {}


def get_performance_monitor(schema_name: Optional[str] = None) -> PerformanceMonitor:
    """Get a performance monitor instance."""
    if not schema_name:
        return _performance_monitor

    if schema_name not in _monitor_by_schema:
        from .optimizer import _build_optimizer_config
        config = _build_optimizer_config(schema_name)
        _monitor_by_schema[schema_name] = PerformanceMonitor(config)

    return _monitor_by_schema[schema_name]

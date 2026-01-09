"""Compatibility wrapper for legacy media module (performance exports)."""

from ..middleware.performance import (
    GraphQLPerformanceMiddleware,
    GraphQLPerformanceView,
    PerformanceAggregator,
    PerformanceAlert,
    RequestMetrics,
    get_performance_aggregator,
    monitor_performance,
    setup_performance_monitoring,
)

__all__ = [
    "RequestMetrics",
    "PerformanceAlert",
    "PerformanceAggregator",
    "GraphQLPerformanceMiddleware",
    "GraphQLPerformanceView",
    "get_performance_aggregator",
    "setup_performance_monitoring",
    "monitor_performance",
]

"""
Performance monitoring middleware.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.middleware.performance` package.

DEPRECATION NOTICE:
    Importing from `rail_django.middleware.performance` module is deprecated.
    Please update your imports to use `rail_django.middleware.performance` package instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.middleware.performance' module is deprecated. "
    "Use 'rail_django.middleware.performance' package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .performance.aggregator import PerformanceAggregator, get_performance_aggregator
from .performance.collectors import QueryMetricsCollector
from .performance.metrics import PerformanceAlert, RequestMetrics
from .performance.middleware import GraphQLPerformanceMiddleware
from .performance.utils import monitor_performance, setup_performance_monitoring
from .performance.views import GraphQLPerformanceView

__all__ = [
    "GraphQLPerformanceMiddleware",
    "GraphQLPerformanceView",
    "RequestMetrics",
    "PerformanceAlert",
    "QueryMetricsCollector",
    "PerformanceAggregator",
    "get_performance_aggregator",
    "setup_performance_monitoring",
    "monitor_performance",
]
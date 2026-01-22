"""
Performance monitoring module.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.debugging.performance_monitor` package.

DEPRECATION NOTICE:
    Importing from `rail_django.debugging.performance_monitor` module is deprecated.
    Please update your imports to use `rail_django.debugging.performance_monitor` package instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.debugging.performance_monitor' module is deprecated. "
    "Use 'rail_django.debugging.performance_monitor' package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .performance_monitor.monitor import PerformanceMonitor
from .performance_monitor.types import (
    MetricType,
    PerformanceAlert,
    PerformanceMetric,
    PerformanceStats,
    PerformanceThreshold,
)

__all__ = [
    "PerformanceMonitor",
    "MetricType",
    "PerformanceMetric",
    "PerformanceThreshold",
    "PerformanceAlert",
    "PerformanceStats",
]
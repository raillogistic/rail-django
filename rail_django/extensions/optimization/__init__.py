"""
Performance Optimization System for Django GraphQL Auto-Generation.

This package provides comprehensive performance optimization features including
N+1 query prevention, complexity analysis, and performance monitoring.
"""

from .analyzer import QueryAnalysisResult, QueryAnalyzer
from .config import QueryOptimizationConfig
from .decorators import optimize_query
from .monitor import PerformanceMetrics, PerformanceMonitor, get_performance_monitor
from .optimizer import (
    QueryOptimizer,
    configure_optimization,
    get_optimizer,
)
from .cache import invalidate_query_cache

__all__ = [
    # Configuration
    "QueryOptimizationConfig",
    # Analyzer
    "QueryAnalyzer",
    "QueryAnalysisResult",
    # Optimizer
    "QueryOptimizer",
    "get_optimizer",
    "configure_optimization",
    # Monitor
    "PerformanceMonitor",
    "PerformanceMetrics",
    "get_performance_monitor",
    # Decorators
    "optimize_query",
    # Cache
    "invalidate_query_cache",
]

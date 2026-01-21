"""
Health Checks & Diagnostics System for Django GraphQL Auto

This package provides comprehensive health monitoring and diagnostics
for the GraphQL system including schema validation, database connectivity,
cache system status, and performance metrics.

Usage:
    from rail_django.extensions.health import (
        HealthChecker,
        health_checker,
        HealthQuery,
        PerformanceQuery,
        RefreshSchemaMutation,
    )

    # Use the global health checker instance
    report = health_checker.get_health_report()

    # Or create a custom instance
    checker = HealthChecker()
    metrics = checker.get_system_metrics()
"""

# Data types
from .types import (
    HealthStatus,
    HealthStatusValue,
    HealthThresholds,
    SystemMetrics,
)

# Health checker
from .checker import HealthChecker, health_checker

# GraphQL types
from .graphql_types import (
    CacheHealthType,
    ComponentHealthSummaryType,
    DatabaseHealthType,
    DetailedHealthReportType,
    HealthReportType,
    HealthStatusType,
    SystemMetricsType,
)

# GraphQL queries and mutations
from .queries import (
    HealthQuery,
    PerformanceQuery,
    RefreshSchemaMutation,
)

# Utility functions
from .utils import (
    count_active_connections,
    generate_recommendations,
    get_cache_info,
    get_database_info,
)

__all__ = [
    # Data types
    "HealthStatus",
    "HealthStatusValue",
    "HealthThresholds",
    "SystemMetrics",
    # Health checker
    "HealthChecker",
    "health_checker",
    # GraphQL types
    "CacheHealthType",
    "ComponentHealthSummaryType",
    "DatabaseHealthType",
    "DetailedHealthReportType",
    "HealthReportType",
    "HealthStatusType",
    "SystemMetricsType",
    # GraphQL queries and mutations
    "HealthQuery",
    "PerformanceQuery",
    "RefreshSchemaMutation",
    # Utility functions
    "count_active_connections",
    "generate_recommendations",
    "get_cache_info",
    "get_database_info",
]

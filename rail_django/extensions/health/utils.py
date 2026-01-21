"""
Utility functions for Health Checking

This module provides helper functions for database info retrieval,
cache info retrieval, and health recommendations generation.
"""

import logging
from typing import Any, Dict, List

from django.db import connections

from .types import HealthStatus, HealthThresholds, SystemMetrics

logger = logging.getLogger(__name__)


def get_database_info(conn, db_alias: str) -> Dict[str, Any]:
    """
    Get additional database information.

    Args:
        conn: Database connection object
        db_alias: Database alias name

    Returns:
        Dict containing database engine, version, and connection info
    """
    try:
        with conn.cursor() as cursor:
            engine = conn.settings_dict.get("ENGINE", "").lower()

            if "postgresql" in engine:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
                )
                active_connections = cursor.fetchone()[0]

                return {
                    "engine": "PostgreSQL",
                    "version": version,
                    "active_connections": active_connections,
                }
            elif "mysql" in engine:
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()[0]

                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                active_connections = cursor.fetchone()[1]

                return {
                    "engine": "MySQL",
                    "version": version,
                    "active_connections": int(active_connections),
                }
            else:
                return {"engine": "SQLite", "version": "Unknown"}

    except Exception as e:
        return {"error": str(e)}


def get_cache_info(cache_backend, cache_alias: str) -> Dict[str, Any]:
    """
    Get cache backend information.

    Args:
        cache_backend: Cache backend instance
        cache_alias: Cache alias name

    Returns:
        Dict containing cache backend type and alias
    """
    try:
        return {
            "backend": str(type(cache_backend).__name__),
            "alias": cache_alias,
        }
    except Exception as e:
        return {"error": str(e)}


def count_active_connections() -> int:
    """
    Count active database connections.

    Returns:
        int: Total number of active database connections
    """
    try:
        total_connections = 0
        for db_alias in connections:
            conn = connections[db_alias]
            if conn.connection is not None:
                total_connections += 1
        return total_connections
    except Exception:
        return 0


def generate_recommendations(
    statuses: List[HealthStatus], metrics: SystemMetrics
) -> List[str]:
    """
    Generate health recommendations based on current status.

    Args:
        statuses: List of component health statuses
        metrics: Current system metrics

    Returns:
        List of recommendation strings
    """
    recommendations = []

    # Check for unhealthy components
    unhealthy_components = [s for s in statuses if s.status == "unhealthy"]
    if unhealthy_components:
        recommendations.append(
            f"Critical: {len(unhealthy_components)} components are unhealthy "
            "and require immediate attention"
        )

    # Check CPU usage
    if metrics.cpu_usage_percent > HealthThresholds.CPU_WARNING:
        recommendations.append(
            "High CPU usage detected. Consider scaling or optimizing queries"
        )

    # Check memory usage
    if metrics.memory_usage_percent > HealthThresholds.MEMORY_WARNING:
        recommendations.append(
            "High memory usage detected. Monitor for memory leaks"
        )

    # Check disk usage
    if metrics.disk_usage_percent > HealthThresholds.DISK_WARNING:
        recommendations.append(
            "Disk space is running low. Clean up logs and temporary files"
        )

    # Check for slow components
    slow_components = [
        s for s in statuses
        if s.response_time_ms > HealthThresholds.RESPONSE_TIME_SLOW_MS
    ]
    if slow_components:
        recommendations.append(
            f"{len(slow_components)} components have slow response times (>1s)"
        )

    if not recommendations:
        recommendations.append(
            "All systems are operating within normal parameters"
        )

    return recommendations

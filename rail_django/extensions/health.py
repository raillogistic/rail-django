"""
Health Checks & Diagnostics System for Django GraphQL Auto

This module provides comprehensive health monitoring and diagnostics
for the GraphQL system including schema validation, database connectivity,
cache system status, and performance metrics.
"""

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psutil
from django.apps import apps
from django.conf import settings

# Cache monitoring disabled: remove Django cache imports
from django.db import connection, connections
from graphene import Boolean, Field, Float, Int
from graphene import List as GrapheneList
from graphene import ObjectType, String
import graphene
from graphql import build_schema, validate
from graphql.error import GraphQLError

from .performance_metrics import (
    ComplexityStatsType,
    PerformanceDistribution,
    PerformanceDistributionType,
    QueryFrequencyStats,
    QueryFrequencyStatsType,
    SlowQueryAlert,
    SlowQueryAlertType,
    performance_collector,
)

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Represents the health status of a system component."""

    component: str
    status: str  # 'healthy', 'degraded', 'unhealthy'
    message: str
    response_time_ms: float
    timestamp: datetime
    details: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class SystemMetrics:
    """System performance and resource metrics."""

    cpu_usage_percent: float
    memory_usage_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    active_connections: int
    cache_hit_rate: float
    uptime_seconds: float


class HealthChecker:
    """
    Comprehensive health checking system for GraphQL application.

    Provides health checks for:
    - GraphQL schema validation
    - Database connectivity
    - Cache system status
    - System resources
    - Performance metrics
    """

    def __init__(self):
        self.start_time = time.time()
        self._cache_stats = {"hits": 0, "misses": 0}

    def check_schema_health(self) -> HealthStatus:
        """
        Check GraphQL schema health and validation.

        Returns:
            HealthStatus: Schema health status with validation results
        """
        start_time = time.time()

        try:
            from rail_django.core.schema import get_schema

            # Get the current schema
            schema = get_schema()

            if not schema:
                return HealthStatus(
                    component="schema",
                    status="unhealthy",
                    message="GraphQL schema not found or not initialized",
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now(timezone.utc),
                )

            # Validate schema structure
            try:
                # Test introspection query
                introspection_query = """
                query IntrospectionQuery {
                    __schema {
                        types {
                            name
                        }
                    }
                }
                """

                result = schema.execute(introspection_query)

                if result.errors:
                    return HealthStatus(
                        component="schema",
                        status="degraded",
                        message=f"Schema validation errors: {[str(e) for e in result.errors]}",
                        response_time_ms=(time.time() - start_time) * 1000,
                        timestamp=datetime.now(timezone.utc),
                        details={"errors": [str(e) for e in result.errors]},
                    )

                # Count types and fields
                type_count = len(result.data["__schema"]["types"])

                return HealthStatus(
                    component="schema",
                    status="healthy",
                    message=f"Schema validation successful with {type_count} types",
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now(timezone.utc),
                    details={"type_count": type_count},
                )

            except Exception as e:
                return HealthStatus(
                    component="schema",
                    status="unhealthy",
                    message=f"Schema validation failed: {str(e)}",
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now(timezone.utc),
                    details={"error": str(e)},
                )

        except Exception as e:
            return HealthStatus(
                component="schema",
                status="unhealthy",
                message=f"Schema health check failed: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now(timezone.utc),
                details={"error": str(e)},
            )

    def check_database_health(self) -> List[HealthStatus]:
        """
        Check database connectivity and performance for all configured databases.

        Returns:
            List[HealthStatus]: Health status for each database connection
        """
        health_statuses = []

        for db_alias in connections:
            start_time = time.time()

            try:
                conn = connections[db_alias]

                # Test basic connectivity
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()

                if result and result[0] == 1:
                    # Get additional database info
                    db_info = self._get_database_info(conn, db_alias)

                    health_statuses.append(
                        HealthStatus(
                            component=f"database_{db_alias}",
                            status="healthy",
                            message=f"Database {db_alias} connection successful",
                            response_time_ms=(time.time() - start_time) * 1000,
                            timestamp=datetime.now(timezone.utc),
                            details=db_info,
                        )
                    )
                else:
                    health_statuses.append(
                        HealthStatus(
                            component=f"database_{db_alias}",
                            status="unhealthy",
                            message=f"Database {db_alias} query returned unexpected result",
                            response_time_ms=(time.time() - start_time) * 1000,
                            timestamp=datetime.now(timezone.utc),
                        )
                    )

            except Exception as e:
                health_statuses.append(
                    HealthStatus(
                        component=f"database_{db_alias}",
                        status="unhealthy",
                        message=f"Database {db_alias} connection failed: {str(e)}",
                        response_time_ms=(time.time() - start_time) * 1000,
                        timestamp=datetime.now(timezone.utc),
                        details={"error": str(e)},
                    )
                )

        return health_statuses

    def check_cache_health(self) -> List[HealthStatus]:
        """
        Check cache system health for all configured caches.

        Returns:
            List[HealthStatus]: Health status for each cache backend
        """
        # Cache health checks disabled; return empty list to avoid misleading status
        return []

    def get_system_metrics(self) -> SystemMetrics:
        """
        Get comprehensive system performance metrics.

        Returns:
            SystemMetrics: Current system resource usage and performance data
        """
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            memory_available_mb = memory.available / (1024 * 1024)

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100

            # Database connections
            active_connections = self._count_active_connections()

            # Cache hit rate disabled
            cache_hit_rate = 0.0

            # Uptime
            uptime_seconds = time.time() - self.start_time

            return SystemMetrics(
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                memory_available_mb=memory_available_mb,
                disk_usage_percent=disk_percent,
                active_connections=active_connections,
                cache_hit_rate=cache_hit_rate,
                uptime_seconds=uptime_seconds,
            )

        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            # Return default metrics on error
            return SystemMetrics(
                cpu_usage_percent=0.0,
                memory_usage_percent=0.0,
                memory_used_mb=0.0,
                memory_available_mb=0.0,
                disk_usage_percent=0.0,
                active_connections=0,
                cache_hit_rate=0.0,
                uptime_seconds=time.time() - self.start_time,
            )

    def get_comprehensive_health_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive health report for all system components.

        Returns:
            Dict[str, Any]: Complete health report with all components and metrics
        """
        report_start_time = time.time()

        # Collect all health checks
        schema_health = self.check_schema_health()
        database_health = self.check_database_health()
        cache_health = self.check_cache_health()
        system_metrics = self.get_system_metrics()

        # Determine overall system health
        all_statuses = [schema_health] + database_health + cache_health

        healthy_count = sum(1 for status in all_statuses if status.status == "healthy")
        degraded_count = sum(
            1 for status in all_statuses if status.status == "degraded"
        )
        unhealthy_count = sum(
            1 for status in all_statuses if status.status == "unhealthy"
        )

        if unhealthy_count > 0:
            overall_status = "unhealthy"
        elif degraded_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        return {
            "overall_status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "report_generation_time_ms": (time.time() - report_start_time) * 1000,
            "summary": {
                "total_components": len(all_statuses),
                "healthy": healthy_count,
                "degraded": degraded_count,
                "unhealthy": unhealthy_count,
            },
            "components": {
                "schema": schema_health.to_dict(),
                "databases": [status.to_dict() for status in database_health],
                "caches": [status.to_dict() for status in cache_health],
            },
            "system_metrics": asdict(system_metrics),
            "recommendations": self._generate_recommendations(
                all_statuses, system_metrics
            ),
        }

    def get_health_report(self) -> Dict[str, Any]:
        """

        Purpose: Provide a backward-compatible health report wrapper.

        Args: None

        Returns: Dict[str, Any]: Health report with top-level component counters for
            healthy_components, degraded_components, and unhealthy_components to
            maintain compatibility with existing views/tests.

        Raises: None

        Example:
            >>> checker = HealthChecker()
            >>> report = checker.get_health_report()
            >>> isinstance(report, dict)
            True
        """
        try:
            comprehensive = self.get_comprehensive_health_report()

            summary = comprehensive.get("summary", {})
            # Map summary counters to top-level keys expected by legacy callers
            return {
                "overall_status": comprehensive.get("overall_status"),
                "timestamp": comprehensive.get("timestamp"),
                "report_generation_time_ms": comprehensive.get(
                    "report_generation_time_ms"
                ),
                "healthy_components": summary.get("healthy", 0),
                "degraded_components": summary.get("degraded", 0),
                "unhealthy_components": summary.get("unhealthy", 0),
                "total_components": summary.get("total_components", 0),
                "components": comprehensive.get("components", {}),
                "system_metrics": comprehensive.get("system_metrics", {}),
                "recommendations": comprehensive.get("recommendations", []),
            }
        except Exception as e:
            logger.error(f"Failed to generate health report: {e}")
            # Provide a minimal fallback structure
            return {
                "overall_status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "report_generation_time_ms": 0.0,
                "healthy_components": 0,
                "degraded_components": 0,
                "unhealthy_components": 1,
                "total_components": 1,
                "components": {"schema": {}, "databases": [], "caches": []},
                "system_metrics": asdict(self.get_system_metrics()),
                "recommendations": [
                    "Health report generation failed; check system logs for details"
                ],
            }

    def _get_database_info(self, conn, db_alias: str) -> Dict[str, Any]:
        """Get additional database information."""
        try:
            with conn.cursor() as cursor:
                # Get database version and basic stats
                if "postgresql" in conn.settings_dict.get("ENGINE", "").lower():
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
                elif "mysql" in conn.settings_dict.get("ENGINE", "").lower():
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

    def _get_cache_info(self, cache_backend, cache_alias: str) -> Dict[str, Any]:
        """Get cache backend information."""
        try:
            cache_info = {
                "backend": str(type(cache_backend).__name__),
                "alias": cache_alias,
            }

            # Try to get Redis info if available
            if hasattr(cache_backend, "_cache") and hasattr(
                cache_backend._cache, "info"
            ):
                redis_info = cache_backend._cache.info()
                cache_info.update(
                    {
                        "redis_version": redis_info.get("redis_version"),
                        "used_memory": redis_info.get("used_memory_human"),
                        "connected_clients": redis_info.get("connected_clients"),
                        "keyspace_hits": redis_info.get("keyspace_hits", 0),
                        "keyspace_misses": redis_info.get("keyspace_misses", 0),
                    }
                )

            return cache_info

        except Exception as e:
            return {"error": str(e)}

    def _count_active_connections(self) -> int:
        """Count active database connections."""
        try:
            total_connections = 0
            for db_alias in connections:
                conn = connections[db_alias]
                if conn.connection is not None:
                    total_connections += 1
            return total_connections
        except Exception:
            return 0

    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        # Cache metrics disabled: always return 0.0
        return 0.0

    def _generate_recommendations(
        self, statuses: List[HealthStatus], metrics: SystemMetrics
    ) -> List[str]:
        """Generate health recommendations based on current status."""
        recommendations = []

        # Check for unhealthy components
        unhealthy_components = [s for s in statuses if s.status == "unhealthy"]
        if unhealthy_components:
            recommendations.append(
                f"Critical: {len(unhealthy_components)} components are unhealthy and require immediate attention"
            )

        # Check system resources
        if metrics.cpu_usage_percent > 80:
            recommendations.append(
                "High CPU usage detected. Consider scaling or optimizing queries"
            )

        if metrics.memory_usage_percent > 85:
            recommendations.append(
                "High memory usage detected. Monitor for memory leaks"
            )

        if metrics.disk_usage_percent > 90:
            recommendations.append(
                "Disk space is running low. Clean up logs and temporary files"
            )

        # Cache performance recommendations disabled

        # Check response times
        slow_components = [s for s in statuses if s.response_time_ms > 1000]
        if slow_components:
            recommendations.append(
                f"{len(slow_components)} components have slow response times (>1s)"
            )

        if not recommendations:
            recommendations.append("All systems are operating within normal parameters")

        return recommendations


# Global health checker instance
health_checker = HealthChecker()


# GraphQL Types for Health Monitoring
class HealthStatusType(ObjectType):
    """GraphQL type for health status information."""

    component = String()
    status = String()
    message = String()
    response_time_ms = Float()
    timestamp = String()


class SystemMetricsType(ObjectType):
    """GraphQL type for system metrics."""

    cpu_usage_percent = Float()
    memory_usage_percent = Float()
    memory_used_mb = Float()
    memory_available_mb = Float()
    disk_usage_percent = Float()
    active_connections = Int()
    cache_hit_rate = Float()
    uptime_seconds = Float()


class HealthReportType(ObjectType):
    """GraphQL type for comprehensive health report."""

    overall_status = String()
    timestamp = String()
    report_generation_time_ms = Float()
    healthy_components = Int()
    degraded_components = Int()
    unhealthy_components = Int()
    recommendations = GrapheneList(String)


class PerformanceQuery(ObjectType):
    """GraphQL queries for advanced performance monitoring."""

    execution_time_distribution = Field(
        PerformanceDistributionType,
        time_window_minutes=Int(default_value=60),
        description="Get query execution time distribution (p95, p99, etc.)",
    )

    most_frequent_queries = Field(
        GrapheneList(QueryFrequencyStatsType),
        limit=Int(default_value=10),
        description="Get most frequently executed queries",
    )

    slowest_queries = Field(
        GrapheneList(QueryFrequencyStatsType),
        limit=Int(default_value=10),
        description="Get slowest queries by average execution time",
    )

    recent_slow_queries = Field(
        GrapheneList(SlowQueryAlertType),
        limit=Int(default_value=20),
        description="Get recent slow query alerts",
    )

    complexity_stats = Field(
        ComplexityStatsType, description="Get query complexity and depth statistics"
    )

    def resolve_execution_time_distribution(
        self, info, time_window_minutes=60, **kwargs
    ):
        """Resolve query execution time distribution."""
        try:
            distribution = performance_collector.get_execution_time_distribution(
                time_window_minutes
            )
            return PerformanceDistributionType(
                p50=distribution.p50,
                p75=distribution.p75,
                p90=distribution.p90,
                p95=distribution.p95,
                p99=distribution.p99,
                min_time=distribution.min_time,
                max_time=distribution.max_time,
                avg_time=distribution.avg_time,
                total_requests=distribution.total_requests,
            )
        except Exception as e:
            logger.error(f"Execution time distribution query failed: {e}")
            return PerformanceDistributionType()

    def resolve_most_frequent_queries(self, info, limit=10, **kwargs):
        """Resolve most frequently executed queries."""
        try:
            queries = performance_collector.get_most_frequent_queries(limit)
            return [
                QueryFrequencyStatsType(
                    query_hash=q.query_hash,
                    query_name=q.query_name,
                    query_text=q.query_text[:500] + "..."
                    if len(q.query_text) > 500
                    else q.query_text,
                    call_count=q.call_count,
                    avg_execution_time=q.avg_execution_time,
                    min_execution_time=q.min_execution_time,
                    max_execution_time=q.max_execution_time,
                    last_executed=q.last_executed.isoformat()
                    if q.last_executed
                    else None,
                    error_count=q.error_count,
                    success_rate=q.success_rate,
                )
                for q in queries
            ]
        except Exception as e:
            logger.error(f"Most frequent queries query failed: {e}")
            return []

    def resolve_slowest_queries(self, info, limit=10, **kwargs):
        """Resolve slowest queries by average execution time."""
        try:
            queries = performance_collector.get_slowest_queries(limit)

            return [
                QueryFrequencyStatsType(
                    query_hash=q.query_hash,
                    query_name=q.query_name,
                    query_text=q.query_text[:500] + "..."
                    if len(q.query_text) > 500
                    else q.query_text,
                    call_count=q.call_count,
                    avg_execution_time=q.avg_execution_time,
                    min_execution_time=q.min_execution_time,
                    max_execution_time=q.max_execution_time,
                    last_executed=q.last_executed.isoformat()
                    if q.last_executed
                    else None,
                    error_count=q.error_count,
                    success_rate=q.success_rate,
                )
                for q in queries
            ]
        except Exception as e:
            logger.error(f"Slowest queries query failed: {e}")
            return []

    def resolve_recent_slow_queries(self, info, limit=20, **kwargs):
        """Resolve recent slow query alerts."""
        try:
            alerts = performance_collector.get_recent_slow_queries(limit)
            return [
                SlowQueryAlertType(
                    query_hash=alert.query_hash,
                    query_name=alert.query_name,
                    execution_time=alert.execution_time,
                    threshold=alert.threshold,
                    timestamp=alert.timestamp.isoformat(),
                    user_id=alert.user_id,
                    query_complexity=alert.query_complexity,
                    database_queries=alert.database_queries,
                )
                for alert in alerts
            ]
        except Exception as e:
            logger.error(f"Recent slow queries query failed: {e}")
            return []

    def resolve_complexity_stats(self, info, **kwargs):
        """Resolve query complexity statistics."""
        try:
            stats = performance_collector.get_complexity_stats()
            if not stats:
                return ComplexityStatsType()

            return ComplexityStatsType(
                avg_complexity=stats.get("avg_complexity", 0.0),
                max_complexity=stats.get("max_complexity", 0),
                avg_depth=stats.get("avg_depth", 0.0),
                max_depth=stats.get("max_depth", 0),
                complex_queries_count=stats.get("complex_queries_count", 0),
                deep_queries_count=stats.get("deep_queries_count", 0),
            )
        except Exception as e:
            logger.error(f"Complexity stats query failed: {e}")
            return ComplexityStatsType()


class HealthQuery(ObjectType):
    """GraphQL queries for health monitoring."""

    health_status = Field(
        HealthReportType, description="Get comprehensive system health report"
    )
    schema_health = Field(
        HealthStatusType, description="Get GraphQL schema health status"
    )
    system_metrics = Field(
        SystemMetricsType, description="Get current system performance metrics"
    )

    # Intégration des métriques de performance avancées
    performance = Field(
        PerformanceQuery, description="Advanced performance monitoring queries"
    )

    def resolve_performance(self, info, **kwargs):
        """Resolve performance monitoring queries."""
        return PerformanceQuery()

    def resolve_health_status(self, info, **kwargs):
        """Resolve comprehensive health report."""
        try:
            report = health_checker.get_comprehensive_health_report()

            return HealthReportType(
                overall_status=report["overall_status"],
                timestamp=report["timestamp"],
                report_generation_time_ms=report["report_generation_time_ms"],
                healthy_components=report["summary"]["healthy"],
                degraded_components=report["summary"]["degraded"],
                unhealthy_components=report["summary"]["unhealthy"],
                recommendations=report["recommendations"],
            )
        except Exception as e:
            logger.error(f"Health status query failed: {e}")
            return HealthReportType(
                overall_status="unhealthy",
                timestamp=datetime.now(timezone.utc).isoformat(),
                report_generation_time_ms=0.0,
                healthy_components=0,
                degraded_components=0,
                unhealthy_components=1,
                recommendations=[f"Health check system error: {str(e)}"],
            )

    def resolve_schema_health(self, info, **kwargs):
        """Resolve schema health status."""
        try:
            status = health_checker.check_schema_health()
            return HealthStatusType(
                component=status.component,
                status=status.status,
                message=status.message,
                response_time_ms=status.response_time_ms,
                timestamp=status.timestamp.isoformat(),
            )
        except Exception as e:
            logger.error(f"Schema health query failed: {e}")
            return HealthStatusType(
                component="schema",
                status="unhealthy",
                message=f"Schema health check failed: {str(e)}",
                response_time_ms=0.0,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def resolve_system_metrics(self, info, **kwargs):
        """Resolve system performance metrics."""
        try:
            metrics = health_checker.get_system_metrics()
            return SystemMetricsType(
                cpu_usage_percent=metrics.cpu_usage_percent,
                memory_usage_percent=metrics.memory_usage_percent,
                memory_used_mb=metrics.memory_used_mb,
                memory_available_mb=metrics.memory_available_mb,
                disk_usage_percent=metrics.disk_usage_percent,
                active_connections=metrics.active_connections,
                cache_hit_rate=metrics.cache_hit_rate,
                uptime_seconds=metrics.uptime_seconds,
            )
        except Exception as e:
            logger.error(f"System metrics query failed: {e}")
            return SystemMetricsType(
                cpu_usage_percent=0.0,
                memory_usage_percent=0.0,
                memory_used_mb=0.0,
                memory_available_mb=0.0,
                disk_usage_percent=0.0,
                active_connections=0,
                cache_hit_rate=0.0,
                uptime_seconds=0.0,
            )


class RefreshSchemaMutation(graphene.Mutation):
    """
    Purpose: Allow authorized clients to refresh/rebuild the GraphQL schema and optionally
        invalidate/warm metadata caches.
    Args:
        schema_name (str): Target schema name, defaults to "default".
        app_label (Optional[str]): If provided, reload schema only for the specified app.
        clear_cache (bool): When true, invalidate metadata caches.
        warm_metadata (bool): When true, warm model metadata cache after refresh.
    Returns:
        success (bool): True if the operation succeeded.
        message (str): Human-readable status message.
        schema_version (int): New schema version after refresh.
        apps_reloaded (List[str]): List of app labels reloaded.
    Raises:
        GraphQLError: If the user is not authorized or on unexpected errors.
    Example:
        >>> # Mutation
        >>> mutation {
        ...   refresh_schema(schemaName: "default", clearCache: true, warmMetadata: true) {
        ...     success
        ...     message
        ...     schemaVersion
        ...   }
        ... }
    """

    class Arguments:
        schema_name = String(required=False, default_value="default")
        app_label = String(required=False)
        clear_cache = Boolean(required=False, default_value=False)
        warm_metadata = Boolean(required=False, default_value=False)

    success = Boolean()
    message = String()
    schema_version = Int()
    apps_reloaded = GrapheneList(String)

    @staticmethod
    def mutate(
        root,
        info,
        schema_name: str = "default",
        app_label: Optional[str] = None,
        clear_cache: bool = False,
        warm_metadata: bool = False,
    ):
        """
        Purpose: Execute schema refresh with optional app scoping and cache operations.
        Args: See class Args.
        Returns: RefreshSchemaMutation: Mutation payload with status and version.
        Raises: GraphQLError on permission or operational errors.
        Example:
            >>> # See class docstring for usage example
        """
        try:
            user = getattr(info.context, "user", None)
            if (
                not user
                or not getattr(user, "is_authenticated", False)
                or not getattr(user, "is_staff", False)
            ):
                raise GraphQLError(
                    "Permission denied: staff authentication required to refresh schema"
                )

            # Perform schema refresh
            from ..core.schema import get_schema_builder

            builder = get_schema_builder(schema_name)

            apps_reloaded: List[str] = []
            if app_label:
                builder.reload_app_schema(app_label)
                apps_reloaded = [app_label]
            else:
                builder.rebuild_schema()

            new_version = builder.get_schema_version()

            # Optional cache invalidation
            if clear_cache:
                try:
                    from .metadata import invalidate_metadata_cache

                    invalidate_metadata_cache(model_name=None, app_name=app_label)
                except Exception as cache_err:
                    logger.warning(f"Cache invalidation failed: {cache_err}")

            # Optional cache warm-up (metadata)
            if warm_metadata:
                try:
                    from .metadata import warm_metadata_cache

                    warm_metadata_cache(app_name=app_label, model_name=None, user=user)
                except Exception as warm_err:
                    logger.warning(f"Metadata warm-up failed: {warm_err}")

            message = f"Schema refreshed for schema '{schema_name}'" + (
                f", app '{app_label}' reloaded" if app_label else ""
            )
            return RefreshSchemaMutation(
                success=True,
                message=message,
                schema_version=new_version,
                apps_reloaded=apps_reloaded,
            )
        except GraphQLError:
            # Re-raise expected GraphQL errors
            raise
        except Exception as e:
            logger.error(f"Schema refresh failed: {e}", exc_info=True)
            raise GraphQLError(f"Schema refresh failed: {e}")

"""
GraphQL Queries and Mutations for Health Monitoring

This module provides GraphQL query and mutation types for health monitoring,
performance metrics, and schema management operations.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import graphene
from graphene import Boolean, Field, Int, ObjectType, String
from graphene import List as GrapheneList
from graphql.error import GraphQLError

from ..performance_metrics import (
    ComplexityStatsType,
    PerformanceDistributionType,
    QueryFrequencyStatsType,
    SlowQueryAlertType,
    performance_collector,
)
from .checker import health_checker
from .graphql_types import HealthReportType, HealthStatusType, SystemMetricsType

logger = logging.getLogger(__name__)


class PerformanceQuery(ObjectType):
    """
    GraphQL queries for advanced performance monitoring.

    Provides access to query execution statistics, performance distribution,
    slow query alerts, and complexity analysis.
    """

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
        ComplexityStatsType,
        description="Get query complexity and depth statistics",
    )

    def resolve_execution_time_distribution(
        self, info, time_window_minutes: int = 60, **kwargs
    ):
        """
        Resolve query execution time distribution.

        Args:
            info: GraphQL resolve info
            time_window_minutes: Time window for statistics in minutes

        Returns:
            PerformanceDistributionType with percentile data
        """
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

    def resolve_most_frequent_queries(self, info, limit: int = 10, **kwargs):
        """
        Resolve most frequently executed queries.

        Args:
            info: GraphQL resolve info
            limit: Maximum number of queries to return

        Returns:
            List of QueryFrequencyStatsType ordered by call count
        """
        try:
            queries = performance_collector.get_most_frequent_queries(limit)
            return [
                QueryFrequencyStatsType(
                    query_hash=q.query_hash,
                    query_name=q.query_name,
                    query_text=(
                        q.query_text[:500] + "..."
                        if len(q.query_text) > 500
                        else q.query_text
                    ),
                    call_count=q.call_count,
                    avg_execution_time=q.avg_execution_time,
                    min_execution_time=q.min_execution_time,
                    max_execution_time=q.max_execution_time,
                    last_executed=(
                        q.last_executed.isoformat() if q.last_executed else None
                    ),
                    error_count=q.error_count,
                    success_rate=q.success_rate,
                )
                for q in queries
            ]
        except Exception as e:
            logger.error(f"Most frequent queries query failed: {e}")
            return []

    def resolve_slowest_queries(self, info, limit: int = 10, **kwargs):
        """
        Resolve slowest queries by average execution time.

        Args:
            info: GraphQL resolve info
            limit: Maximum number of queries to return

        Returns:
            List of QueryFrequencyStatsType ordered by average execution time
        """
        try:
            queries = performance_collector.get_slowest_queries(limit)

            return [
                QueryFrequencyStatsType(
                    query_hash=q.query_hash,
                    query_name=q.query_name,
                    query_text=(
                        q.query_text[:500] + "..."
                        if len(q.query_text) > 500
                        else q.query_text
                    ),
                    call_count=q.call_count,
                    avg_execution_time=q.avg_execution_time,
                    min_execution_time=q.min_execution_time,
                    max_execution_time=q.max_execution_time,
                    last_executed=(
                        q.last_executed.isoformat() if q.last_executed else None
                    ),
                    error_count=q.error_count,
                    success_rate=q.success_rate,
                )
                for q in queries
            ]
        except Exception as e:
            logger.error(f"Slowest queries query failed: {e}")
            return []

    def resolve_recent_slow_queries(self, info, limit: int = 20, **kwargs):
        """
        Resolve recent slow query alerts.

        Args:
            info: GraphQL resolve info
            limit: Maximum number of alerts to return

        Returns:
            List of SlowQueryAlertType for recent slow queries
        """
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
        """
        Resolve query complexity statistics.

        Args:
            info: GraphQL resolve info

        Returns:
            ComplexityStatsType with complexity and depth statistics
        """
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
    """
    GraphQL queries for health monitoring.

    Provides access to system health status, schema health, system metrics,
    and advanced performance monitoring.
    """

    health_status = Field(
        HealthReportType,
        description="Get comprehensive system health report",
    )
    schema_health = Field(
        HealthStatusType,
        description="Get GraphQL schema health status",
    )
    system_metrics = Field(
        SystemMetricsType,
        description="Get current system performance metrics",
    )
    performance = Field(
        PerformanceQuery,
        description="Advanced performance monitoring queries",
    )

    def resolve_performance(self, info, **kwargs):
        """
        Resolve performance monitoring queries.

        Returns:
            PerformanceQuery instance for nested performance queries
        """
        return PerformanceQuery()

    def resolve_health_status(self, info, **kwargs):
        """
        Resolve comprehensive health report.

        Args:
            info: GraphQL resolve info

        Returns:
            HealthReportType with overall system health status
        """
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
        """
        Resolve schema health status.

        Args:
            info: GraphQL resolve info

        Returns:
            HealthStatusType with schema validation results
        """
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
        """
        Resolve system performance metrics.

        Args:
            info: GraphQL resolve info

        Returns:
            SystemMetricsType with current system resource usage
        """
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
                collection_time_ms=metrics.collection_time_ms,
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
                collection_time_ms=0.0,
            )


class RefreshSchemaMutation(graphene.Mutation):
    """
    Mutation to refresh/rebuild the GraphQL schema.

    Allows authorized staff users to trigger a schema refresh and optionally
    invalidate or warm metadata caches.

    Arguments:
        schema_name: Target schema name, defaults to "default"
        app_label: If provided, reload schema only for the specified app
        clear_cache: When true, invalidate metadata caches
        warm_metadata: When true, warm model metadata cache after refresh

    Returns:
        success: True if the operation succeeded
        message: Human-readable status message
        schema_version: New schema version after refresh
        apps_reloaded: List of app labels reloaded

    Raises:
        GraphQLError: If the user is not authorized or on unexpected errors

    Example:
        >>> # Mutation
        >>> mutation {
        ...   refreshSchema(schemaName: "default", clearCache: true) {
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

    success = Boolean(description="True if the operation succeeded")
    message = String(description="Human-readable status message")
    schema_version = Int(description="New schema version after refresh")
    apps_reloaded = GrapheneList(String, description="List of app labels reloaded")

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
        Execute schema refresh with optional app scoping and cache operations.

        Args:
            root: GraphQL root value
            info: GraphQL resolve info containing request context
            schema_name: Target schema name
            app_label: Optional app label to scope refresh
            clear_cache: Whether to invalidate metadata caches
            warm_metadata: Whether to warm metadata cache after refresh

        Returns:
            RefreshSchemaMutation: Mutation payload with status and version

        Raises:
            GraphQLError: On permission or operational errors
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

            from rail_django.core.schema import get_schema_builder

            builder = get_schema_builder(schema_name)

            apps_reloaded: list[str] = []
            if app_label:
                builder.reload_app_schema(app_label)
                apps_reloaded = [app_label]
            else:
                builder.rebuild_schema()

            new_version = builder.get_schema_version()

            if clear_cache:
                try:
                    from ..metadata import invalidate_metadata_cache

                    invalidate_metadata_cache(model_name=None, app_name=app_label)
                except Exception as cache_err:
                    logger.warning(f"Cache invalidation failed: {cache_err}")

            if warm_metadata:
                try:
                    from ..metadata import warm_metadata_cache

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
            raise
        except Exception as e:
            logger.error(f"Schema refresh failed: {e}", exc_info=True)
            raise GraphQLError(f"Schema refresh failed: {e}")

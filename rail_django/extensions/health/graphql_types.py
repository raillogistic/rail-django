"""
GraphQL Types for Health Monitoring

This module defines the GraphQL object types used to expose health status,
system metrics, and health reports through the GraphQL API.
"""

from graphene import Float, Int, ObjectType, String
from graphene import List as GrapheneList


class HealthStatusType(ObjectType):
    """
    GraphQL type for health status information.

    Represents the health status of a single system component.

    Fields:
        component: Name of the component being monitored
        status: Health status ('healthy', 'degraded', 'unhealthy')
        message: Human-readable status message
        response_time_ms: Time taken to check this component in milliseconds
        timestamp: ISO-formatted timestamp of when the check was performed
    """

    component = String(description="Name of the component being monitored")
    status = String(description="Health status: healthy, degraded, or unhealthy")
    message = String(description="Human-readable status message")
    response_time_ms = Float(description="Time taken to check component in ms")
    timestamp = String(description="ISO-formatted timestamp of the health check")


class SystemMetricsType(ObjectType):
    """
    GraphQL type for system metrics.

    Exposes current system resource usage and performance data.

    Fields:
        cpu_usage_percent: Current CPU usage percentage (0-100)
        memory_usage_percent: Current memory usage percentage (0-100)
        memory_used_mb: Amount of memory used in megabytes
        memory_available_mb: Amount of memory available in megabytes
        disk_usage_percent: Disk usage percentage (0-100)
        active_connections: Number of active database connections
        cache_hit_rate: Cache hit rate as a ratio (0.0-1.0)
        uptime_seconds: Application uptime in seconds
        collection_time_ms: Time taken to collect metrics in milliseconds
    """

    cpu_usage_percent = Float(description="Current CPU usage percentage (0-100)")
    memory_usage_percent = Float(description="Current memory usage percentage (0-100)")
    memory_used_mb = Float(description="Amount of memory used in megabytes")
    memory_available_mb = Float(description="Amount of memory available in megabytes")
    disk_usage_percent = Float(description="Disk usage percentage (0-100)")
    active_connections = Int(description="Number of active database connections")
    cache_hit_rate = Float(description="Cache hit rate as a ratio (0.0-1.0)")
    uptime_seconds = Float(description="Application uptime in seconds")
    collection_time_ms = Float(description="Time taken to collect metrics in ms")


class HealthReportType(ObjectType):
    """
    GraphQL type for comprehensive health report.

    Provides an overview of system health including all component statuses,
    summary counts, and recommendations.

    Fields:
        overall_status: Overall system health status
        timestamp: ISO-formatted timestamp of the report
        report_generation_time_ms: Time taken to generate the report in ms
        healthy_components: Count of components with healthy status
        degraded_components: Count of components with degraded status
        unhealthy_components: Count of components with unhealthy status
        recommendations: List of health recommendations
    """

    overall_status = String(description="Overall system health status")
    timestamp = String(description="ISO-formatted timestamp of the report")
    report_generation_time_ms = Float(
        description="Time taken to generate the report in ms"
    )
    healthy_components = Int(description="Count of components with healthy status")
    degraded_components = Int(description="Count of components with degraded status")
    unhealthy_components = Int(description="Count of components with unhealthy status")
    recommendations = GrapheneList(
        String, description="List of health recommendations"
    )


class DatabaseHealthType(ObjectType):
    """
    GraphQL type for database-specific health information.

    Provides detailed health status for a single database connection.

    Fields:
        alias: Database alias name
        status: Connection health status
        engine: Database engine type (PostgreSQL, MySQL, SQLite)
        version: Database version string
        active_connections: Number of active connections to this database
        response_time_ms: Time taken to check connectivity in milliseconds
        message: Human-readable status message
    """

    alias = String(description="Database alias name")
    status = String(description="Connection health status")
    engine = String(description="Database engine type")
    version = String(description="Database version string")
    active_connections = Int(description="Number of active connections")
    response_time_ms = Float(description="Time taken to check connectivity in ms")
    message = String(description="Human-readable status message")


class CacheHealthType(ObjectType):
    """
    GraphQL type for cache-specific health information.

    Provides detailed health status for a single cache backend.

    Fields:
        alias: Cache alias name
        status: Cache health status
        backend: Cache backend class name
        hit_rate: Cache hit rate as a ratio (0.0-1.0)
        response_time_ms: Time taken to check cache in milliseconds
        message: Human-readable status message
    """

    alias = String(description="Cache alias name")
    status = String(description="Cache health status")
    backend = String(description="Cache backend class name")
    hit_rate = Float(description="Cache hit rate as a ratio (0.0-1.0)")
    response_time_ms = Float(description="Time taken to check cache in ms")
    message = String(description="Human-readable status message")


class ComponentHealthSummaryType(ObjectType):
    """
    GraphQL type for component health summary.

    Provides a summary of health status counts across all components.

    Fields:
        total_components: Total number of monitored components
        healthy: Count of healthy components
        degraded: Count of degraded components
        unhealthy: Count of unhealthy components
    """

    total_components = Int(description="Total number of monitored components")
    healthy = Int(description="Count of healthy components")
    degraded = Int(description="Count of degraded components")
    unhealthy = Int(description="Count of unhealthy components")


class DetailedHealthReportType(ObjectType):
    """
    GraphQL type for detailed health report with full component breakdown.

    Provides comprehensive health information including individual component
    statuses, system metrics, and recommendations.

    Fields:
        overall_status: Overall system health status
        timestamp: ISO-formatted timestamp of the report
        report_generation_time_ms: Time taken to generate the report in ms
        summary: Component health summary counts
        schema_health: GraphQL schema health status
        database_health: List of database health statuses
        cache_health: List of cache health statuses
        system_metrics: Current system resource metrics
        recommendations: List of health recommendations
    """

    overall_status = String(description="Overall system health status")
    timestamp = String(description="ISO-formatted timestamp of the report")
    report_generation_time_ms = Float(
        description="Time taken to generate the report in ms"
    )
    summary = GrapheneList(
        ComponentHealthSummaryType, description="Component health summary"
    )
    schema_health = GrapheneList(HealthStatusType, description="Schema health status")
    database_health = GrapheneList(
        DatabaseHealthType, description="Database health statuses"
    )
    cache_health = GrapheneList(CacheHealthType, description="Cache health statuses")
    system_metrics = GrapheneList(SystemMetricsType, description="System metrics")
    recommendations = GrapheneList(
        String, description="List of health recommendations"
    )

"""
Health Check Data Types for Django GraphQL Auto

This module defines the dataclasses used for health status and system metrics
throughout the health monitoring system.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class HealthStatus:
    """
    Represents the health status of a system component.

    Attributes:
        component: Name of the system component being monitored
        status: Health status ('healthy', 'degraded', 'unhealthy')
        message: Human-readable status message
        response_time_ms: Time taken to check this component in milliseconds
        timestamp: When the health check was performed
        details: Optional additional details about the component status
    """

    component: str
    status: str  # 'healthy', 'degraded', 'unhealthy'
    message: str
    response_time_ms: float
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dict containing all fields with timestamp as ISO format string.
        """
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def is_healthy(self) -> bool:
        """Check if the component status is healthy."""
        return self.status == "healthy"

    def is_degraded(self) -> bool:
        """Check if the component status is degraded."""
        return self.status == "degraded"

    def is_unhealthy(self) -> bool:
        """Check if the component status is unhealthy."""
        return self.status == "unhealthy"


@dataclass
class SystemMetrics:
    """
    System performance and resource metrics.

    Attributes:
        cpu_usage_percent: Current CPU usage as a percentage (0-100)
        memory_usage_percent: Current memory usage as a percentage (0-100)
        memory_used_mb: Amount of memory used in megabytes
        memory_available_mb: Amount of memory available in megabytes
        disk_usage_percent: Disk usage as a percentage (0-100)
        active_connections: Number of active database connections
        cache_hit_rate: Cache hit rate as a ratio (0.0-1.0)
        uptime_seconds: Application uptime in seconds
        collection_time_ms: Time taken to collect these metrics in milliseconds
    """

    cpu_usage_percent: float
    memory_usage_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    active_connections: int
    cache_hit_rate: float
    uptime_seconds: float
    collection_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def is_cpu_critical(self, threshold: float = 80.0) -> bool:
        """Check if CPU usage exceeds the critical threshold."""
        return self.cpu_usage_percent > threshold

    def is_memory_critical(self, threshold: float = 85.0) -> bool:
        """Check if memory usage exceeds the critical threshold."""
        return self.memory_usage_percent > threshold

    def is_disk_critical(self, threshold: float = 90.0) -> bool:
        """Check if disk usage exceeds the critical threshold."""
        return self.disk_usage_percent > threshold


# Status constants for consistent usage across the module
class HealthStatusValue:
    """Constants for health status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# Threshold constants for health checks
class HealthThresholds:
    """Default threshold values for health monitoring."""

    CPU_WARNING = 80.0
    CPU_CRITICAL = 95.0
    MEMORY_WARNING = 85.0
    MEMORY_CRITICAL = 95.0
    DISK_WARNING = 90.0
    DISK_CRITICAL = 98.0
    RESPONSE_TIME_SLOW_MS = 1000.0
    CACHE_HIT_RATE_LOW = 0.7

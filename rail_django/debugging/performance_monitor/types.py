"""
Performance monitoring types and data classes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, NamedTuple


class MetricType(Enum):
    """Types of performance metrics."""
    EXECUTION_TIME = "execution_time"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    QUERY_COUNT = "query_count"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"


@dataclass
class PerformanceMetric:
    """Represents a performance metric measurement."""
    metric_type: MetricType
    value: float
    timestamp: datetime
    operation: str
    context: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration."""
    metric_type: MetricType
    warning_threshold: float
    critical_threshold: float
    enabled: bool = True


@dataclass
class PerformanceAlert:
    """Performance alert when thresholds are exceeded."""
    metric_type: MetricType
    current_value: float
    threshold_value: float
    severity: str  # 'warning' or 'critical'
    operation: str
    timestamp: datetime
    context: dict[str, Any] = field(default_factory=dict)


class PerformanceStats(NamedTuple):
    """Performance statistics for an operation."""
    count: int
    avg: float
    min: float
    max: float
    median: float
    p95: float
    p99: float
    std_dev: float

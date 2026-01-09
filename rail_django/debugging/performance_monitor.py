"""
Performance monitoring module.

This module provides comprehensive performance monitoring for GraphQL operations,
including query execution times, memory usage, and system resource tracking.
"""

import json
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, NamedTuple, Optional

import psutil

logger = logging.getLogger(__name__)


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
    context: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)


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
    context: Dict[str, Any] = field(default_factory=dict)


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


class PerformanceMonitor:
    """
    Comprehensive performance monitoring for GraphQL operations.

    Tracks execution times, memory usage, CPU usage, and provides
    alerting when performance thresholds are exceeded.
    """

    def __init__(self,
                 enable_memory_tracking: bool = True,
                 enable_cpu_tracking: bool = True,
                 enable_system_monitoring: bool = True,
                 metric_retention_hours: int = 24,
                 alert_callbacks: List[Callable[[PerformanceAlert], None]] = None):

        self.enable_memory_tracking = enable_memory_tracking
        self.enable_cpu_tracking = enable_cpu_tracking
        self.enable_system_monitoring = enable_system_monitoring
        self.metric_retention_hours = metric_retention_hours
        self.alert_callbacks = alert_callbacks or []

        # Metric storage
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._operation_metrics: Dict[str, Dict[MetricType, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=1000))
        )

        # Performance thresholds
        self._thresholds: Dict[MetricType, PerformanceThreshold] = {
            MetricType.EXECUTION_TIME: PerformanceThreshold(
                MetricType.EXECUTION_TIME, 1000.0, 5000.0  # ms
            ),
            MetricType.MEMORY_USAGE: PerformanceThreshold(
                MetricType.MEMORY_USAGE, 100.0, 500.0  # MB
            ),
            MetricType.CPU_USAGE: PerformanceThreshold(
                MetricType.CPU_USAGE, 70.0, 90.0  # percentage
            ),
            MetricType.ERROR_RATE: PerformanceThreshold(
                MetricType.ERROR_RATE, 5.0, 15.0  # percentage
            )
        }

        # Tracking state
        self._active_operations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

        # System monitoring
        self._system_monitor_thread = None
        self._system_monitor_running = False

        # Process reference for system metrics
        self._process = psutil.Process()

        self.logger = logging.getLogger(__name__)

        if self.enable_system_monitoring:
            self.start_system_monitoring()

    def start_system_monitoring(self, interval_seconds: float = 5.0):
        """Start background system monitoring."""
        if self._system_monitor_running:
            return

        self._system_monitor_running = True
        self._system_monitor_thread = threading.Thread(
            target=self._system_monitor_loop,
            args=(interval_seconds,),
            daemon=True
        )
        self._system_monitor_thread.start()

        self.logger.info("System monitoring started")

    def stop_system_monitoring(self):
        """Stop background system monitoring."""
        self._system_monitor_running = False
        if self._system_monitor_thread:
            self._system_monitor_thread.join(timeout=1.0)

        self.logger.info("System monitoring stopped")

    def set_threshold(self, metric_type: MetricType, warning: float,
                      critical: float, enabled: bool = True):
        """Set performance threshold for a metric type."""
        self._thresholds[metric_type] = PerformanceThreshold(
            metric_type, warning, critical, enabled
        )

    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """Add callback for performance alerts."""
        self.alert_callbacks.append(callback)

    def start_operation(self, operation_id: str, operation_name: str,
                        context: Dict[str, Any] = None) -> str:
        """
        Start monitoring a GraphQL operation.

        Args:
            operation_id: Unique identifier for this operation instance
            operation_name: Name of the operation (e.g., 'getUserProfile')
            context: Additional context for the operation

        Returns:
            Operation ID for tracking
        """
        start_time = time.time()

        operation_data = {
            'operation_name': operation_name,
            'start_time': start_time,
            'context': context or {},
            'memory_start': None,
            'cpu_start': None
        }

        # Capture initial system metrics
        if self.enable_memory_tracking:
            try:
                memory_info = self._process.memory_info()
                operation_data['memory_start'] = memory_info.rss / 1024 / 1024  # MB
            except Exception as e:
                self.logger.warning(f"Failed to capture memory info: {e}")

        if self.enable_cpu_tracking:
            try:
                operation_data['cpu_start'] = self._process.cpu_percent()
            except Exception as e:
                self.logger.warning(f"Failed to capture CPU info: {e}")

        with self._lock:
            self._active_operations[operation_id] = operation_data

        self.logger.debug(f"Started monitoring operation: {operation_name} ({operation_id})")
        return operation_id

    def end_operation(self, operation_id: str, success: bool = True,
                      error: Exception = None) -> Optional[Dict[str, Any]]:
        """
        End monitoring a GraphQL operation.

        Args:
            operation_id: Operation ID returned by start_operation
            success: Whether the operation completed successfully
            error: Exception if operation failed

        Returns:
            Performance metrics for the operation
        """
        end_time = time.time()

        with self._lock:
            if operation_id not in self._active_operations:
                self.logger.warning(f"Unknown operation ID: {operation_id}")
                return None

            operation_data = self._active_operations.pop(operation_id)

        # Calculate metrics
        execution_time_ms = (end_time - operation_data['start_time']) * 1000
        operation_name = operation_data['operation_name']

        metrics = {
            'operation_name': operation_name,
            'execution_time_ms': execution_time_ms,
            'success': success,
            'timestamp': datetime.now()
        }

        # Memory metrics
        if self.enable_memory_tracking and operation_data['memory_start'] is not None:
            try:
                memory_info = self._process.memory_info()
                memory_end = memory_info.rss / 1024 / 1024  # MB
                memory_delta = memory_end - operation_data['memory_start']

                metrics['memory_usage_mb'] = memory_end
                metrics['memory_delta_mb'] = memory_delta

                self._record_metric(
                    MetricType.MEMORY_USAGE, memory_end, operation_name,
                    context={'delta': memory_delta}
                )

            except Exception as e:
                self.logger.warning(f"Failed to capture end memory info: {e}")

        # CPU metrics
        if self.enable_cpu_tracking and operation_data['cpu_start'] is not None:
            try:
                cpu_end = self._process.cpu_percent()
                metrics['cpu_usage_percent'] = cpu_end

                self._record_metric(
                    MetricType.CPU_USAGE, cpu_end, operation_name
                )

            except Exception as e:
                self.logger.warning(f"Failed to capture end CPU info: {e}")

        # Record execution time
        self._record_metric(
            MetricType.EXECUTION_TIME, execution_time_ms, operation_name,
            context={'success': success}
        )

        # Record query count
        self._record_metric(
            MetricType.QUERY_COUNT, 1, operation_name,
            context={'success': success}
        )

        # Check thresholds and generate alerts
        self._check_thresholds(operation_name, metrics)

        self.logger.debug(
            f"Completed monitoring operation: {operation_name} "
            f"({execution_time_ms:.2f}ms, success: {success})"
        )

        return metrics

    def record_custom_metric(self, metric_type: MetricType, value: float,
                             operation: str, context: Dict[str, Any] = None,
                             tags: Dict[str, str] = None):
        """Record a custom performance metric."""
        self._record_metric(metric_type, value, operation, context, tags)

    def get_operation_stats(self, operation_name: str,
                            metric_type: MetricType = MetricType.EXECUTION_TIME,
                            hours_back: int = 1) -> Optional[PerformanceStats]:
        """
        Get performance statistics for an operation.

        Args:
            operation_name: Name of the operation
            metric_type: Type of metric to analyze
            hours_back: How many hours of data to include

        Returns:
            Performance statistics or None if no data
        """
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        with self._lock:
            if operation_name not in self._operation_metrics:
                return None

            metrics = self._operation_metrics[operation_name].get(metric_type, deque())

            # Filter by time
            recent_values = [
                m.value for m in metrics
                if m.timestamp >= cutoff_time
            ]

        if not recent_values:
            return None

        # Calculate statistics
        recent_values.sort()
        count = len(recent_values)

        return PerformanceStats(
            count=count,
            avg=statistics.mean(recent_values),
            min=min(recent_values),
            max=max(recent_values),
            median=statistics.median(recent_values),
            p95=recent_values[int(count * 0.95)] if count > 0 else 0,
            p99=recent_values[int(count * 0.99)] if count > 0 else 0,
            std_dev=statistics.stdev(recent_values) if count > 1 else 0
        )

    def get_system_stats(self, hours_back: int = 1) -> Dict[str, Any]:
        """Get system-wide performance statistics."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        stats = {}

        with self._lock:
            for metric_type in [MetricType.MEMORY_USAGE, MetricType.CPU_USAGE]:
                key = f"system_{metric_type.value}"
                if key in self._metrics:
                    recent_values = [
                        m.value for m in self._metrics[key]
                        if m.timestamp >= cutoff_time
                    ]

                    if recent_values:
                        stats[metric_type.value] = {
                            'avg': statistics.mean(recent_values),
                            'min': min(recent_values),
                            'max': max(recent_values),
                            'current': recent_values[-1] if recent_values else None
                        }

        return stats

    def get_top_operations(self, metric_type: MetricType = MetricType.EXECUTION_TIME,
                           limit: int = 10, hours_back: int = 1) -> List[Dict[str, Any]]:
        """Get top operations by performance metric."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        operation_averages = []

        with self._lock:
            for operation_name, metrics_by_type in self._operation_metrics.items():
                if metric_type not in metrics_by_type:
                    continue

                recent_values = [
                    m.value for m in metrics_by_type[metric_type]
                    if m.timestamp >= cutoff_time
                ]

                if recent_values:
                    operation_averages.append({
                        'operation': operation_name,
                        'avg_value': statistics.mean(recent_values),
                        'count': len(recent_values),
                        'max_value': max(recent_values)
                    })

        # Sort by average value (descending for most problematic)
        operation_averages.sort(key=lambda x: x['avg_value'], reverse=True)

        return operation_averages[:limit]

    def get_error_rate(self, operation_name: str = None, hours_back: int = 1) -> float:
        """Calculate error rate for operations."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        total_operations = 0
        failed_operations = 0

        with self._lock:
            if operation_name:
                # Specific operation
                if operation_name in self._operation_metrics:
                    query_metrics = self._operation_metrics[operation_name].get(
                        MetricType.QUERY_COUNT, deque()
                    )

                    for metric in query_metrics:
                        if metric.timestamp >= cutoff_time:
                            total_operations += 1
                            if not metric.context.get('success', True):
                                failed_operations += 1
            else:
                # All operations
                for op_metrics in self._operation_metrics.values():
                    query_metrics = op_metrics.get(MetricType.QUERY_COUNT, deque())

                    for metric in query_metrics:
                        if metric.timestamp >= cutoff_time:
                            total_operations += 1
                            if not metric.context.get('success', True):
                                failed_operations += 1

        if total_operations == 0:
            return 0.0

        return (failed_operations / total_operations) * 100

    def export_metrics(self, format: str = 'json', hours_back: int = 24) -> str:
        """Export performance metrics in specified format."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'hours_back': hours_back,
            'system_stats': self.get_system_stats(hours_back),
            'operations': {}
        }

        # Export operation metrics
        with self._lock:
            for operation_name, metrics_by_type in self._operation_metrics.items():
                operation_data = {}

                for metric_type, metrics in metrics_by_type.items():
                    recent_metrics = [
                        {
                            'value': m.value,
                            'timestamp': m.timestamp.isoformat(),
                            'context': m.context,
                            'tags': m.tags
                        }
                        for m in metrics if m.timestamp >= cutoff_time
                    ]

                    if recent_metrics:
                        operation_data[metric_type.value] = recent_metrics

                if operation_data:
                    export_data['operations'][operation_name] = operation_data

        if format == 'json':
            return json.dumps(export_data, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def clear_metrics(self, operation_name: str = None):
        """Clear performance metrics."""
        with self._lock:
            if operation_name:
                if operation_name in self._operation_metrics:
                    del self._operation_metrics[operation_name]
            else:
                self._metrics.clear()
                self._operation_metrics.clear()

    def _record_metric(self, metric_type: MetricType, value: float, operation: str,
                       context: Dict[str, Any] = None, tags: Dict[str, str] = None):
        """Record a performance metric."""
        metric = PerformanceMetric(
            metric_type=metric_type,
            value=value,
            timestamp=datetime.now(),
            operation=operation,
            context=context or {},
            tags=tags or {}
        )

        with self._lock:
            # Store in operation-specific metrics
            self._operation_metrics[operation][metric_type].append(metric)

            # Store in global metrics for system-wide tracking
            if metric_type in [MetricType.MEMORY_USAGE, MetricType.CPU_USAGE]:
                key = f"system_{metric_type.value}"
                self._metrics[key].append(metric)

        # Clean up old metrics
        self._cleanup_old_metrics()

    def _check_thresholds(self, operation_name: str, metrics: Dict[str, Any]):
        """Check if metrics exceed thresholds and generate alerts."""
        for metric_name, value in metrics.items():
            if not isinstance(value, (int, float)):
                continue

            # Map metric names to types
            metric_type_mapping = {
                'execution_time_ms': MetricType.EXECUTION_TIME,
                'memory_usage_mb': MetricType.MEMORY_USAGE,
                'cpu_usage_percent': MetricType.CPU_USAGE
            }

            metric_type = metric_type_mapping.get(metric_name)
            if not metric_type or metric_type not in self._thresholds:
                continue

            threshold = self._thresholds[metric_type]
            if not threshold.enabled:
                continue

            alert = None

            if value >= threshold.critical_threshold:
                alert = PerformanceAlert(
                    metric_type=metric_type,
                    current_value=value,
                    threshold_value=threshold.critical_threshold,
                    severity='critical',
                    operation=operation_name,
                    timestamp=datetime.now(),
                    context=metrics
                )
            elif value >= threshold.warning_threshold:
                alert = PerformanceAlert(
                    metric_type=metric_type,
                    current_value=value,
                    threshold_value=threshold.warning_threshold,
                    severity='warning',
                    operation=operation_name,
                    timestamp=datetime.now(),
                    context=metrics
                )

            if alert:
                self._handle_alert(alert)

    def _handle_alert(self, alert: PerformanceAlert):
        """Handle a performance alert."""
        # Log the alert
        log_level = logging.ERROR if alert.severity == 'critical' else logging.WARNING
        self.logger.log(
            log_level,
            f"Performance {alert.severity}: {alert.operation} "
            f"{alert.metric_type.value} = {alert.current_value:.2f} "
            f"(threshold: {alert.threshold_value:.2f})"
        )

        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")

    def _system_monitor_loop(self, interval_seconds: float):
        """Background system monitoring loop."""
        while self._system_monitor_running:
            try:
                # Memory usage
                if self.enable_memory_tracking:
                    memory_info = self._process.memory_info()
                    memory_mb = memory_info.rss / 1024 / 1024

                    self._record_metric(
                        MetricType.MEMORY_USAGE, memory_mb, "system"
                    )

                # CPU usage
                if self.enable_cpu_tracking:
                    cpu_percent = self._process.cpu_percent()

                    self._record_metric(
                        MetricType.CPU_USAGE, cpu_percent, "system"
                    )

            except Exception as e:
                self.logger.error(f"Error in system monitoring: {e}")

            time.sleep(interval_seconds)

    def _cleanup_old_metrics(self):
        """Clean up old metrics based on retention policy."""
        cutoff_time = datetime.now() - timedelta(hours=self.metric_retention_hours)

        # This is called frequently, so we only clean up occasionally
        if hasattr(self, '_last_cleanup'):
            if (datetime.now() - self._last_cleanup).total_seconds() < 300:  # 5 minutes
                return

        with self._lock:
            # Clean up global metrics
            for key, metrics in self._metrics.items():
                while metrics and metrics[0].timestamp < cutoff_time:
                    metrics.popleft()

            # Clean up operation metrics
            for operation_metrics in self._operation_metrics.values():
                for metric_type_metrics in operation_metrics.values():
                    while (metric_type_metrics and
                           metric_type_metrics[0].timestamp < cutoff_time):
                        metric_type_metrics.popleft()

        self._last_cleanup = datetime.now()

    def __del__(self):
        """Cleanup when monitor is destroyed."""
        self.stop_system_monitoring()

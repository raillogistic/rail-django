"""
Health monitoring logic for SchemaManager.
"""

import logging
import threading
from datetime import datetime
from typing import Optional

from graphql import validate_schema
from .health import SchemaHealth

logger = logging.getLogger(__name__)


class SchemaHealthMixin:
    """Mixin for schema health monitoring."""

    def check_schema_health(self, name: str) -> SchemaHealth:
        """Perform health check on a schema."""
        if name not in self._schemas: raise ValueError(f"Schema {name} not found")
        schema = self._schemas[name]
        health = SchemaHealth(schema_name=name, status='healthy', last_check=datetime.now())
        issues = []
        performance_score = 100.0

        try:
            validation_errors = validate_schema(schema)
            if validation_errors:
                issues.extend([str(error) for error in validation_errors])
                health.status = 'critical'
                performance_score -= 50
        except Exception as e:
            issues.append(f"Schema validation error: {e}")
            health.status = 'critical'
            performance_score -= 50

        if self.introspector:
            try:
                introspection = self.introspector.introspect_schema(schema)
                deprecated_count = sum(1 for type_info in introspection.types.values() for field in type_info.fields if field.is_deprecated)
                if deprecated_count > 0:
                    issues.append(f"{deprecated_count} deprecated fields found")
                    if deprecated_count > 10: health.status = 'warning'; performance_score -= 10
            except Exception as e: issues.append(f"Introspection error: {e}")

        if self.performance_monitor:
            try:
                stats = self.performance_monitor.get_operation_stats(operation_name=f"schema:{name}", hours_back=24)
                if stats:
                    avg_time = stats.get('avg_execution_time_ms', 0)
                    error_rate = stats.get('error_rate', 0)
                    health.error_rate = error_rate
                    if avg_time > 1000: issues.append(f"High average execution time: {avg_time:.2f}ms"); performance_score -= 20
                    if error_rate > 0.05:
                        issues.append(f"High error rate: {error_rate:.2%}")
                        if error_rate > 0.1: health.status = 'critical'
                        else: health.status = 'warning'
                        performance_score -= 30
            except Exception as e: issues.append(f"Performance monitoring error: {e}")

        health.issues = issues
        health.performance_score = max(0, performance_score)
        if health.status == 'healthy' and issues: health.status = 'warning'
        with self._lock: self._health_status[name] = health
        return health

    def _start_health_monitoring(self):
        """Start background health monitoring."""
        def monitor_health():
            while not self._stop_health_monitor.is_set():
                try:
                    with self._lock: schema_names = list(self._schemas.keys())
                    for name in schema_names:
                        try: self.check_schema_health(name)
                        except Exception as e: logger.error(f"Health check failed for schema {name}: {e}")
                    self._stop_health_monitor.wait(self.health_check_interval)
                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
                    self._stop_health_monitor.wait(60)

        self._health_monitor_thread = threading.Thread(target=monitor_health, daemon=True, name="SchemaHealthMonitor")
        self._health_monitor_thread.start()

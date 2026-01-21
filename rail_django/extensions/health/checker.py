"""
Health Checker for Django GraphQL Auto

This module provides the HealthChecker class for comprehensive health monitoring
of the GraphQL application including schema validation, database connectivity,
cache system status, and performance metrics.
"""

import copy
import logging
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psutil
from django.conf import settings
from django.db import connections

from .types import HealthStatus, SystemMetrics
from .utils import count_active_connections, generate_recommendations, get_database_info

logger = logging.getLogger(__name__)


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

    _process_start_time = time.time()
    _cache_lock = threading.Lock()
    _system_metrics_cache: Optional[SystemMetrics] = None
    _system_metrics_cache_ts: float = 0.0
    _health_report_cache: Optional[Dict[str, Any]] = None
    _health_report_cache_ts: float = 0.0

    def __init__(self) -> None:
        """Initialize the health checker with process start time."""
        self.start_time = self._process_start_time
        self._cache_stats = {"hits": 0, "misses": 0}

    def _resolve_cache_ttl(
        self, ttl_seconds: Optional[float], setting_name: str, default: float
    ) -> float:
        """Resolve cache TTL from parameter, settings, or default."""
        if ttl_seconds is None:
            ttl_seconds = getattr(settings, setting_name, default)
        try:
            ttl_value = float(ttl_seconds)
        except (TypeError, ValueError):
            ttl_value = 0.0
        return max(0.0, ttl_value)

    def _get_cached_system_metrics(self, ttl_seconds: float) -> Optional[SystemMetrics]:
        """Get cached system metrics if still valid."""
        if ttl_seconds <= 0:
            return None
        now = time.monotonic()
        cache_owner = type(self)
        with cache_owner._cache_lock:
            cached = cache_owner._system_metrics_cache
            if cached and (now - cache_owner._system_metrics_cache_ts) <= ttl_seconds:
                return cached
        return None

    def _set_cached_system_metrics(self, metrics: SystemMetrics) -> None:
        """Store system metrics in cache."""
        cache_owner = type(self)
        with cache_owner._cache_lock:
            cache_owner._system_metrics_cache = SystemMetrics(**asdict(metrics))
            cache_owner._system_metrics_cache_ts = time.monotonic()

    def _get_cached_health_report(self, ttl_seconds: float) -> Optional[Dict[str, Any]]:
        """Get cached health report if still valid."""
        if ttl_seconds <= 0:
            return None
        now = time.monotonic()
        cache_owner = type(self)
        with cache_owner._cache_lock:
            cached = cache_owner._health_report_cache
            if cached and (now - cache_owner._health_report_cache_ts) <= ttl_seconds:
                return cached
        return None

    def _set_cached_health_report(self, report: Dict[str, Any]) -> None:
        """Store health report in cache."""
        cache_owner = type(self)
        with cache_owner._cache_lock:
            cache_owner._health_report_cache = copy.deepcopy(report)
            cache_owner._health_report_cache_ts = time.monotonic()

    def check_schema_health(self) -> HealthStatus:
        """Check GraphQL schema health and validation."""
        start_time = time.time()

        try:
            from rail_django.core.schema import get_schema

            schema = get_schema()

            if not schema:
                return HealthStatus(
                    component="schema",
                    status="unhealthy",
                    message="GraphQL schema not found or not initialized",
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now(timezone.utc),
                )

            try:
                introspection_query = """
                query IntrospectionQuery {
                    __schema { types { name } }
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
        """Check database connectivity for all configured databases."""
        health_statuses = []

        for db_alias in connections:
            start_time = time.time()

            try:
                conn = connections[db_alias]
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()

                if result and result[0] == 1:
                    db_info = get_database_info(conn, db_alias)
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
        """Check cache system health. Currently disabled, returns empty list."""
        return []

    def get_system_metrics(
        self, *, use_cache: bool = True, ttl_seconds: Optional[float] = None
    ) -> SystemMetrics:
        """Get comprehensive system performance metrics."""
        ttl_value = self._resolve_cache_ttl(
            ttl_seconds, "HEALTH_METRICS_CACHE_TTL_SECONDS", 5.0
        )
        if use_cache:
            cached = self._get_cached_system_metrics(ttl_value)
            if cached:
                return SystemMetrics(**asdict(cached))

        start_time = time.perf_counter()
        try:
            cpu_percent = psutil.cpu_percent(interval=0.0)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            metrics = SystemMetrics(
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                memory_available_mb=memory.available / (1024 * 1024),
                disk_usage_percent=(disk.used / disk.total) * 100,
                active_connections=count_active_connections(),
                cache_hit_rate=0.0,
                uptime_seconds=time.time() - self.start_time,
                collection_time_ms=(time.perf_counter() - start_time) * 1000,
            )
            if use_cache and ttl_value > 0:
                self._set_cached_system_metrics(metrics)
            return metrics

        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            metrics = SystemMetrics(
                cpu_usage_percent=0.0,
                memory_usage_percent=0.0,
                memory_used_mb=0.0,
                memory_available_mb=0.0,
                disk_usage_percent=0.0,
                active_connections=0,
                cache_hit_rate=0.0,
                uptime_seconds=time.time() - self.start_time,
                collection_time_ms=(time.perf_counter() - start_time) * 1000,
            )
            if use_cache and ttl_value > 0:
                self._set_cached_system_metrics(metrics)
            return metrics

    def get_comprehensive_health_report(
        self, *, use_cache: bool = True, ttl_seconds: Optional[float] = None
    ) -> Dict[str, Any]:
        """Generate a comprehensive health report for all system components."""
        ttl_value = self._resolve_cache_ttl(
            ttl_seconds, "HEALTH_REPORT_CACHE_TTL_SECONDS", 5.0
        )
        if use_cache:
            cached_report = self._get_cached_health_report(ttl_value)
            if cached_report:
                return copy.deepcopy(cached_report)

        report_start_time = time.perf_counter()

        schema_health = self.check_schema_health()
        database_health = self.check_database_health()
        cache_health = self.check_cache_health()
        system_metrics = self.get_system_metrics(use_cache=use_cache)

        all_statuses = [schema_health] + database_health + cache_health

        healthy_count = sum(1 for s in all_statuses if s.status == "healthy")
        degraded_count = sum(1 for s in all_statuses if s.status == "degraded")
        unhealthy_count = sum(1 for s in all_statuses if s.status == "unhealthy")

        if unhealthy_count > 0:
            overall_status = "unhealthy"
        elif degraded_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        report = {
            "overall_status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "report_generation_time_ms": (time.perf_counter() - report_start_time) * 1000,
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
            "recommendations": generate_recommendations(all_statuses, system_metrics),
        }
        if use_cache and ttl_value > 0:
            self._set_cached_health_report(report)

        return report

    def get_health_report(
        self,
        *,
        use_cache: bool = True,
        ttl_seconds: Optional[float] = None,
        comprehensive_report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Provide a backward-compatible health report wrapper."""
        try:
            if comprehensive_report is None:
                comprehensive_report = self.get_comprehensive_health_report(
                    use_cache=use_cache, ttl_seconds=ttl_seconds
                )
            return self._summarize_report(comprehensive_report)
        except Exception as e:
            logger.error(f"Failed to generate health report: {e}")
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

    def _summarize_report(self, comprehensive: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize comprehensive report for legacy compatibility."""
        summary = comprehensive.get("summary", {})
        return {
            "overall_status": comprehensive.get("overall_status"),
            "timestamp": comprehensive.get("timestamp"),
            "report_generation_time_ms": comprehensive.get("report_generation_time_ms"),
            "healthy_components": summary.get("healthy", 0),
            "degraded_components": summary.get("degraded", 0),
            "unhealthy_components": summary.get("unhealthy", 0),
            "total_components": summary.get("total_components", 0),
            "components": comprehensive.get("components", {}),
            "system_metrics": comprehensive.get("system_metrics", {}),
            "recommendations": comprehensive.get("recommendations", []),
        }


# Global health checker instance
health_checker = HealthChecker()

"""
Middleware de monitoring des performances pour Django GraphQL Auto.

Ce module fournit un middleware complet pour surveiller:
- Les performances des requêtes GraphQL
- L'utilisation des ressources
- Les métriques de cache
- Les alertes de performance
- Les rapports détaillés
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Deque, Dict, List, Optional

import graphene
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.views import View

from ..extensions.optimization import get_performance_monitor

logger = logging.getLogger(__name__)


@dataclass
class RequestMetrics:
    """Métriques pour une requête individuelle."""

    request_id: str
    query_name: str
    start_time: float
    end_time: Optional[float] = None
    execution_time: Optional[float] = None

    # Métriques de performance
    database_queries: int = 0
    database_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    n_plus_one_queries: List[Dict[str, Any]] = field(default_factory=list)
    n_plus_one_count: int = 0

    # Métriques de ressources
    memory_usage: float = 0.0
    cpu_usage: float = 0.0

    # Informations sur la requête
    query_complexity: Optional[int] = None
    query_depth: Optional[int] = None
    user_id: Optional[int] = None

    # Erreurs
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_slow_query(self) -> bool:
        """Détermine si la requête est considérée comme lente."""
        slow_threshold = getattr(settings, "GRAPHQL_SLOW_QUERY_THRESHOLD", 1.0)
        return self.execution_time and self.execution_time > slow_threshold

    @property
    def is_complex_query(self) -> bool:
        """Détermine si la requête est considérée comme complexe."""
        complexity_threshold = getattr(settings, "GRAPHQL_COMPLEXITY_THRESHOLD", 100)
        return self.query_complexity and self.query_complexity > complexity_threshold


class QueryMetricsCollector:
    """Collect query count/time and spot repeated query patterns."""

    def __init__(self, n_plus_one_threshold: int = 5, max_sql_length: int = 200):
        self.query_count = 0
        self.total_time = 0.0
        self.n_plus_one_threshold = n_plus_one_threshold
        self.max_sql_length = max_sql_length
        self._fingerprints: Dict[str, Dict[str, Any]] = {}

    def execute_wrapper(self, execute, sql, params, many, context):
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            duration = time.perf_counter() - start
            self.query_count += 1
            self.total_time += duration
            fingerprint = self._normalize_sql(sql)
            data = self._fingerprints.setdefault(
                fingerprint, {"count": 0, "total_time": 0.0}
            )
            data["count"] += 1
            data["total_time"] += duration

    def get_n_plus_one_candidates(self, limit: int = 5) -> List[Dict[str, Any]]:
        candidates = [
            {"sql": self._truncate_sql(sql), "count": data["count"]}
            for sql, data in self._fingerprints.items()
            if data["count"] >= self.n_plus_one_threshold
        ]
        candidates.sort(key=lambda item: item["count"], reverse=True)
        return candidates[:limit]

    def _normalize_sql(self, sql: Any) -> str:
        return " ".join(str(sql or "").split())

    def _truncate_sql(self, sql: str) -> str:
        if len(sql) <= self.max_sql_length:
            return sql
        return f"{sql[: self.max_sql_length]}..."


@dataclass
class PerformanceAlert:
    """Alerte de performance."""

    alert_type: str  # 'slow_query', 'high_complexity', 'memory_usage', etc.
    severity: str  # 'low', 'medium', 'high', 'critical'
    message: str
    timestamp: datetime
    request_metrics: RequestMetrics
    threshold_value: Optional[float] = None
    actual_value: Optional[float] = None


class PerformanceAggregator:
    """Agrégateur de métriques de performance."""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.metrics_history: Deque[RequestMetrics] = deque(maxlen=window_size)
        self.alerts_history: Deque[PerformanceAlert] = deque(maxlen=100)
        self.lock = threading.Lock()

        # Statistiques agrégées
        self._stats_cache = {}
        self._last_stats_update = 0
        self._stats_cache_duration = 60  # 1 minute

    def add_metrics(self, metrics: RequestMetrics):
        """Ajoute des métriques à l'historique."""
        with self.lock:
            self.metrics_history.append(metrics)
            self._invalidate_stats_cache()

            # Vérifier les alertes
            self._check_alerts(metrics)

    def get_aggregated_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques agrégées."""
        current_time = time.time()

        # Utiliser le cache si disponible et récent
        if (
            self._stats_cache
            and current_time - self._last_stats_update < self._stats_cache_duration
        ):
            return self._stats_cache

        with self.lock:
            if not self.metrics_history:
                return {}

            # Calculer les statistiques
            total_requests = len(self.metrics_history)
            successful_requests = sum(1 for m in self.metrics_history if not m.errors)

            execution_times = [
                m.execution_time for m in self.metrics_history if m.execution_time
            ]
            if execution_times:
                avg_execution_time = sum(execution_times) / len(execution_times)
                max_execution_time = max(execution_times)
                min_execution_time = min(execution_times)
                p95_execution_time = sorted(execution_times)[
                    int(len(execution_times) * 0.95)
                ]
            else:
                avg_execution_time = max_execution_time = min_execution_time = (
                    p95_execution_time
                ) = 0

            db_queries = [
                m.database_queries for m in self.metrics_history if m.database_queries
            ]
            avg_db_queries = (
                sum(db_queries) / len(db_queries) if db_queries else 0
            )
            db_time = [
                m.database_time for m in self.metrics_history if m.database_time
            ]
            avg_db_time = sum(db_time) / len(db_time) if db_time else 0
            n_plus_one_requests = sum(
                1 for m in self.metrics_history if m.n_plus_one_count
            )
            n_plus_one_rate = (
                (n_plus_one_requests / total_requests * 100)
                if total_requests > 0
                else 0
            )

            # Statistiques de cache
            total_cache_hits = sum(m.cache_hits for m in self.metrics_history)
            total_cache_misses = sum(m.cache_misses for m in self.metrics_history)
            cache_hit_rate = (
                total_cache_hits / (total_cache_hits + total_cache_misses) * 100
                if total_cache_hits + total_cache_misses > 0
                else 0
            )

            # Requêtes lentes
            slow_queries = sum(1 for m in self.metrics_history if m.is_slow_query)
            slow_query_rate = (
                (slow_queries / total_requests * 100) if total_requests > 0 else 0
            )

            # Requêtes complexes
            complex_queries = sum(1 for m in self.metrics_history if m.is_complex_query)
            complex_query_rate = (
                (complex_queries / total_requests * 100) if total_requests > 0 else 0
            )

            # Top requêtes par temps d'exécution
            top_slow_queries = sorted(
                [m for m in self.metrics_history if m.execution_time],
                key=lambda m: m.execution_time,
                reverse=True,
            )[:10]

            stats = {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "success_rate": (successful_requests / total_requests * 100)
                if total_requests > 0
                else 0,
                "avg_execution_time": avg_execution_time,
                "avg_database_queries": avg_db_queries,
                "avg_database_time": avg_db_time,
                "n_plus_one_rate": n_plus_one_rate,
                "max_execution_time": max_execution_time,
                "min_execution_time": min_execution_time,
                "p95_execution_time": p95_execution_time,
                "cache_hit_rate": cache_hit_rate,
                "slow_query_rate": slow_query_rate,
                "complex_query_rate": complex_query_rate,
                "top_slow_queries": [
                    {
                        "query_name": m.query_name,
                        "execution_time": m.execution_time,
                        "timestamp": datetime.fromtimestamp(m.start_time),
                    }
                    for m in top_slow_queries
                ],
                "recent_alerts": [
                    {
                        "type": alert.alert_type,
                        "severity": alert.severity,
                        "message": alert.message,
                        "timestamp": alert.timestamp,
                    }
                    for alert in list(self.alerts_history)[-10:]
                ],
            }

            # Mettre en cache les statistiques
            self._stats_cache = stats
            self._last_stats_update = current_time

            return stats

    def _invalidate_stats_cache(self):
        """Invalide le cache des statistiques."""
        self._stats_cache = {}
        self._last_stats_update = 0

    def _check_alerts(self, metrics: RequestMetrics):
        """Vérifie et génère des alertes basées sur les métriques."""
        alerts = []

        # Alerte pour requête lente
        if metrics.is_slow_query:
            alerts.append(
                PerformanceAlert(
                    alert_type="slow_query",
                    severity="medium" if metrics.execution_time < 5.0 else "high",
                    message=f"Slow query detected: {metrics.query_name} took {metrics.execution_time:.2f}s",
                    timestamp=datetime.now(),
                    request_metrics=metrics,
                    threshold_value=getattr(
                        settings, "GRAPHQL_SLOW_QUERY_THRESHOLD", 1.0
                    ),
                    actual_value=metrics.execution_time,
                )
            )

        # Alerte pour requête complexe
        if metrics.is_complex_query:
            alerts.append(
                PerformanceAlert(
                    alert_type="high_complexity",
                    severity="medium",
                    message=f"Complex query detected: {metrics.query_name} has complexity {metrics.query_complexity}",
                    timestamp=datetime.now(),
                    request_metrics=metrics,
                    threshold_value=getattr(
                        settings, "GRAPHQL_COMPLEXITY_THRESHOLD", 100
                    ),
                    actual_value=metrics.query_complexity,
                )
            )

        # Alerte pour utilisation mémoire élevée
        memory_threshold = getattr(settings, "GRAPHQL_MEMORY_THRESHOLD", 100.0)  # MB
        if metrics.memory_usage > memory_threshold:
            alerts.append(
                PerformanceAlert(
                    alert_type="high_memory_usage",
                    severity="high",
                    message=f"High memory usage: {metrics.query_name} used {metrics.memory_usage:.2f}MB",
                    timestamp=datetime.now(),
                    request_metrics=metrics,
                    threshold_value=memory_threshold,
                    actual_value=metrics.memory_usage,
                )
            )

        # Ajouter les alertes à l'historique
        for alert in alerts:
            self.alerts_history.append(alert)

            # Logger les alertes critiques
            if alert.severity in ["high", "critical"]:
                logger.warning(f"Performance Alert: {alert.message}")


# Instance globale de l'agrégateur
_performance_aggregator: Optional[PerformanceAggregator] = None


def get_performance_aggregator() -> PerformanceAggregator:
    """Retourne l'instance globale de l'agrégateur de performance."""
    global _performance_aggregator
    if _performance_aggregator is None:
        _performance_aggregator = PerformanceAggregator()
    return _performance_aggregator


class GraphQLPerformanceMiddleware(MiddlewareMixin):
    """
    Middleware for monitoring GraphQL request performance.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.enabled = getattr(settings, "GRAPHQL_PERFORMANCE_ENABLED", settings.DEBUG)
        self.aggregator = get_performance_aggregator() if self.enabled else None
        self.performance_monitor = get_performance_monitor() if self.enabled else None
        perf_settings = getattr(settings, "RAIL_DJANGO_GRAPHQL", {}).get(
            "performance_settings", {}
        )
        self.enable_query_metrics = bool(perf_settings.get("enable_query_metrics", False))
        self.enable_n_plus_one_detection = bool(
            perf_settings.get("enable_n_plus_one_detection", True)
        )
        self.n_plus_one_threshold = int(perf_settings.get("n_plus_one_threshold", 5))

    def process_request(self, request):
        """Handle the start of a request."""
        if not self.enabled or not self._is_graphql_request(request):
            return None

        request._graphql_request_id = f"req_{int(time.time() * 1000)}_{id(request)}"
        request._graphql_start_time = time.time()
        query_name = self._resolve_query_name(request)
        request._graphql_query_text = self._extract_query_text(request)

        request._graphql_metrics = RequestMetrics(
            request_id=request._graphql_request_id,
            query_name=query_name,
            start_time=request._graphql_start_time,
            user_id=getattr(request.user, "id", None) if hasattr(request, "user") else None,
        )
        if self.enable_query_metrics and hasattr(connection, "execute_wrapper"):
            collector = QueryMetricsCollector(
                n_plus_one_threshold=self.n_plus_one_threshold
            )
            wrapper = connection.execute_wrapper(collector.execute_wrapper)
            wrapper.__enter__()
            request._graphql_query_metrics = collector
            request._graphql_query_wrapper = wrapper

        return None

    def process_response(self, request, response):
        """Handle the end of a request."""
        if not self.enabled or not hasattr(request, "_graphql_metrics"):
            return response

        end_time = time.time()
        metrics = request._graphql_metrics
        metrics.end_time = end_time
        metrics.execution_time = end_time - metrics.start_time
        self._finalize_query_metrics(request, metrics)

        metrics.cache_hits = 0
        metrics.cache_misses = 0

        if self.aggregator:
            self.aggregator.add_metrics(metrics)

        if getattr(settings, "GRAPHQL_PERFORMANCE_HEADERS", False):
            response["X-GraphQL-Execution-Time"] = f"{metrics.execution_time:.3f}"
            if metrics.query_complexity:
                response["X-GraphQL-Query-Complexity"] = str(metrics.query_complexity)
            if metrics.database_queries:
                response["X-GraphQL-DB-Queries"] = str(metrics.database_queries)
            if metrics.database_time:
                response["X-GraphQL-DB-Time"] = f"{metrics.database_time:.3f}"
            if metrics.n_plus_one_count:
                response["X-GraphQL-N-Plus-One"] = str(metrics.n_plus_one_count)

        return response

    def process_exception(self, request, exception):
        """Handle exceptions."""
        if not self.enabled or not hasattr(request, "_graphql_metrics"):
            return None

        metrics = request._graphql_metrics
        metrics.errors.append(str(exception))

        end_time = time.time()
        metrics.end_time = end_time
        metrics.execution_time = end_time - metrics.start_time
        self._finalize_query_metrics(request, metrics)

        if self.aggregator:
            self.aggregator.add_metrics(metrics)

        return None

    def _finalize_query_metrics(self, request, metrics: RequestMetrics) -> None:
        wrapper = getattr(request, "_graphql_query_wrapper", None)
        if wrapper is not None:
            try:
                wrapper.__exit__(None, None, None)
            except Exception:
                logger.debug("Failed to close query metrics wrapper", exc_info=True)
            request._graphql_query_wrapper = None
        collector = getattr(request, "_graphql_query_metrics", None)
        if collector is None:
            return

        metrics.database_queries = collector.query_count
        metrics.database_time = collector.total_time
        if self.enable_n_plus_one_detection:
            candidates = collector.get_n_plus_one_candidates()
            metrics.n_plus_one_queries = candidates
            metrics.n_plus_one_count = len(candidates)
            if candidates:
                metrics.warnings.append("Potential N+1 query pattern detected")

    def _resolve_query_name(self, request) -> str:
        query_text = self._extract_query_text(request)
        if not query_text:
            return "unknown"
        if request.method == "POST" and request.body:
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                op_name = payload.get("operationName") or payload.get("operation_name")
                if op_name:
                    return str(op_name)
        first_field = self._extract_first_field_name(query_text)
        return first_field or "anonymous"

    def _extract_first_field_name(self, query_text: str) -> Optional[str]:
        tokens = query_text.replace("{", " ").replace("}", " ").split()
        for token in tokens:
            lowered = token.lower()
            if lowered in {"query", "mutation", "subscription"}:
                continue
            if lowered.startswith("fragment"):
                continue
            if token.startswith("$") or token.startswith("..."):
                continue
            return token
        return None

    def _extract_query_text(self, request) -> str:
        if request.method == "GET":
            query = request.GET.get("query", "")
            return str(query) if query is not None else ""
        if not request.body:
            return ""
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return ""
        if isinstance(payload, dict):
            query = payload.get("query", "")
            return str(query) if query is not None else ""
        return ""

    def _is_graphql_request(self, request) -> bool:
        """Return True when the request targets GraphQL."""
        if request.path.endswith("/graphql/") or request.path.endswith("/graphql"):
            return True
        content_type = getattr(request, "content_type", "")
        return bool(content_type and "graphql" in content_type.lower())


class GraphQLPerformanceView(View):
    """Vue pour exposer les métriques de performance via une API."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.aggregator = get_performance_aggregator()

    def get(self, request, *args, **kwargs):
        """Endpoint GET pour récupérer les métriques de performance."""
        action = request.GET.get("action", "stats")

        if action == "stats":
            data = self.get_performance_stats()
        elif action == "alerts":
            limit = int(request.GET.get("limit", 50))
            data = self.get_recent_alerts(limit)
        elif action == "slow_queries":
            limit = int(request.GET.get("limit", 20))
            data = self.get_slow_queries(limit)
        else:
            data = {"error": "Invalid action. Use: stats, alerts, or slow_queries"}

        return JsonResponse(data, safe=False)

    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance."""
        return self.aggregator.get_aggregated_stats()

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retourne les alertes récentes."""
        alerts = list(self.aggregator.alerts_history)[-limit:]
        return [
            {
                "type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "query_name": alert.request_metrics.query_name,
                "execution_time": alert.request_metrics.execution_time,
                "threshold_value": alert.threshold_value,
                "actual_value": alert.actual_value,
            }
            for alert in alerts
        ]

    def get_slow_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retourne les requêtes les plus lentes."""
        slow_queries = [
            m
            for m in self.aggregator.metrics_history
            if m.execution_time and m.is_slow_query
        ]

        # Trier par temps d'exécution décroissant
        slow_queries.sort(key=lambda m: m.execution_time, reverse=True)

        return [
            {
                "query_name": m.query_name,
                "execution_time": m.execution_time,
                "timestamp": datetime.fromtimestamp(m.start_time).isoformat(),
                "user_id": m.user_id,
                "query_complexity": m.query_complexity,
                "database_queries": m.database_queries,
                "database_time": m.database_time,
                "n_plus_one_count": m.n_plus_one_count,
                "cache_hits": m.cache_hits,
                "cache_misses": m.cache_misses,
            }
            for m in slow_queries[:limit]
        ]


# Fonction utilitaire pour configurer le middleware
def setup_performance_monitoring():
    """Configure le monitoring des performances."""
    # Vérifier que le middleware est configuré
    middleware_classes = getattr(settings, "MIDDLEWARE", [])
    middleware_name = "rail_django.middleware.performance.GraphQLPerformanceMiddleware"

    if middleware_name not in middleware_classes:
        logger.warning(
            f"GraphQLPerformanceMiddleware not found in MIDDLEWARE settings. "
            f"Add '{middleware_name}' to MIDDLEWARE to enable performance monitoring."
        )

    # Configurer les seuils par défaut si non définis
    if not hasattr(settings, "GRAPHQL_SLOW_QUERY_THRESHOLD"):
        settings.GRAPHQL_SLOW_QUERY_THRESHOLD = 1.0

    if not hasattr(settings, "GRAPHQL_COMPLEXITY_THRESHOLD"):
        settings.GRAPHQL_COMPLEXITY_THRESHOLD = 100

    if not hasattr(settings, "GRAPHQL_MEMORY_THRESHOLD"):
        settings.GRAPHQL_MEMORY_THRESHOLD = 100.0

    logger.info("GraphQL performance monitoring configured")


# Décorateur pour surveiller des fonctions spécifiques
def monitor_performance(query_name: Optional[str] = None):
    """
    Décorateur pour surveiller les performances d'une fonction.

    Args:
        query_name: Nom de la requête (optionnel)
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            start_time = time.time()
            aggregator = get_performance_aggregator()

            # Créer les métriques
            metrics = RequestMetrics(
                request_id=f"func_{int(time.time() * 1000)}_{id(func)}",
                query_name=query_name or func.__name__,
                start_time=start_time,
            )

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                metrics.errors.append(str(e))
                raise
            finally:
                # Finaliser les métriques
                end_time = time.time()
                metrics.end_time = end_time
                metrics.execution_time = end_time - start_time

                # Ajouter à l'agrégateur
                aggregator.add_metrics(metrics)

        return wrapper

    return decorator

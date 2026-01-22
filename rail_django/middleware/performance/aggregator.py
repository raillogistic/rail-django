"""
Aggregator for performance metrics.
"""

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from django.conf import settings

from .metrics import RequestMetrics, PerformanceAlert

logger = logging.getLogger(__name__)


class PerformanceAggregator:
    """Agrégateur de métriques de performance."""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.metrics_history: deque[RequestMetrics] = deque(maxlen=window_size)
        self.alerts_history: deque[PerformanceAlert] = deque(maxlen=100)
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

    def get_aggregated_stats(self) -> dict[str, Any]:
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

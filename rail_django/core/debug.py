"""
Middleware de monitoring des performances pour Django GraphQL Auto.

Ce module fournit un middleware complet pour surveiller:
- Les performances des requêtes GraphQL
- L'utilisation des ressources
- Les métriques de cache
- Les alertes de performance
- Les rapports détaillés
"""

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Deque, Dict, List, Optional

import graphene
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
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
        slow_threshold = getattr(settings, 'GRAPHQL_SLOW_QUERY_THRESHOLD', 1.0)
        return self.execution_time and self.execution_time > slow_threshold

    @property
    def is_complex_query(self) -> bool:
        """Détermine si la requête est considérée comme complexe."""
        complexity_threshold = getattr(settings, 'GRAPHQL_COMPLEXITY_THRESHOLD', 100)
        return self.query_complexity and self.query_complexity > complexity_threshold


@dataclass
class PerformanceAlert:
    """Alerte de performance."""

    alert_type: str  # 'slow_query', 'high_complexity', 'memory_usage', etc.
    severity: str    # 'low', 'medium', 'high', 'critical'
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
        if (self._stats_cache and
                current_time - self._last_stats_update < self._stats_cache_duration):
            return self._stats_cache

        with self.lock:
            if not self.metrics_history:
                return {}

            # Calculer les statistiques
            total_requests = len(self.metrics_history)
            successful_requests = sum(1 for m in self.metrics_history if not m.errors)

            execution_times = [m.execution_time for m in self.metrics_history if m.execution_time]
            if execution_times:
                avg_execution_time = sum(execution_times) / len(execution_times)
                max_execution_time = max(execution_times)
                min_execution_time = min(execution_times)
                p95_execution_time = sorted(execution_times)[int(len(execution_times) * 0.95)]
            else:
                avg_execution_time = max_execution_time = min_execution_time = p95_execution_time = 0

            # Statistiques de cache
            total_cache_hits = sum(m.cache_hits for m in self.metrics_history)
            total_cache_misses = sum(m.cache_misses for m in self.metrics_history)
            cache_hit_rate = (total_cache_hits / (total_cache_hits + total_cache_misses) * 100
                              if total_cache_hits + total_cache_misses > 0 else 0)

            # Requêtes lentes
            slow_queries = sum(1 for m in self.metrics_history if m.is_slow_query)
            slow_query_rate = (slow_queries / total_requests * 100) if total_requests > 0 else 0

            # Requêtes complexes
            complex_queries = sum(1 for m in self.metrics_history if m.is_complex_query)
            complex_query_rate = (complex_queries / total_requests *
                                  100) if total_requests > 0 else 0

            # Top requêtes par temps d'exécution
            top_slow_queries = sorted(
                [m for m in self.metrics_history if m.execution_time],
                key=lambda m: m.execution_time,
                reverse=True
            )[:10]

            stats = {
                'total_requests': total_requests,
                'successful_requests': successful_requests,
                'success_rate': (successful_requests / total_requests * 100) if total_requests > 0 else 0,
                'avg_execution_time': avg_execution_time,
                'max_execution_time': max_execution_time,
                'min_execution_time': min_execution_time,
                'p95_execution_time': p95_execution_time,
                'cache_hit_rate': cache_hit_rate,
                'slow_query_rate': slow_query_rate,
                'complex_query_rate': complex_query_rate,
                'top_slow_queries': [
                    {
                        'query_name': m.query_name,
                        'execution_time': m.execution_time,
                        'timestamp': datetime.fromtimestamp(m.start_time)
                    }
                    for m in top_slow_queries
                ],
                'recent_alerts': [
                    {
                        'type': alert.alert_type,
                        'severity': alert.severity,
                        'message': alert.message,
                        'timestamp': alert.timestamp
                    }
                    for alert in list(self.alerts_history)[-10:]
                ]
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
            alerts.append(PerformanceAlert(
                alert_type='slow_query',
                severity='medium' if metrics.execution_time < 5.0 else 'high',
                message=f"Slow query detected: {metrics.query_name} took {metrics.execution_time:.2f}s",
                timestamp=datetime.now(),
                request_metrics=metrics,
                threshold_value=getattr(settings, 'GRAPHQL_SLOW_QUERY_THRESHOLD', 1.0),
                actual_value=metrics.execution_time
            ))

        # Alerte pour requête complexe
        if metrics.is_complex_query:
            alerts.append(PerformanceAlert(
                alert_type='high_complexity',
                severity='medium',
                message=f"Complex query detected: {metrics.query_name} has complexity {metrics.query_complexity}",
                timestamp=datetime.now(),
                request_metrics=metrics,
                threshold_value=getattr(settings, 'GRAPHQL_COMPLEXITY_THRESHOLD', 100),
                actual_value=metrics.query_complexity
            ))

        # Alerte pour utilisation mémoire élevée
        memory_threshold = getattr(settings, 'GRAPHQL_MEMORY_THRESHOLD', 100.0)  # MB
        if metrics.memory_usage > memory_threshold:
            alerts.append(PerformanceAlert(
                alert_type='high_memory_usage',
                severity='high',
                message=f"High memory usage: {metrics.query_name} used {metrics.memory_usage:.2f}MB",
                timestamp=datetime.now(),
                request_metrics=metrics,
                threshold_value=memory_threshold,
                actual_value=metrics.memory_usage
            ))

        # Ajouter les alertes à l'historique
        for alert in alerts:
            self.alerts_history.append(alert)

            # Logger les alertes critiques
            if alert.severity in ['high', 'critical']:
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
    Middleware pour surveiller les performances des requêtes GraphQL.

    Ce middleware collecte des métriques détaillées sur chaque requête GraphQL
    et les agrège pour fournir des insights sur les performances.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.aggregator = get_performance_aggregator()
        self.performance_monitor = get_performance_monitor()

    def process_request(self, request):
        """Traite le début d'une requête."""
        # Générer un ID unique pour la requête
        request._graphql_request_id = f"req_{int(time.time() * 1000)}_{id(request)}"
        request._graphql_start_time = time.time()

        # Initialiser les métriques de la requête
        request._graphql_metrics = RequestMetrics(
            request_id=request._graphql_request_id,
            query_name="unknown",
            start_time=request._graphql_start_time,
            user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None
        )

        return None

    def process_response(self, request, response):
        """Traite la fin d'une requête."""
        if not hasattr(request, '_graphql_metrics'):
            return response

        # Finaliser les métriques
        end_time = time.time()
        metrics = request._graphql_metrics
        metrics.end_time = end_time
        metrics.execution_time = end_time - metrics.start_time

        # Cache metrics disabled: set to zero to avoid misleading values
        metrics.cache_hits = 0
        metrics.cache_misses = 0

        # Ajouter les métriques à l'agrégateur
        self.aggregator.add_metrics(metrics)

        # Ajouter des headers de performance si configuré
        if getattr(settings, 'GRAPHQL_PERFORMANCE_HEADERS', False):
            response['X-GraphQL-Execution-Time'] = f"{metrics.execution_time:.3f}"
            if metrics.query_complexity:
                response['X-GraphQL-Query-Complexity'] = str(metrics.query_complexity)

        return response

    def process_exception(self, request, exception):
        """Traite les exceptions."""
        if hasattr(request, '_graphql_metrics'):
            metrics = request._graphql_metrics
            metrics.errors.append(str(exception))

            # Finaliser les métriques même en cas d'erreur
            end_time = time.time()
            metrics.end_time = end_time
            metrics.execution_time = end_time - metrics.start_time

            # Ajouter les métriques à l'agrégateur
            self.aggregator.add_metrics(metrics)

        return None


class GraphQLPerformanceView:
    """Vue pour exposer les métriques de performance via une API."""

    def __init__(self):
        self.aggregator = get_performance_aggregator()

    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance."""
        return self.aggregator.get_aggregated_stats()

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retourne les alertes récentes."""
        alerts = list(self.aggregator.alerts_history)[-limit:]
        return [
            {
                'type': alert.alert_type,
                'severity': alert.severity,
                'message': alert.message,
                'timestamp': alert.timestamp.isoformat(),
                'query_name': alert.request_metrics.query_name,
                'execution_time': alert.request_metrics.execution_time,
                'threshold_value': alert.threshold_value,
                'actual_value': alert.actual_value
            }
            for alert in alerts
        ]

    def get_slow_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retourne les requêtes les plus lentes."""
        slow_queries = [
            m for m in self.aggregator.metrics_history
            if m.execution_time and m.is_slow_query
        ]

        # Trier par temps d'exécution décroissant
        slow_queries.sort(key=lambda m: m.execution_time, reverse=True)

        return [
            {
                'query_name': m.query_name,
                'execution_time': m.execution_time,
                'timestamp': datetime.fromtimestamp(m.start_time).isoformat(),
                'user_id': m.user_id,
                'query_complexity': m.query_complexity,
                'database_queries': m.database_queries,
                'cache_hits': m.cache_hits,
                'cache_misses': m.cache_misses
            }
            for m in slow_queries[:limit]
        ]


# Fonction utilitaire pour configurer le middleware
def setup_performance_monitoring():
    """Configure le monitoring des performances."""
    # Vérifier que le middleware est configuré
    middleware_classes = getattr(settings, 'MIDDLEWARE', [])
    middleware_name = 'django_graphql_auto.middleware.performance.GraphQLPerformanceMiddleware'

    if middleware_name not in middleware_classes:
        logger.warning(
            f"GraphQLPerformanceMiddleware not found in MIDDLEWARE settings. "
            f"Add '{middleware_name}' to MIDDLEWARE to enable performance monitoring."
        )

    # Configurer les seuils par défaut si non définis
    if not hasattr(settings, 'GRAPHQL_SLOW_QUERY_THRESHOLD'):
        settings.GRAPHQL_SLOW_QUERY_THRESHOLD = 1.0

    if not hasattr(settings, 'GRAPHQL_COMPLEXITY_THRESHOLD'):
        settings.GRAPHQL_COMPLEXITY_THRESHOLD = 100

    if not hasattr(settings, 'GRAPHQL_MEMORY_THRESHOLD'):
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
                start_time=start_time
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

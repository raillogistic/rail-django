"""
Performance monitoring views.
"""

from datetime import datetime
from typing import Any

from django.http import JsonResponse
from django.views import View

from .aggregator import get_performance_aggregator


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

    def get_performance_stats(self) -> dict[str, Any]:
        """Retourne les statistiques de performance."""
        return self.aggregator.get_aggregated_stats()

    def get_recent_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
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

    def get_slow_queries(self, limit: int = 20) -> list[dict[str, Any]]:
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

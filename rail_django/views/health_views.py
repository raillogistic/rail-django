"""
Health monitoring views for GraphQL system diagnostics.

This module provides Django views for the health monitoring dashboard
and API endpoints for health data retrieval.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..extensions.health import HealthChecker

logger = logging.getLogger(__name__)


class HealthDashboardView(View):
    """
    Vue principale pour afficher le tableau de bord de santé du système.

    Cette vue sert le template HTML du tableau de bord avec toutes les
    métriques de santé et diagnostics en temps réel.
    """

    def get(self, request):
        """
        Affiche le tableau de bord de santé du système.

        Returns:
            HttpResponse: Template HTML du tableau de bord
        """
        try:
            # Obtenir les données de santé initiales
            health_checker = HealthChecker()
            initial_data = {
                "health_status": health_checker.get_health_report(),
                # Convert dataclass to plain dict for JSON serialization
                "system_metrics": health_checker.get_system_metrics().__dict__,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            context = {
                "initial_data": json.dumps(initial_data, default=str),
                "refresh_interval": getattr(settings, "HEALTH_REFRESH_INTERVAL", 30),
                "auto_refresh_enabled": getattr(settings, "HEALTH_AUTO_REFRESH", True),
            }

            return render(request, "health_dashboard.html", context)

        except Exception as e:
            logger.error(f"Erreur lors du chargement du tableau de bord: {e}")
            return render(
                request,
                "health_dashboard.html",
                {
                    "error": str(e),
                    "initial_data": "{}",
                    "refresh_interval": 30,
                    "auto_refresh_enabled": True,
                },
            )


class HealthAPIView(View):
    """
    API endpoint pour récupérer les données de santé du système.

    Fournit des données JSON pour les requêtes AJAX du tableau de bord
    et les intégrations externes.
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request):
        """
        Récupère les données de santé actuelles du système.

        Returns:
            JsonResponse: Données de santé au format JSON
        """
        try:
            health_checker = HealthChecker()

            # Obtenir toutes les métriques de santé
            schema_health = health_checker.check_schema_health()
            database_health = health_checker.check_database_health()
            cache_health = health_checker.check_cache_health()

            health_data = {
                "health_status": health_checker.get_health_report(),
                "system_metrics": health_checker.get_system_metrics().__dict__,
                "schema_health": getattr(schema_health, "to_dict", lambda: schema_health)(),
                "database_health": [
                    getattr(status, "to_dict", lambda: status)() for status in database_health
                ],
                "cache_health": [
                    getattr(status, "to_dict", lambda: status)() for status in cache_health
                ],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            return JsonResponse(health_data, safe=False)

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des données de santé: {e}")
            return JsonResponse(
                {
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "error",
                },
                status=500,
            )

    def post(self, request):
        """
        Traite les requêtes GraphQL pour les données de santé.

        Args:
            request: Requête HTTP avec query GraphQL

        Returns:
            JsonResponse: Réponse GraphQL avec données de santé
        """
        try:
            # Parser la requête GraphQL
            body = json.loads(request.body.decode("utf-8"))
            query = body.get("query", "")
            # Initialiser le vérificateur de santé
            health_checker = HealthChecker()

            # Traiter différents types de requêtes
            response_data = {"data": {}}

            if "healthStatus" in query:
                response_data["data"]["healthStatus"] = (
                    health_checker.get_health_report()
                )

            if "systemMetrics" in query:
                response_data["data"]["systemMetrics"] = (
                    health_checker.get_system_metrics().__dict__
                )

            if "schemaHealth" in query:
                sh = health_checker.check_schema_health()
                response_data["data"]["schemaHealth"] = getattr(sh, "to_dict", lambda: sh)()

            if "databaseHealth" in query:
                dbh = health_checker.check_database_health()
                response_data["data"]["databaseHealth"] = [
                    getattr(status, "to_dict", lambda: status)() for status in dbh
                ]

            if "cacheHealth" in query:
                ch = health_checker.check_cache_health()
                response_data["data"]["cacheHealth"] = [
                    getattr(status, "to_dict", lambda: status)() for status in ch
                ]

            return JsonResponse(response_data)

        except json.JSONDecodeError:
            return JsonResponse(
                {"errors": [{"message": "Invalid JSON in request body"}]}, status=400
            )
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la requête GraphQL: {e}")
            return JsonResponse({"errors": [{"message": str(e)}]}, status=500)


@require_http_methods(["GET"])
def health_check_endpoint(request):
    """
    Endpoint simple de vérification de santé pour les load balancers.

    Args:
        request: Requête HTTP

    Returns:
        JsonResponse: Statut de santé simple
    """
    try:
        health_checker = HealthChecker()
        health_report = health_checker.get_health_report()

        # Déterminer le code de statut HTTP basé sur la santé
        status_code = 200
        if health_report["overall_status"] == "unhealthy":
            status_code = 503  # Service Unavailable
        elif health_report["overall_status"] == "degraded":
            status_code = 200  # OK mais avec avertissement

        return JsonResponse(
            {
                "status": health_report["overall_status"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "healthy_components": health_report.get("healthy_components", 0),
                "total_components": (
                    health_report.get("healthy_components", 0)
                    + health_report.get("degraded_components", 0)
                    + health_report.get("unhealthy_components", 0)
                ),
            },
            status=status_code,
        )

    except Exception as e:
        logger.error(f"Erreur lors de la vérification de santé: {e}")
        return JsonResponse(
            {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=503,
        )


@require_http_methods(["GET"])
def health_metrics_endpoint(request):
    """
    Endpoint pour les métriques système détaillées.

    Args:
        request: Requête HTTP

    Returns:
        JsonResponse: Métriques système complètes
    """
    try:
        health_checker = HealthChecker()
        metrics = health_checker.get_system_metrics()

        return JsonResponse(
            {
                "metrics": metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "collection_time_ms": metrics.get("collection_time_ms", 0),
            }
        )

    except Exception as e:
        logger.error(f"Erreur lors de la collecte des métriques: {e}")
        return JsonResponse(
            {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()},
            status=500,
        )


@require_http_methods(["GET"])
def health_components_endpoint(request):
    """
    Endpoint pour le statut détaillé de tous les composants.

    Args:
        request: Requête HTTP

    Returns:
        JsonResponse: Statut de tous les composants
    """
    try:
        health_checker = HealthChecker()

        components = {
            "schema": health_checker.check_schema_health(),
            "database": health_checker.check_database_health(),
            "cache": health_checker.check_cache_health(),
        }

        return JsonResponse(
            {
                "components": components,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_components": len(components),
            }
        )

    except Exception as e:
        logger.error(f"Erreur lors de la vérification des composants: {e}")
        return JsonResponse(
            {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()},
            status=500,
        )


class HealthHistoryView(View):
    """
    Vue pour l'historique des données de santé.

    Permet de récupérer les données historiques pour les graphiques
    et l'analyse des tendances.
    """

    def get(self, request):
        """
        Récupère l'historique des données de santé.

        Query parameters:
            - hours: Nombre d'heures d'historique (défaut: 24)
            - interval: Intervalle entre les points (défaut: 5 minutes)

        Returns:
            JsonResponse: Données historiques
        """
        try:
            hours = int(request.GET.get("hours", 24))
            interval_minutes = int(request.GET.get("interval", 5))

            # Dans une implémentation réelle, ceci viendrait d'une base de données
            # Pour l'instant, on génère des données d'exemple
            historical_data = self._generate_sample_history(hours, interval_minutes)

            return JsonResponse(
                {
                    "history": historical_data,
                    "period_hours": hours,
                    "interval_minutes": interval_minutes,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except ValueError as e:
            return JsonResponse(
                {
                    "error": f"Paramètres invalides: {e}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                status=400,
            )
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'historique: {e}")
            return JsonResponse(
                {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()},
                status=500,
            )

    def _generate_sample_history(
        self, hours: int, interval_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        Génère des données d'historique d'exemple.

        Args:
            hours: Nombre d'heures d'historique
            interval_minutes: Intervalle entre les points

        Returns:
            List[Dict]: Données historiques d'exemple
        """
        import random
        from datetime import timedelta

        history = []
        current_time = datetime.now(timezone.utc)

        # Générer des points de données
        total_points = (hours * 60) // interval_minutes

        for i in range(total_points):
            timestamp = current_time - timedelta(minutes=i * interval_minutes)

            # Générer des métriques réalistes avec des variations
            base_cpu = 25 + random.uniform(-10, 15)
            base_memory = 60 + random.uniform(-20, 25)

            history.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "cpu_usage_percent": max(0, min(100, base_cpu)),
                    "memory_usage_percent": max(0, min(100, base_memory)),
                    "cache_hit_rate": max(70, min(100, 85 + random.uniform(-10, 10))),
                    "active_connections": max(0, int(50 + random.uniform(-20, 30))),
                    "response_time_ms": max(10, int(100 + random.uniform(-50, 100))),
                    "healthy_components": random.choice([3, 4, 4, 4]),  # Mostly healthy
                    "degraded_components": random.choice([0, 0, 1, 0]),
                    "unhealthy_components": random.choice([0, 0, 0, 1]),
                }
            )

        return list(reversed(history))  # Chronological order


# Fonction utilitaire pour l'intégration avec les URLs
def get_health_urls():
    """
    Retourne les patterns d'URL pour les vues de santé.

    Returns:
        List: Patterns d'URL Django
    """
    from django.urls import path

    return [
        path("health/", HealthDashboardView.as_view(), name="health_dashboard"),
        path("health/api/", HealthAPIView.as_view(), name="health_api"),
        path("health/check/", health_check_endpoint, name="health_check"),
        path("health/metrics/", health_metrics_endpoint, name="health_metrics"),
        path(
            "health/components/", health_components_endpoint, name="health_components"
        ),
        path("health/history/", HealthHistoryView.as_view(), name="health_history"),
    ]

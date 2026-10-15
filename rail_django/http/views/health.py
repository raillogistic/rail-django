"""
Health monitoring views for GraphQL system diagnostics.

This module provides Django views for the health monitoring dashboard
and API endpoints for health data retrieval.
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_http_methods

from rail_django.extensions.health import HealthChecker

logger = logging.getLogger(__name__)


def require_health_access(view_func):
    """Protect diagnostic data while keeping liveness endpoints public."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if getattr(settings, "HEALTH_DIAGNOSTICS_PUBLIC", False):
            return view_func(request, *args, **kwargs)

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not (
            getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
        ):
            return JsonResponse({"error": "Staff privileges required"}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


@method_decorator(require_health_access, name="dispatch")
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
            comprehensive_report = health_checker.get_comprehensive_health_report()
            health_status = health_checker.summarize_report(comprehensive_report)
            initial_data = {
                "health_status": health_status,
                "system_metrics": comprehensive_report.get("system_metrics", {}),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            context = {
                "initial_data": json.dumps(initial_data, default=str),
                "refresh_interval": getattr(settings, "HEALTH_REFRESH_INTERVAL", 30),
                "auto_refresh_enabled": getattr(settings, "HEALTH_AUTO_REFRESH", True),
            }

            return render(request, "health_dashboard.html", context)

        except Exception:
            logger.exception("Unable to load the health dashboard")
            return render(
                request,
                "health_dashboard.html",
                {
                    "error": "Health data is unavailable.",
                    "initial_data": "{}",
                    "refresh_interval": 30,
                    "auto_refresh_enabled": True,
                },
            )


@method_decorator(require_health_access, name="dispatch")
class HealthAPIView(View):
    """
    API endpoint pour récupérer les données de santé du système.

    Fournit des données JSON pour les requêtes AJAX du tableau de bord
    et les intégrations externes.
    """

    def get(self, request):
        """
        Récupère les données de santé actuelles du système.

        Returns:
            JsonResponse: Données de santé au format JSON
        """
        try:
            health_checker = HealthChecker()

            # Obtenir toutes les métriques de santé
            comprehensive_report = health_checker.get_comprehensive_health_report()
            health_status = health_checker.summarize_report(comprehensive_report)
            components = comprehensive_report.get("components", {})

            health_data = {
                "health_status": health_status,
                "system_metrics": comprehensive_report.get("system_metrics", {}),
                "schema_health": components.get("schema", {}),
                "database_health": components.get("databases", []),
                "cache_health": components.get("caches", []),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            return JsonResponse(health_data, safe=False)

        except Exception:
            logger.exception("Unable to retrieve health data")
            return JsonResponse(
                {
                    "error": "Health data is unavailable.",
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
            needs_report = any(
                key in query
                for key in (
                    "healthStatus",
                    "schemaHealth",
                    "databaseHealth",
                    "cacheHealth",
                )
            )
            comprehensive_report = (
                health_checker.get_comprehensive_health_report()
                if needs_report
                else None
            )
            components = (
                comprehensive_report.get("components", {})
                if comprehensive_report
                else {}
            )

            if "healthStatus" in query:
                response_data["data"]["healthStatus"] = health_checker.summarize_report(
                    comprehensive_report
                )

            if "systemMetrics" in query:
                if comprehensive_report is not None:
                    response_data["data"]["systemMetrics"] = comprehensive_report.get(
                        "system_metrics", {}
                    )
                else:
                    response_data["data"]["systemMetrics"] = asdict(
                        health_checker.get_system_metrics()
                    )

            if "schemaHealth" in query:
                response_data["data"]["schemaHealth"] = components.get("schema", {})

            if "databaseHealth" in query:
                response_data["data"]["databaseHealth"] = components.get(
                    "databases", []
                )

            if "cacheHealth" in query:
                response_data["data"]["cacheHealth"] = components.get("caches", [])

            return JsonResponse(response_data)

        except json.JSONDecodeError:
            return JsonResponse(
                {"errors": [{"message": "Invalid JSON in request body"}]}, status=400
            )
        except Exception:
            logger.exception("Unable to process a health API request")
            return JsonResponse(
                {"errors": [{"message": "Health data is unavailable."}]}, status=500
            )


@require_http_methods(["GET"])
def health_liveness_endpoint(request):
    """Return a dependency-free process liveness response."""
    return JsonResponse(
        {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


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
        cache_ttl = getattr(settings, "HEALTH_CHECK_CACHE_TTL_SECONDS", None)
        health_report = health_checker.summarize_report(
            health_checker.get_comprehensive_health_report(
                use_cache=True, ttl_seconds=cache_ttl
            )
        )

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

    except Exception:
        logger.exception("Health check failed")
        return JsonResponse(
            {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=503,
        )


@require_health_access
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
        metrics_dict = asdict(metrics)

        return JsonResponse(
            {
                "metrics": metrics_dict,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "collection_time_ms": metrics_dict.get("collection_time_ms", 0),
            }
        )

    except Exception:
        logger.exception("Unable to collect health metrics")
        return JsonResponse(
            {
                "error": "Health metrics are unavailable.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=500,
        )


@require_health_access
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
        comprehensive_report = health_checker.get_comprehensive_health_report()
        report_components = comprehensive_report.get("components", {})

        components = {
            "schema": report_components.get("schema", {}),
            "database": report_components.get("databases", []),
            "cache": report_components.get("caches", []),
        }

        return JsonResponse(
            {
                "components": components,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_components": len(components),
            }
        )

    except Exception:
        logger.exception("Unable to inspect health components")
        return JsonResponse(
            {
                "error": "Health components are unavailable.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=500,
        )


@method_decorator(require_health_access, name="dispatch")
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
        return JsonResponse(
            {
                "error": "Health history storage is not configured.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=501,
        )


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
        path("health/live/", health_liveness_endpoint, name="health_live"),
        path("health/ready/", health_check_endpoint, name="health_ready"),
        path("health/metrics/", health_metrics_endpoint, name="health_metrics"),
        path(
            "health/components/", health_components_endpoint, name="health_components"
        ),
        path("health/history/", HealthHistoryView.as_view(), name="health_history"),
    ]

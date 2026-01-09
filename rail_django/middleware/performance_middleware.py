"""
Performance Monitoring Middleware for Django GraphQL Auto

This middleware automatically collects performance metrics for all GraphQL queries,
including execution time, complexity analysis, and slow query detection.
"""

import django
import logging
import time
import tracemalloc
from typing import Any, Dict, Optional

from django.db import connection
from django.utils.deprecation import MiddlewareMixin
from graphql import GraphQLError

from ..extensions.performance_metrics import performance_collector

logger = logging.getLogger(__name__)


class GraphQLPerformanceMiddleware(MiddlewareMixin):
    """
    Middleware pour surveiller les performances des requêtes GraphQL.

    Collecte automatiquement:
    - Temps d'exécution des requêtes
    - Analyse de complexité et profondeur
    - Utilisation mémoire
    - Statistiques de cache et base de données
    - Détection des requêtes lentes
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.get_response = get_response

        # Configuration par défaut
        self.slow_query_threshold = getattr(
            django.conf.settings, "GRAPHQL_SLOW_QUERY_THRESHOLD", 1.0
        )
        self.enable_memory_tracking = getattr(
            django.conf.settings, "GRAPHQL_ENABLE_MEMORY_TRACKING", True
        )
        self.log_slow_queries = getattr(
            django.conf.settings, "GRAPHQL_LOG_SLOW_QUERIES", True
        )

    def process_request(self, request):
        """Initialise le suivi des performances au début de la requête."""
        if self._is_graphql_request(request):
            # Démarrer le suivi du temps
            request._graphql_start_time = time.time()

            # Démarrer le suivi mémoire si activé
            if self.enable_memory_tracking:
                tracemalloc.start()
                request._graphql_memory_start = tracemalloc.get_traced_memory()[0]

            # Compter les requêtes DB initiales
            request._graphql_initial_queries = len(connection.queries)

            # Caching removed: initialize cache metrics to zero
            request._graphql_initial_cache_hits = 0
            request._graphql_initial_cache_misses = 0

    def process_response(self, request, response):
        """Collecte les métriques de performance à la fin de la requête."""
        if self._is_graphql_request(request) and hasattr(
            request, "_graphql_start_time"
        ):
            try:
                self._collect_performance_metrics(request, response)
            except Exception as e:
                logger.error(f"Failed to collect performance metrics: {e}")

        return response

    def process_exception(self, request, exception):
        """Collecte les métriques même en cas d'exception."""
        if self._is_graphql_request(request) and hasattr(
            request, "_graphql_start_time"
        ):
            try:
                self._collect_performance_metrics(request, None, str(exception))
            except Exception as e:
                logger.error(f"Failed to collect performance metrics on exception: {e}")

        return None

    def _is_graphql_request(self, request) -> bool:
        """Vérifie si la requête est une requête GraphQL."""
        return (
            request.path.endswith("/graphql/")
            or request.path.endswith("/graphql")
            or "graphql" in request.content_type.lower()
            if hasattr(request, "content_type")
            else False
        )

    def _collect_performance_metrics(
        self, request, response, error_message: Optional[str] = None
    ):
        """Collecte et enregistre les métriques de performance."""

        # Calculer le temps d'exécution
        execution_time = time.time() - request._graphql_start_time

        # Extraire la requête GraphQL
        query_text = self._extract_query_text(request)
        if not query_text:
            return

        # Calculer l'utilisation mémoire
        memory_usage_mb = 0.0
        if self.enable_memory_tracking and hasattr(request, "_graphql_memory_start"):
            try:
                current_memory = tracemalloc.get_traced_memory()[0]
                memory_usage_mb = (
                    (current_memory - request._graphql_memory_start) / 1024 / 1024
                )
                tracemalloc.stop()
            except Exception:
                pass

        # Calculer les requêtes DB
        db_queries = len(connection.queries) - request._graphql_initial_queries

        # Caching removed: report zero cache hits/misses
        cache_hits = 0
        cache_misses = 0

        # Obtenir l'ID utilisateur si disponible
        user_id = None
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = str(request.user.id)

        # Enregistrer les métriques
        performance_collector.record_query_execution(
            query_text=query_text,
            execution_time=execution_time,
            user_id=user_id,
            database_queries=db_queries,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            memory_usage_mb=memory_usage_mb,
            error_message=error_message,
        )

        # Logger les requêtes lentes si activé
        if (
            self.log_slow_queries
            and execution_time > self.slow_query_threshold
            and not error_message
        ):
            logger.warning(
                f"Slow GraphQL query detected: {execution_time:.2f}s "
                f"(threshold: {self.slow_query_threshold}s) "
                f"- DB queries: {db_queries} "
                f"- Memory: {memory_usage_mb:.2f}MB "
                f"- User: {user_id or 'anonymous'}"
            )

    def _extract_query_text(self, request) -> Optional[str]:
        """Extrait le texte de la requête GraphQL."""
        try:
            if request.method == "POST":
                if hasattr(request, "body"):
                    import json

                    body = json.loads(request.body.decode("utf-8"))
                    return body.get("query", "")
                elif hasattr(request, "POST"):
                    return request.POST.get("query", "")
            elif request.method == "GET":
                return request.GET.get("query", "")
        except Exception as e:
            logger.debug(f"Failed to extract GraphQL query: {e}")

        return None


class GraphQLExecutionMiddleware:
    """
    Middleware GraphQL pour l'exécution des requêtes.

    Ce middleware s'intègre directement dans le processus d'exécution GraphQL
    pour une collecte de métriques plus précise.
    """

    def __init__(self):
        self.slow_query_threshold = 1.0

    def resolve(self, next_resolver, root, info, **args):
        """Middleware de résolution pour collecter les métriques par champ."""

        # Démarrer le chronométrage
        start_time = time.time()

        try:
            # Exécuter le résolveur
            result = next_resolver(root, info, **args)

            # Calculer le temps d'exécution
            execution_time = time.time() - start_time

            # Enregistrer les métriques si c'est une requête racine
            if info.path and len(info.path.as_list()) == 1:
                self._record_field_metrics(info, execution_time)

            return result

        except Exception as e:
            execution_time = time.time() - start_time

            # Enregistrer l'erreur
            if info.path and len(info.path.as_list()) == 1:
                self._record_field_metrics(info, execution_time, str(e))

            raise

    def _record_field_metrics(
        self, info, execution_time: float, error_message: Optional[str] = None
    ):
        """Enregistre les métriques pour un champ spécifique."""

        try:
            # Construire une requête simplifiée pour ce champ
            field_name = info.field_name
            query_text = f"query {{ {field_name} }}"

            # Obtenir l'ID utilisateur du contexte
            user_id = None
            if hasattr(info.context, "user") and info.context.user.is_authenticated:
                user_id = str(info.context.user.id)

            # Enregistrer les métriques
            performance_collector.record_query_execution(
                query_text=query_text,
                execution_time=execution_time,
                user_id=user_id,
                database_queries=0,  # Sera mis à jour par le middleware Django
                cache_hits=0,
                cache_misses=0,
                memory_usage_mb=0.0,
                error_message=error_message,
            )

        except Exception as e:
            logger.debug(f"Failed to record field metrics: {e}")


# Instance globale du middleware d'exécution
graphql_execution_middleware = GraphQLExecutionMiddleware()


def get_performance_middleware_config():
    """
    Retourne la configuration recommandée pour le middleware de performance.

    À ajouter dans settings.py:

    MIDDLEWARE = [
        # ... autres middlewares ...
        'rail_django.middleware.performance_middleware.GraphQLPerformanceMiddleware',
    ]

    # Configuration optionnelle
    GRAPHQL_SLOW_QUERY_THRESHOLD = 1.0  # secondes
    GRAPHQL_ENABLE_MEMORY_TRACKING = True
    GRAPHQL_LOG_SLOW_QUERIES = True
    """

    return {
        "middleware_class": "rail_django.middleware.performance_middleware.GraphQLPerformanceMiddleware",
        "settings": {
            "GRAPHQL_SLOW_QUERY_THRESHOLD": 1.0,
            "GRAPHQL_ENABLE_MEMORY_TRACKING": True,
            "GRAPHQL_LOG_SLOW_QUERIES": True,
        },
    }

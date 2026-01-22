"""
Performance monitoring utility functions.
"""

import logging
import time
from typing import Callable, Optional

from django.conf import settings

from .aggregator import get_performance_aggregator
from .metrics import RequestMetrics

logger = logging.getLogger(__name__)


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

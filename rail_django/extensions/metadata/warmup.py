"""Cache warming utilities for metadata.

This module provides utilities for pre-warming the metadata cache
and retrieving cache statistics. Cache warming can significantly
improve response times for metadata queries by populating the cache
before user requests arrive.
"""

import logging
from typing import Any, Dict, Optional

from django.apps import apps

logger = logging.getLogger(__name__)


def _get_metadata_extractor():
    """Lazily import ModelMetadataExtractor to avoid circular imports.

    Returns:
        ModelMetadataExtractor: Instance for metadata extraction.
    """
    from ..metadata import ModelMetadataExtractor

    return ModelMetadataExtractor()


def warm_metadata_cache(
    app_name: Optional[str] = None,
    model_name: Optional[str] = None,
    user: Any = None,
) -> None:
    """Pre-warm metadata cache for specified models.

    Populates the metadata cache ahead of time to improve response
    times for subsequent metadata queries. Can target a specific
    model, all models in an app, or all models in the project.

    Args:
        app_name: Specific app to warm cache for. If None with model_name None,
            warms cache for all apps.
        model_name: Specific model to warm cache for. Requires app_name.
        user: User context for permission-based caching. If None, caches
            anonymous metadata.

    Example:
        >>> # Warm cache for a specific model
        >>> warm_metadata_cache(app_name="products", model_name="Product")

        >>> # Warm cache for all models in an app
        >>> warm_metadata_cache(app_name="products")

        >>> # Warm cache for all models in the project
        >>> warm_metadata_cache()

        >>> # Warm cache with user context for permission-based caching
        >>> warm_metadata_cache(app_name="products", user=request.user)
    """
    extractor = _get_metadata_extractor()

    if app_name and model_name:
        # Warm cache for specific model
        try:
            extractor.extract_model_metadata(app_name, model_name, user)
            logger.info("Warmed metadata cache for %s.%s", app_name, model_name)
        except Exception as e:
            logger.error(
                "Failed to warm cache for %s.%s: %s", app_name, model_name, e
            )
    elif app_name:
        # Warm cache for all models in app
        try:
            app_config = apps.get_app_config(app_name)
            model_count = 0
            for model in app_config.get_models():
                try:
                    extractor.extract_model_metadata(app_name, model.__name__, user)
                    model_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to warm cache for %s.%s: %s",
                        app_name,
                        model.__name__,
                        e,
                    )
            logger.info(
                "Warmed metadata cache for app %s (%d models)", app_name, model_count
            )
        except Exception as e:
            logger.error("Failed to warm cache for app %s: %s", app_name, e)
    else:
        # Warm cache for all models
        total_models = 0
        failed_models = 0
        for app_config in apps.get_app_configs():
            for model in app_config.get_models():
                try:
                    extractor.extract_model_metadata(
                        app_config.label, model.__name__, user
                    )
                    total_models += 1
                except Exception as e:
                    failed_models += 1
                    logger.warning(
                        "Failed to warm cache for %s.%s: %s",
                        app_config.label,
                        model.__name__,
                        e,
                    )
        logger.info(
            "Warmed metadata cache for all models (%d succeeded, %d failed)",
            total_models,
            failed_models,
        )


def warm_table_metadata_cache(
    app_name: Optional[str] = None,
    model_name: Optional[str] = None,
    user: Any = None,
    counts: bool = False,
) -> None:
    """Pre-warm table metadata cache for specified models.

    Similar to warm_metadata_cache but specifically targets the table
    metadata extraction which is used for list/table views.

    Args:
        app_name: Specific app to warm cache for.
        model_name: Specific model to warm cache for.
        user: User context for permission-based caching.
        counts: Whether to include relationship counts in cached data.

    Example:
        >>> # Warm table cache for a specific model
        >>> warm_table_metadata_cache(app_name="products", model_name="Product")
    """
    from ..metadata import ModelTableExtractor

    extractor = ModelTableExtractor()

    if app_name and model_name:
        try:
            extractor.extract_model_table_metadata(
                app_name=app_name,
                model_name=model_name,
                counts=counts,
                user=user,
            )
            logger.info("Warmed table metadata cache for %s.%s", app_name, model_name)
        except Exception as e:
            logger.error(
                "Failed to warm table cache for %s.%s: %s", app_name, model_name, e
            )
    elif app_name:
        try:
            app_config = apps.get_app_config(app_name)
            model_count = 0
            for model in app_config.get_models():
                try:
                    extractor.extract_model_table_metadata(
                        app_name=app_name,
                        model_name=model.__name__,
                        counts=counts,
                        user=user,
                    )
                    model_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to warm table cache for %s.%s: %s",
                        app_name,
                        model.__name__,
                        e,
                    )
            logger.info(
                "Warmed table metadata cache for app %s (%d models)",
                app_name,
                model_count,
            )
        except Exception as e:
            logger.error("Failed to warm table cache for app %s: %s", app_name, e)
    else:
        total_models = 0
        failed_models = 0
        for app_config in apps.get_app_configs():
            for model in app_config.get_models():
                try:
                    extractor.extract_model_table_metadata(
                        app_name=app_config.label,
                        model_name=model.__name__,
                        counts=counts,
                        user=user,
                    )
                    total_models += 1
                except Exception as e:
                    failed_models += 1
                    logger.warning(
                        "Failed to warm table cache for %s.%s: %s",
                        app_config.label,
                        model.__name__,
                        e,
                    )
        logger.info(
            "Warmed table metadata cache for all models (%d succeeded, %d failed)",
            total_models,
            failed_models,
        )


def get_cache_stats() -> Dict[str, Any]:
    """Return TTL cache statistics for model table metadata.

    Provides insight into cache performance including hit/miss rates,
    cache size, and configuration.

    Returns:
        Dict[str, Any]: Cache statistics including:
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_rate: Ratio of hits to total requests (0.0-1.0)
            - sets: Number of cache entries set
            - deletes: Number of cache entries deleted
            - invalidations: Number of cache invalidation events
            - default_timeout: Configured cache timeout in seconds
            - size: Current number of entries in the cache

    Example:
        >>> stats = get_cache_stats()
        >>> print(f"Cache hit rate: {stats['hit_rate']:.2%}")
        Cache hit rate: 85.00%

        >>> print(f"Cache size: {stats['size']} entries")
        Cache size: 42 entries
    """
    from .cache import (
        _get_table_cache_timeout,
        _table_cache,
        _table_cache_lock,
        _table_cache_stats,
    )

    # Safely snapshot current stats and size under lock
    with _table_cache_lock:
        stats_snapshot = dict(_table_cache_stats)
        cache_size = len(_table_cache)

    total_requests = stats_snapshot.get("hits", 0) + stats_snapshot.get("misses", 0)
    hit_rate = (
        (stats_snapshot.get("hits", 0) / total_requests) if total_requests else 0.0
    )

    return {
        "hits": stats_snapshot.get("hits", 0),
        "misses": stats_snapshot.get("misses", 0),
        "hit_rate": hit_rate,
        "sets": stats_snapshot.get("sets", 0),
        "deletes": stats_snapshot.get("deletes", 0),
        "invalidations": stats_snapshot.get("invalidations", 0),
        "default_timeout": _get_table_cache_timeout(),
        "size": cache_size,
    }


def get_metadata_cache_stats() -> Dict[str, Any]:
    """Return cache statistics for general metadata cache.

    Similar to get_cache_stats but for the general metadata cache
    used by model_metadata queries.

    Returns:
        Dict[str, Any]: Cache statistics for metadata cache.

    Example:
        >>> stats = get_metadata_cache_stats()
        >>> print(f"Metadata cache hit rate: {stats['hit_rate']:.2%}")
    """
    from .cache import (
        _metadata_cache,
        _metadata_cache_lock,
        _metadata_cache_stats,
    )

    with _metadata_cache_lock:
        stats_snapshot = dict(_metadata_cache_stats)
        cache_size = len(_metadata_cache)

    total_requests = stats_snapshot.get("hits", 0) + stats_snapshot.get("misses", 0)
    hit_rate = (
        (stats_snapshot.get("hits", 0) / total_requests) if total_requests else 0.0
    )

    return {
        "hits": stats_snapshot.get("hits", 0),
        "misses": stats_snapshot.get("misses", 0),
        "hit_rate": hit_rate,
        "sets": stats_snapshot.get("sets", 0),
        "deletes": stats_snapshot.get("deletes", 0),
        "invalidations": stats_snapshot.get("invalidations", 0),
        "size": cache_size,
    }


def get_combined_cache_stats() -> Dict[str, Any]:
    """Return combined statistics for all metadata caches.

    Aggregates statistics from both the table cache and general
    metadata cache.

    Returns:
        Dict[str, Any]: Combined cache statistics with separate sections.

    Example:
        >>> stats = get_combined_cache_stats()
        >>> print(f"Table cache: {stats['table']['size']} entries")
        >>> print(f"Metadata cache: {stats['metadata']['size']} entries")
    """
    return {
        "table": get_cache_stats(),
        "metadata": get_metadata_cache_stats(),
    }


def clear_all_caches() -> None:
    """Clear all metadata caches.

    Completely empties the table cache, metadata cache, and filter
    class cache. Useful for development and testing.

    Example:
        >>> clear_all_caches()
        >>> stats = get_cache_stats()
        >>> assert stats['size'] == 0
    """
    from .cache import invalidate_metadata_cache

    invalidate_metadata_cache()
    logger.info("All metadata caches cleared")


__all__ = [
    "warm_metadata_cache",
    "warm_table_metadata_cache",
    "get_cache_stats",
    "get_metadata_cache_stats",
    "get_combined_cache_stats",
    "clear_all_caches",
]

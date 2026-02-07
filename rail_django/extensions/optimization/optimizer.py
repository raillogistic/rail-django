"""
Query optimizer for applying optimizations to Django querysets.
"""

import logging
from typing import Dict, List, Optional, Union

from django.db.models import Prefetch, QuerySet
from django.db.models.fields.related import ManyToManyField
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from graphql import GraphQLResolveInfo

from .config import QueryOptimizationConfig
from .analyzer import QueryAnalyzer

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Optimizes Django querysets based on GraphQL query analysis."""

    def __init__(self, config: QueryOptimizationConfig):
        self.config = config
        self.analyzer = QueryAnalyzer(config)

    def optimize_queryset(
        self, queryset: QuerySet, info: GraphQLResolveInfo, model: type[models.Model]
    ) -> QuerySet:
        """
        Optimize a Django queryset based on GraphQL query analysis.
        """
        if not self.config.auto_optimize_queries:
            return queryset

        analysis = self.analyzer.analyze_query(info, model)

        # Apply select_related optimization
        if self.config.enable_select_related and analysis.select_related_fields:
            queryset = queryset.select_related(*analysis.select_related_fields)
            logger.debug(f"Applied select_related: {analysis.select_related_fields}")

        # Apply prefetch_related optimization
        if self.config.enable_prefetch_related and analysis.prefetch_related_fields:
            prefetch_fields, skipped_fields = self._filter_valid_prefetch_fields(
                model, analysis.prefetch_related_fields
            )
            if skipped_fields:
                logger.debug(
                    f"Skipped invalid prefetch_related paths: {skipped_fields}"
                )
            if not prefetch_fields:
                return queryset

            prefetch_objects = self._build_prefetch_objects(
                model, prefetch_fields
            )
            queryset = queryset.prefetch_related(*prefetch_objects)
            logger.debug(
                f"Applied prefetch_related: {prefetch_fields}"
            )

        return queryset

    def _filter_valid_prefetch_fields(
        self, model: type[models.Model], fields: list[str]
    ) -> tuple[list[str], list[str]]:
        valid_fields: list[str] = []
        invalid_fields: list[str] = []
        seen: set[str] = set()

        for field_path in fields:
            if not field_path or field_path in seen:
                continue
            seen.add(field_path)
            if self._is_valid_prefetch_path(model, field_path):
                valid_fields.append(field_path)
            else:
                invalid_fields.append(field_path)

        return valid_fields, invalid_fields

    def _is_valid_prefetch_path(
        self, model: type[models.Model], field_path: str
    ) -> bool:
        current_model = model
        for segment in field_path.split("__"):
            related_model = self._resolve_related_model(current_model, segment)
            if related_model is None:
                return False
            current_model = related_model
        return True

    @staticmethod
    def _resolve_related_model(
        current_model: type[models.Model], segment: str
    ) -> Optional[type[models.Model]]:
        try:
            field = current_model._meta.get_field(segment)
            if getattr(field, "is_relation", False):
                return getattr(field, "related_model", None)
            return None
        except FieldDoesNotExist:
            pass

        if hasattr(current_model._meta, "related_objects"):
            for rel in current_model._meta.related_objects:
                if rel.get_accessor_name() == segment:
                    return rel.related_model

        return None

    def _build_prefetch_objects(
        self, model: type[models.Model], fields: list[str]
    ) -> list[Union[str, Prefetch]]:
        """Build Prefetch objects for complex prefetch_related optimization."""
        prefetch_objects = []

        for field_name in fields:
            if "__" in field_name:
                prefetch_objects.append(field_name)
                continue
            try:
                field = model._meta.get_field(field_name)
                if isinstance(field, ManyToManyField):
                    prefetch_objects.append(field_name)
                else:
                    related_model = field.related_model
                    prefetch_objects.append(
                        Prefetch(field_name, queryset=related_model.objects.all())
                    )
            except FieldDoesNotExist:
                prefetch_objects.append(field_name)

        return prefetch_objects


# Global optimization manager instances
_optimization_config = QueryOptimizationConfig()
_query_optimizer = QueryOptimizer(_optimization_config)
_optimizer_by_schema: dict[str, QueryOptimizer] = {}


def _build_optimizer_config(schema_name: Optional[str]) -> QueryOptimizationConfig:
    """Build optimizer config from performance settings."""
    from ...config_proxy import get_settings_proxy

    proxy = get_settings_proxy(schema_name)
    perf_settings = proxy.get("performance_settings", {}) or {}

    return QueryOptimizationConfig(
        enable_select_related=perf_settings.get("enable_select_related", True),
        enable_prefetch_related=perf_settings.get("enable_prefetch_related", True),
        max_prefetch_depth=perf_settings.get(
            "max_prefetch_depth", perf_settings.get("max_query_depth", 3)
        ),
        auto_optimize_queries=perf_settings.get("enable_query_optimization", True),
        enable_schema_caching=False,
        enable_query_caching=bool(perf_settings.get("enable_query_caching", False)),
        enable_field_caching=False,
        cache_timeout=perf_settings.get(
            "query_cache_timeout", perf_settings.get("cache_timeout", 300)
        ),
        query_cache_user_specific=bool(
            perf_settings.get("query_cache_user_specific", False)
        ),
        query_cache_scope=perf_settings.get("query_cache_scope", "schema"),
        enable_complexity_analysis=perf_settings.get("enable_query_cost_analysis", False),
        max_query_complexity=perf_settings.get("max_query_complexity", 1000),
        max_query_depth=perf_settings.get("max_query_depth", 10),
        query_timeout=perf_settings.get("query_timeout", 30),
        enable_performance_monitoring=bool(
            perf_settings.get("enable_performance_monitoring", False)
        ),
        log_slow_queries=bool(perf_settings.get("log_slow_queries", False)),
        slow_query_threshold=float(perf_settings.get("slow_query_threshold", 1.0)),
    )


def get_optimizer(schema_name: Optional[str] = None) -> QueryOptimizer:
    """Get a query optimizer instance for a schema (selection-set driven)."""
    if not schema_name:
        return _query_optimizer

    if schema_name not in _optimizer_by_schema:
        config = _build_optimizer_config(schema_name)
        _optimizer_by_schema[schema_name] = QueryOptimizer(config)

    return _optimizer_by_schema[schema_name]


def configure_optimization(config: QueryOptimizationConfig) -> None:
    """Configure global optimization settings."""
    global _optimization_config, _query_optimizer
    from .monitor import _performance_monitor, _monitor_by_schema, PerformanceMonitor

    _optimization_config = config
    _query_optimizer = QueryOptimizer(config)
    
    # Update performance monitor as well
    import sys
    monitor_mod = sys.modules.get('rail_django.extensions.optimization.monitor')
    if monitor_mod:
        monitor_mod._performance_monitor = PerformanceMonitor(config)
        monitor_mod._monitor_by_schema.clear()

    _optimizer_by_schema.clear()
    logger.info("Performance optimization configured")

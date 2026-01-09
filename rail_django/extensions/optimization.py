"""
Performance Optimization System for Django GraphQL Auto-Generation

This module provides comprehensive performance optimization features including:
- N+1 Query Prevention with automatic select_related and prefetch_related
- Multi-level caching strategies (schema, query, field-level)
- Query complexity analysis and optimization
- Resource usage monitoring and timeout handling
"""

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

import graphene
from django.core.exceptions import FieldDoesNotExist
from django.db import connection, models
from django.db.models import Prefetch, QuerySet
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from django.db.models.fields.reverse_related import (
    ManyToManyRel,
    ManyToOneRel,
    OneToOneRel,
)
from graphql import GraphQLResolveInfo
from graphql.execution.collect_fields import collect_fields

# Caching removed from project: no cache imports

logger = logging.getLogger(__name__)


@dataclass
class QueryOptimizationConfig:
    """Configuration for query optimization features."""

    # N+1 Query Prevention
    enable_select_related: bool = True
    enable_prefetch_related: bool = True
    max_prefetch_depth: int = 3
    auto_optimize_queries: bool = True

    # Caching
    enable_schema_caching: bool = True
    enable_query_caching: bool = True
    enable_field_caching: bool = True
    cache_timeout: int = 300  # 5 minutes

    # Query Optimization
    enable_complexity_analysis: bool = True
    max_query_complexity: int = 1000
    max_query_depth: int = 10
    query_timeout: int = 30  # seconds

    # Resource Monitoring
    enable_performance_monitoring: bool = True
    log_slow_queries: bool = True
    slow_query_threshold: float = 1.0  # seconds


@dataclass
class QueryAnalysisResult:
    """Result of query analysis for optimization."""

    requested_fields: Set[str] = field(default_factory=set)
    select_related_fields: List[str] = field(default_factory=list)
    prefetch_related_fields: List[str] = field(default_factory=list)
    complexity_score: int = 0
    depth: int = 0
    estimated_queries: int = 1


@dataclass
class PerformanceMetrics:
    """Performance metrics for query execution."""

    execution_time: float = 0.0
    query_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    complexity_score: int = 0
    memory_usage: int = 0


class QueryAnalyzer:
    """Analyzes GraphQL queries to extract optimization information."""

    def __init__(self, config: QueryOptimizationConfig):
        self.config = config

    def analyze_query(
        self, info: GraphQLResolveInfo, model: Type[models.Model]
    ) -> QueryAnalysisResult:
        """
        Analyze a GraphQL query to determine optimization strategies.

        Args:
            info: GraphQL resolve info containing query details
            model: Django model being queried

        Returns:
            QueryAnalysisResult with optimization recommendations
        """
        result = QueryAnalysisResult()

        # Extract requested fields from GraphQL query
        result.requested_fields = self._extract_requested_fields(info)

        # Analyze relationships for optimization
        result.select_related_fields = self._get_select_related_fields(
            model, result.requested_fields
        )
        result.prefetch_related_fields = self._get_prefetch_related_fields(
            model, result.requested_fields
        )

        # Calculate complexity and depth
        result.complexity_score = self._calculate_complexity(info)
        result.depth = self._calculate_depth(info)

        # Estimate number of queries without optimization
        result.estimated_queries = self._estimate_query_count(
            model, result.requested_fields
        )

        return result

    def _extract_requested_fields(self, info: GraphQLResolveInfo) -> Set[str]:
        """Extract requested fields from GraphQL query."""
        try:
            # Extract field names directly from the selection set
            # This is more reliable than using collect_fields which has version compatibility issues
            requested_fields = set()

            if info.field_nodes and info.field_nodes[0].selection_set:
                for selection in info.field_nodes[0].selection_set.selections:
                    # Handle field selections
                    if hasattr(selection, "name") and hasattr(selection.name, "value"):
                        requested_fields.add(selection.name.value)
                    # Handle inline fragments and fragment spreads
                    elif (
                        hasattr(selection, "selection_set") and selection.selection_set
                    ):
                        for sub_selection in selection.selection_set.selections:
                            if hasattr(sub_selection, "name") and hasattr(
                                sub_selection.name, "value"
                            ):
                                requested_fields.add(sub_selection.name.value)

            return requested_fields
        except Exception as e:
            logger.warning(f"Failed to extract requested fields: {e}")
            return set()

    def _get_select_related_fields(
        self, model: Type[models.Model], requested_fields: Set[str]
    ) -> List[str]:
        """Determine which fields should use select_related."""
        select_related = []

        for field_name in requested_fields:
            try:
                field = model._meta.get_field(field_name)
                if isinstance(field, (ForeignKey, OneToOneField)):
                    select_related.append(field_name)
            except FieldDoesNotExist:
                # Field might be a reverse relationship or method
                continue

        return select_related

    def _get_prefetch_related_fields(
        self, model: Type[models.Model], requested_fields: Set[str]
    ) -> List[str]:
        """Determine which fields should use prefetch_related."""
        prefetch_related = []

        for field_name in requested_fields:
            try:
                field = model._meta.get_field(field_name)
                if isinstance(field, ManyToManyField):
                    prefetch_related.append(field_name)
            except FieldDoesNotExist:
                # Check for reverse relationships
                # For modern Django versions, use related_objects
                if hasattr(model._meta, "related_objects"):
                    for rel in model._meta.related_objects:
                        if rel.get_accessor_name() == field_name:
                            if isinstance(rel, (ManyToOneRel, ManyToManyRel)):
                                prefetch_related.append(field_name)
                            break
                # Fallback for Django versions that use get_fields() with related fields
                elif hasattr(model._meta, "get_fields"):
                    try:
                        for field in model._meta.get_fields():
                            if hasattr(field, "related_model") and hasattr(
                                field, "get_accessor_name"
                            ):
                                if field.get_accessor_name() == field_name:
                                    if (
                                        hasattr(field, "many_to_many")
                                        and field.many_to_many
                                    ):
                                        prefetch_related.append(field_name)
                                    elif (
                                        hasattr(field, "one_to_many")
                                        and field.one_to_many
                                    ):
                                        prefetch_related.append(field_name)
                                    break
                    except AttributeError:
                        pass
                else:
                    # Final fallback for very old Django versions
                    try:
                        for rel in model._meta.get_all_related_objects():
                            if rel.get_accessor_name() == field_name:
                                if isinstance(rel, (ManyToOneRel, ManyToManyRel)):
                                    prefetch_related.append(field_name)
                                break
                    except AttributeError:
                        pass

        return prefetch_related

    def _calculate_complexity(self, info: GraphQLResolveInfo) -> int:
        """Calculate query complexity score."""
        # Simple complexity calculation based on field count and nesting
        complexity = 0

        def count_fields(selection_set, depth=0):
            nonlocal complexity
            if not selection_set or depth > self.config.max_query_depth:
                return

            for field in selection_set.selections:
                complexity += 1 + depth  # Base cost + depth penalty
                if hasattr(field, "selection_set") and field.selection_set:
                    count_fields(field.selection_set, depth + 1)

        try:
            count_fields(info.field_nodes[0].selection_set)
        except Exception as e:
            logger.warning(f"Failed to calculate query complexity: {e}")
            complexity = 1

        return complexity

    def _calculate_depth(self, info: GraphQLResolveInfo) -> int:
        """Calculate maximum query depth."""

        def get_depth(selection_set, current_depth=0):
            if not selection_set:
                return current_depth

            max_depth = current_depth
            for field in selection_set.selections:
                if hasattr(field, "selection_set") and field.selection_set:
                    depth = get_depth(field.selection_set, current_depth + 1)
                    max_depth = max(max_depth, depth)

            return max_depth

        try:
            return get_depth(info.field_nodes[0].selection_set)
        except Exception as e:
            logger.warning(f"Failed to calculate query depth: {e}")
            return 1

    def _estimate_query_count(
        self, model: Type[models.Model], requested_fields: Set[str]
    ) -> int:
        """Estimate number of database queries without optimization."""
        query_count = 1  # Base query

        for field_name in requested_fields:
            try:
                field = model._meta.get_field(field_name)
                if isinstance(field, (ForeignKey, OneToOneField, ManyToManyField)):
                    query_count += 1  # Additional query per relationship
            except FieldDoesNotExist:
                # Reverse relationships also add queries
                # For modern Django versions, use related_objects
                if hasattr(model._meta, "related_objects"):
                    for rel in model._meta.related_objects:
                        if rel.get_accessor_name() == field_name:
                            query_count += 1
                            break
                # Fallback for Django versions that use get_fields() with related fields
                elif hasattr(model._meta, "get_fields"):
                    try:
                        for field in model._meta.get_fields():
                            if hasattr(field, "related_model") and hasattr(
                                field, "get_accessor_name"
                            ):
                                if field.get_accessor_name() == field_name:
                                    query_count += 1
                                    break
                    except AttributeError:
                        pass
                else:
                    # Final fallback for very old Django versions
                    try:
                        for rel in model._meta.get_all_related_objects():
                            if rel.get_accessor_name() == field_name:
                                query_count += 1
                                break
                    except AttributeError:
                        pass

        return query_count


class QueryOptimizer:
    """Optimizes Django querysets based on GraphQL query analysis."""

    def __init__(self, config: QueryOptimizationConfig):
        self.config = config
        self.analyzer = QueryAnalyzer(config)

    def optimize_queryset(
        self, queryset: QuerySet, info: GraphQLResolveInfo, model: Type[models.Model]
    ) -> QuerySet:
        """
        Optimize a Django queryset based on GraphQL query analysis.

        Args:
            queryset: Base Django queryset
            info: GraphQL resolve info
            model: Django model being queried

        Returns:
            Optimized queryset with select_related and prefetch_related
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
            prefetch_objects = self._build_prefetch_objects(
                model, analysis.prefetch_related_fields
            )
            queryset = queryset.prefetch_related(*prefetch_objects)
            logger.debug(
                f"Applied prefetch_related: {analysis.prefetch_related_fields}"
            )

        return queryset

    def _build_prefetch_objects(
        self, model: Type[models.Model], fields: List[str]
    ) -> List[Union[str, Prefetch]]:
        """Build Prefetch objects for complex prefetch_related optimization."""
        prefetch_objects = []

        for field_name in fields:
            try:
                field = model._meta.get_field(field_name)
                if isinstance(field, ManyToManyField):
                    # Simple prefetch for many-to-many
                    prefetch_objects.append(field_name)
                else:
                    # Create Prefetch object for more control
                    related_model = field.related_model
                    prefetch_objects.append(
                        Prefetch(field_name, queryset=related_model.objects.all())
                    )
            except FieldDoesNotExist:
                # Handle reverse relationships
                prefetch_objects.append(field_name)

        return prefetch_objects


## CacheManager removed: caching functionality is not supported in this project.


class PerformanceMonitor:
    """Monitors and tracks GraphQL query performance."""

    def __init__(self, config: QueryOptimizationConfig):
        self.config = config
        self.metrics: Dict[str, List[PerformanceMetrics]] = defaultdict(list)

    def start_monitoring(self, query_name: str) -> Dict[str, Any]:
        """Start monitoring a query execution."""
        if not self.config.enable_performance_monitoring:
            return {}

        return {
            "start_time": time.time(),
            "initial_query_count": len(connection.queries),
            "query_name": query_name,
        }

    def end_monitoring(self, context: Dict[str, Any]) -> PerformanceMetrics:
        """End monitoring and record metrics."""
        if not self.config.enable_performance_monitoring or not context:
            return PerformanceMetrics()

        end_time = time.time()
        execution_time = end_time - context["start_time"]
        query_count = len(connection.queries) - context["initial_query_count"]

        metrics = PerformanceMetrics(
            execution_time=execution_time, query_count=query_count
        )

        # Store metrics
        query_name = context["query_name"]
        self.metrics[query_name].append(metrics)

        # Log slow queries
        if (
            self.config.log_slow_queries
            and execution_time > self.config.slow_query_threshold
        ):
            logger.warning(
                f"Slow query detected: {query_name} took {execution_time:.2f}s "
                f"with {query_count} database queries"
            )

        return metrics

    def record_query_performance(
        self,
        query_name: str,
        execution_time: float,
        cache_hit: bool = False,
        error: str = None,
        query_count: int = None,
    ) -> None:
        """Record query performance metrics."""
        if not self.config.enable_performance_monitoring:
            return

        # Create performance metrics
        metrics = PerformanceMetrics(
            execution_time=execution_time,
            query_count=query_count or 0,
            cache_hits=1 if cache_hit else 0,
            cache_misses=0 if cache_hit else 1,
        )

        # Store metrics
        self.metrics[query_name].append(metrics)

        # Log slow queries
        if (
            self.config.log_slow_queries
            and execution_time > self.config.slow_query_threshold
        ):
            logger.warning(
                f"Slow query detected: {query_name} took {execution_time:.2f}s"
                + (f" (cache hit)" if cache_hit else "")
                + (f" - Error: {error}" if error else "")
            )

        # Log errors
        if error:
            logger.error(f"xQuery error in {query_name}: {error}", exc_info=True)

    def get_performance_stats(self, query_name: str = None) -> Dict[str, Any]:
        """Get performance statistics."""
        if query_name:
            query_metrics = self.metrics.get(query_name, [])
            if not query_metrics:
                return {}

            return {
                "query_name": query_name,
                "total_executions": len(query_metrics),
                "avg_execution_time": sum(m.execution_time for m in query_metrics)
                / len(query_metrics),
                "avg_query_count": sum(m.query_count for m in query_metrics)
                / len(query_metrics),
                "max_execution_time": max(m.execution_time for m in query_metrics),
                "min_execution_time": min(m.execution_time for m in query_metrics),
            }
        else:
            # Return overall stats
            all_metrics = []
            for metrics_list in self.metrics.values():
                all_metrics.extend(metrics_list)

            if not all_metrics:
                return {}

            return {
                "total_queries": len(all_metrics),
                "avg_execution_time": sum(m.execution_time for m in all_metrics)
                / len(all_metrics),
                "avg_query_count": sum(m.query_count for m in all_metrics)
                / len(all_metrics),
                "slow_queries": len(
                    [
                        m
                        for m in all_metrics
                        if m.execution_time > self.config.slow_query_threshold
                    ]
                ),
            }


# Decorators for performance optimization


def optimize_query(
    enable_caching: bool = False,
    cache_timeout: Optional[int] = None,
    user_specific_cache: bool = False,
    complexity_limit: Optional[int] = None,
):
    """
    Décorateur pour optimiser automatiquement les requêtes GraphQL.

    Args:
        enable_caching: Active le cache pour cette requête
        cache_timeout: Durée de vie du cache en secondes
        user_specific_cache: Cache spécifique à l'utilisateur
        complexity_limit: Limite de complexité pour cette requête
    """

    def decorator(resolver_func: Callable) -> Callable:
        @wraps(resolver_func)
        def wrapper(root, info: GraphQLResolveInfo, **kwargs):
            optimizer = get_optimizer()
            performance_monitor = get_performance_monitor()

            # Démarrer le monitoring
            start_time = time.time()

            try:
                # Analyser la complexité si une limite est définie
                if complexity_limit:
                    analysis = optimizer.query_analyzer.analyze_query_complexity(info)
                    if analysis.complexity_score > complexity_limit:
                        raise Exception(
                            f"Query complexity {analysis.complexity_score} exceeds limit {complexity_limit}"
                        )

                # Exécuter la requête
                result = resolver_func(root, info, **kwargs)

                # Optimize queryset if it's a QuerySet
                if isinstance(result, QuerySet) and hasattr(result, "model"):
                    result = optimizer.optimize_queryset(result, info, result.model)

                # Enregistrer les métriques de performance
                execution_time = time.time() - start_time
                performance_monitor.record_query_performance(
                    query_name=info.field_name,
                    execution_time=execution_time,
                    cache_hit=False,
                )

                return result

            except Exception as e:
                # Enregistrer l'erreur
                execution_time = time.time() - start_time
                performance_monitor.record_query_performance(
                    query_name=info.field_name,
                    execution_time=execution_time,
                    cache_hit=False,
                    error=str(e),
                )
                raise

        return wrapper

    return decorator


## cache_result decorator removed: no caching in project


# Global optimization manager instance
_optimization_config = QueryOptimizationConfig()
_query_optimizer = QueryOptimizer(_optimization_config)
_performance_monitor = PerformanceMonitor(_optimization_config)


def get_optimizer() -> QueryOptimizer:
    """Get the global query optimizer instance."""
    return _query_optimizer


## get_cache_manager removed: caching not supported


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _performance_monitor


def configure_optimization(config: QueryOptimizationConfig) -> None:
    """Configure global optimization settings."""
    global _optimization_config, _query_optimizer, _performance_monitor

    _optimization_config = config
    _query_optimizer = QueryOptimizer(config)
    _performance_monitor = PerformanceMonitor(config)

    logger.info("Performance optimization configured")

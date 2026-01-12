"""
Performance Optimization System for Django GraphQL Auto-Generation

This module provides comprehensive performance optimization features including:
- N+1 Query Prevention with automatic select_related and prefetch_related
- Caching hooks retained for compatibility (caching is disabled in this project)
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
from graphql import DocumentNode, GraphQLResolveInfo
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
    enable_schema_caching: bool = False
    enable_query_caching: bool = False
    enable_field_caching: bool = False
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
        """Extract requested fields from GraphQL query including nested fields."""
        requested_fields = set()

        def extract_fields(selection_set, parent_path=""):
            if not selection_set:
                return

            for selection in selection_set.selections:
                # Handle field selections
                if hasattr(selection, "name") and hasattr(selection.name, "value"):
                    field_name = selection.name.value
                    current_path = f"{parent_path}__{field_name}" if parent_path else field_name
                    requested_fields.add(current_path)
                    
                    # Recurse if there are sub-selections
                    if hasattr(selection, "selection_set") and selection.selection_set:
                        extract_fields(selection.selection_set, current_path)
                        
                # Handle inline fragments and fragment spreads
                elif hasattr(selection, "selection_set") and selection.selection_set:
                    # For fragments, we continue with the same parent path
                    extract_fields(selection.selection_set, parent_path)

        try:
            if info.field_nodes and info.field_nodes[0].selection_set:
                extract_fields(info.field_nodes[0].selection_set)
            return requested_fields
        except Exception as e:
            logger.warning(f"Failed to extract requested fields: {e}")
            return set()

    def _get_select_related_fields(
        self, model: Type[models.Model], requested_fields: Set[str]
    ) -> List[str]:
        """Determine which fields should use select_related, including nested ones."""
        select_related = []

        for field_path in requested_fields:
            # We only care about potential relationship paths
            current_model = model
            parts = field_path.split("__")
            valid_path = []
            
            # Check if this path corresponds to a chain of ForeignKeys/OneToOneFields
            is_valid_chain = True
            for part in parts:
                try:
                    field = current_model._meta.get_field(part)
                    if isinstance(field, (ForeignKey, OneToOneField)):
                        valid_path.append(part)
                        current_model = field.related_model
                    else:
                        # Encountered a non-relation or non-forward-relation field
                        is_valid_chain = False
                        break
                except FieldDoesNotExist:
                    is_valid_chain = False
                    break
            
            if is_valid_chain and valid_path:
                select_related.append("__".join(valid_path))

        return select_related

    def _get_prefetch_related_fields(
        self, model: Type[models.Model], requested_fields: Set[str]
    ) -> List[str]:
        """Determine which fields should use prefetch_related."""
        prefetch_related = []
        
        # We look for the *first* point in a path where a prefetch is needed.
        # Nested prefetches are handled by the fact that the prefetch query itself
        # can be optimized (though complex nested prefetch logic is hard to automate perfectly).
        # For now, we identify direct prefetch candidates on the current model.
        
        # We also want to support explicit nested prefetch paths if possible, 
        # but standard prefetch_related strings work for that.

        for field_path in requested_fields:
            parts = field_path.split("__")
            current_model = model
            current_path = []
            
            # Traverse the path to find where we hit a ManyToMany or Reverse Relation
            for i, part in enumerate(parts):
                try:
                    field = None
                    is_prefetch_needed = False
                    
                    # Check forward fields
                    try:
                        field = current_model._meta.get_field(part)
                        if isinstance(field, ManyToManyField):
                            is_prefetch_needed = True
                        elif isinstance(field, (ForeignKey, OneToOneField)):
                            # Forward relation, continue traversing but don't prefetch yet
                            current_model = field.related_model
                    except FieldDoesNotExist:
                        # Check reverse relationships
                        if hasattr(current_model._meta, "related_objects"):
                            for rel in current_model._meta.related_objects:
                                if rel.get_accessor_name() == part:
                                    is_prefetch_needed = True
                                    field = rel
                                    current_model = rel.related_model
                                    break
                    
                    current_path.append(part)
                    
                    if is_prefetch_needed:
                        # We found a point requiring prefetch.
                        # The full path up to here is the prefetch string.
                        prefetch_related.append("__".join(current_path))
                        # We stop traversing this path for the *root* queryset optimization 
                        # because subsequent segments belong to the prefetched queryset's own optimization.
                        break
                        
                except Exception:
                    break

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
    Decorator for optimizing GraphQL queries.

    Args:
        enable_caching: Ignored (caching disabled in this project)
        cache_timeout: Ignored (caching disabled in this project)
        user_specific_cache: Ignored (caching disabled in this project)
        complexity_limit: Optional complexity limit for the query
    """

    def decorator(resolver_func: Callable) -> Callable:
        @wraps(resolver_func)
        def wrapper(root, info: GraphQLResolveInfo, **kwargs):
            schema_name = getattr(info.context, "schema_name", None)
            optimizer = get_optimizer(schema_name)
            performance_monitor = get_performance_monitor(schema_name)

            # Démarrer le monitoring
            start_time = time.time()

            try:
                # Analyser la complexité si une limite est définie
                if complexity_limit:
                    from ..security.graphql_security import (
                        GraphQLSecurityAnalyzer,
                        SecurityConfig,
                    )

                    fragments = list(getattr(info, "fragments", {}).values())
                    document = DocumentNode(definitions=[info.operation] + fragments)
                    analyzer = GraphQLSecurityAnalyzer(
                        SecurityConfig(
                            max_query_complexity=int(complexity_limit),
                            enable_query_cost_analysis=True,
                        )
                    )
                    analysis = analyzer.analyze_query(
                        document,
                        info.schema,
                        getattr(info.context, "user", None),
                        info.variable_values,
                    )
                    if analysis.complexity > complexity_limit:
                        raise Exception(
                            f"Query complexity {analysis.complexity} exceeds limit {complexity_limit}"
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
_optimizer_by_schema: Dict[str, QueryOptimizer] = {}
_monitor_by_schema: Dict[str, PerformanceMonitor] = {}


def _build_optimizer_config(schema_name: Optional[str]) -> QueryOptimizationConfig:
    """Build optimizer config from performance settings."""
    from ..config_proxy import get_settings_proxy

    proxy = get_settings_proxy(schema_name)
    perf_settings = proxy.get("performance_settings", {}) or {}

    return QueryOptimizationConfig(
        enable_select_related=perf_settings.get("enable_select_related", True),
        enable_prefetch_related=perf_settings.get("enable_prefetch_related", True),
        max_prefetch_depth=perf_settings.get("max_query_depth", 3),
        auto_optimize_queries=perf_settings.get("enable_query_optimization", True),
        enable_schema_caching=False,
        enable_query_caching=False,
        enable_field_caching=False,
        cache_timeout=perf_settings.get("cache_timeout", 300),
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


## get_cache_manager removed: caching not supported


def get_performance_monitor(schema_name: Optional[str] = None) -> PerformanceMonitor:
    """Get a performance monitor instance."""
    if not schema_name:
        return _performance_monitor

    if schema_name not in _monitor_by_schema:
        config = _build_optimizer_config(schema_name)
        _monitor_by_schema[schema_name] = PerformanceMonitor(config)

    return _monitor_by_schema[schema_name]


def configure_optimization(config: QueryOptimizationConfig) -> None:
    """Configure global optimization settings."""
    global _optimization_config, _query_optimizer, _performance_monitor

    _optimization_config = config
    _query_optimizer = QueryOptimizer(config)
    _performance_monitor = PerformanceMonitor(config)
    _optimizer_by_schema.clear()
    _monitor_by_schema.clear()

    logger.info("Performance optimization configured")

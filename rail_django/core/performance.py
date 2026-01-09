"""
Performance optimization utilities for Rail Django GraphQL.

This module implements performance-related settings from LIBRARY_DEFAULTS
including query optimization and dataloader functionality. Caching has been
fully removed from this project.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, Union

from django.conf import settings as django_settings
from django.db import models

from ..conf import get_setting

logger = logging.getLogger(__name__)


@dataclass
class PerformanceSettings:
    """Settings for performance optimization."""

    enable_query_optimization: bool = True
    enable_select_related: bool = True
    enable_prefetch_related: bool = True
    enable_only_fields: bool = True
    enable_defer_fields: bool = False
    # Caching removed; related settings removed
    enable_dataloader: bool = True
    dataloader_batch_size: int = 100
    max_query_depth: int = 10
    max_query_complexity: int = 1000
    enable_query_cost_analysis: bool = False
    query_timeout: int = 30  # seconds

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "PerformanceSettings":
        """Create PerformanceSettings from schema configuration."""
        from ..defaults import LIBRARY_DEFAULTS

        defaults = LIBRARY_DEFAULTS.get("performance_settings", {})
        
        # Override with Django settings if available
        django_perf_settings = getattr(django_settings, "RAIL_DJANGO_GRAPHQL", {}).get(
            "performance_settings", {}
        )

        # Merge settings (Django settings override defaults)
        merged_settings = {**defaults, **django_perf_settings}

        # Filter to only include valid fields
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered_settings = {k: v for k, v in merged_settings.items() if k in valid_fields}

        # Auto-disable query caching in DEBUG mode to avoid stale results during development
        # No caching: no DEBUG-based cache overrides needed

        return cls(**filtered_settings)


class QueryOptimizer:
    """Query optimization utilities."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = PerformanceSettings.from_schema(schema_name)

    def optimize_queryset(self, queryset: models.QuerySet, info: Any = None) -> models.QuerySet:
        """
        Optimize a Django QuerySet for GraphQL execution.

        Args:
            queryset: The Django QuerySet to optimize
            info: GraphQL resolve info (optional)

        Returns:
            Optimized QuerySet
        """
        if not self.settings.enable_query_optimization:
            return queryset

        optimized_qs = queryset

        # Apply select_related optimization
        if self.settings.enable_select_related:
            select_related_fields = self._get_select_related_fields(queryset.model, info)
            if select_related_fields:
                optimized_qs = optimized_qs.select_related(*select_related_fields)

        # Apply prefetch_related optimization
        if self.settings.enable_prefetch_related:
            prefetch_fields = self._get_prefetch_related_fields(queryset.model, info)
            if prefetch_fields:
                optimized_qs = optimized_qs.prefetch_related(*prefetch_fields)

        # Apply only() optimization
        if self.settings.enable_only_fields:
            only_fields = self._get_only_fields(queryset.model, info)
            if only_fields:
                optimized_qs = optimized_qs.only(*only_fields)

        # Apply defer() optimization
        if self.settings.enable_defer_fields:
            defer_fields = self._get_defer_fields(queryset.model, info)
            if defer_fields:
                optimized_qs = optimized_qs.defer(*defer_fields)

        return optimized_qs

    def _get_select_related_fields(self, model: Type[models.Model], info: Any = None) -> List[str]:
        """Get fields that should be select_related."""
        select_related_fields = []

        # Analyze model relationships
        for field in model._meta.get_fields():
            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                select_related_fields.append(field.name)

        return select_related_fields

    def _get_prefetch_related_fields(self, model: Type[models.Model], info: Any = None) -> List[str]:
        """Get fields that should be prefetch_related."""
        prefetch_fields = []

        # Analyze reverse relationships
        for field in model._meta.get_fields():
            if isinstance(field, (models.ManyToManyField, models.ForeignKey)) and field.many_to_many:
                prefetch_fields.append(field.name)
            elif hasattr(field, 'related_name') and field.related_name:
                prefetch_fields.append(field.related_name)

        return prefetch_fields

    def _get_only_fields(self, model: Type[models.Model], info: Any = None) -> List[str]:
        """Get fields that should be included in only()."""
        # For now, return empty list - could be enhanced with GraphQL field analysis
        return []

    def _get_defer_fields(self, model: Type[models.Model], info: Any = None) -> List[str]:
        """Get fields that should be deferred."""
        defer_fields = []

        # Defer large text fields by default
        for field in model._meta.get_fields():
            if isinstance(field, models.TextField):
                defer_fields.append(field.name)

        return defer_fields


## QueryCache removed: caching is not supported.


class QueryComplexityAnalyzer:
    """Analyze and limit GraphQL query complexity."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = PerformanceSettings.from_schema(schema_name)

    def analyze_query_depth(self, query: str) -> int:
        """Analyze the depth of a GraphQL query."""
        # Simple depth analysis - could be enhanced with proper AST parsing
        depth = 0
        current_depth = 0

        for char in query:
            if char == '{':
                current_depth += 1
                depth = max(depth, current_depth)
            elif char == '}':
                current_depth -= 1

        return depth

    def analyze_query_complexity(self, query: str) -> int:
        """Analyze the complexity of a GraphQL query."""
        # Simple complexity analysis - count fields and nested structures
        complexity = 0

        # Count field selections (simplified)
        lines = query.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and '{' not in stripped and '}' not in stripped:
                complexity += 1

        return complexity

    def validate_query_limits(self, query: str) -> List[str]:
        """Validate query against performance limits."""
        errors = []

        # Check query depth
        depth = self.analyze_query_depth(query)
        if depth > self.settings.max_query_depth:
            errors.append(
                f"Query depth {depth} exceeds maximum allowed depth {self.settings.max_query_depth}")

        # Check query complexity
        if self.settings.enable_query_cost_analysis:
            complexity = self.analyze_query_complexity(query)
            if complexity > self.settings.max_query_complexity:
                errors.append(
                    f"Query complexity {complexity} exceeds maximum allowed complexity {self.settings.max_query_complexity}")

        return errors


# Global instances
query_optimizer = QueryOptimizer()
complexity_analyzer = QueryComplexityAnalyzer()


def get_query_optimizer(schema_name: Optional[str] = None) -> QueryOptimizer:
    """Get query optimizer instance for schema."""
    return QueryOptimizer(schema_name)


## get_query_cache removed


def get_complexity_analyzer(schema_name: Optional[str] = None) -> QueryComplexityAnalyzer:
    """Get complexity analyzer instance for schema."""
    return QueryComplexityAnalyzer(schema_name)

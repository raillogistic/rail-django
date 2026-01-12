"""
Performance optimization utilities for Rail Django GraphQL.

This module implements performance-related settings from LIBRARY_DEFAULTS
including query optimization and dataloader functionality. Caching has been
fully removed from this project.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Type

from django.db import models
from graphql import Visitor, parse, visit
from graphql.language.ast import FieldNode

from .runtime_settings import RuntimeSettings

logger = logging.getLogger(__name__)


PerformanceSettings = RuntimeSettings


class QueryOptimizer:
    """Query optimization utilities."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = RuntimeSettings.from_schema(schema_name)
        self._selection_optimizer = self._build_selection_optimizer()

    def _build_selection_optimizer(self):
        """Build a selection-set driven optimizer when available."""
        try:
            from ..extensions.optimization import (
                QueryOptimizationConfig,
                QueryOptimizer as SelectionOptimizer,
            )
        except Exception:
            return None

        config = QueryOptimizationConfig(
            enable_select_related=self.settings.enable_select_related,
            enable_prefetch_related=self.settings.enable_prefetch_related,
            max_prefetch_depth=self.settings.max_query_depth,
            auto_optimize_queries=self.settings.enable_query_optimization,
            enable_schema_caching=False,
            enable_query_caching=False,
            enable_field_caching=False,
            enable_complexity_analysis=self.settings.enable_query_cost_analysis,
            max_query_complexity=self.settings.max_query_complexity,
            max_query_depth=self.settings.max_query_depth,
            query_timeout=self.settings.query_timeout,
            enable_performance_monitoring=False,
            log_slow_queries=False,
        )
        return SelectionOptimizer(config)

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

        if info is not None and self._selection_optimizer is not None:
            try:
                return self._selection_optimizer.optimize_queryset(
                    queryset, info, queryset.model
                )
            except Exception:
                # Fall back to default queryset without blanket prefetching
                return queryset

        optimized_qs = queryset

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

    def __init__(
        self,
        schema_name: Optional[str] = None,
        complexity_weights: Optional[Dict[str, int]] = None,
    ):
        self.schema_name = schema_name
        self.settings = PerformanceSettings.from_schema(schema_name)
        self.complexity_weights = complexity_weights or {
            "field": 1,
            "list_field": 2,
            "connection": 3,
            "nested_object": 2,
            "fragment": 1,
        }

    def analyze_query(self, query: str) -> Tuple[int, int]:
        """Analyze query depth and complexity, preferring AST parsing."""
        ast_result = self._analyze_with_ast(query)
        if ast_result is not None:
            return ast_result
        return self.analyze_query_depth(query), self.analyze_query_complexity(query)

    def _analyze_with_ast(self, query: str) -> Optional[Tuple[int, int]]:
        try:
            document = parse(query)
        except Exception:
            return None
        analyzer = _ComplexityVisitor(self.complexity_weights)
        visit(document, analyzer)
        return analyzer.max_depth, analyzer.total_complexity

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

    def validate_query_limits(
        self,
        query: str,
        *,
        schema: Optional[Any] = None,
        document: Optional[Any] = None,
    ) -> List[str]:
        """Validate query against performance limits."""
        errors: List[str] = []
        enable_depth = bool(self.settings.enable_query_depth_limiting)
        enable_complexity = bool(self.settings.enable_query_cost_analysis)

        try:
            from ..security.graphql_security import (
                GraphQLSecurityAnalyzer,
                SecurityConfig,
            )

            doc = document or parse(query)
            analyzer = GraphQLSecurityAnalyzer(
                SecurityConfig(
                    max_query_complexity=self.settings.max_query_complexity,
                    max_query_depth=self.settings.max_query_depth,
                    max_field_count=1000000,
                    max_operation_count=1000000,
                    enable_introspection=True,
                    enable_query_cost_analysis=enable_complexity,
                    enable_depth_limiting=enable_depth,
                )
            )
            if schema is not None and (enable_depth or enable_complexity):
                result = analyzer.analyze_query(doc, schema, user=None)
                errors.extend(result.blocked_reasons)
                return errors
        except Exception:
            # Fall back to the simple string-based analysis
            pass

        depth, complexity = self.analyze_query(query)
        if enable_depth and depth > self.settings.max_query_depth:
            errors.append(
                f"Query depth {depth} exceeds maximum allowed depth {self.settings.max_query_depth}"
            )

        if enable_complexity:
            if complexity > self.settings.max_query_complexity:
                errors.append(
                    f"Query complexity {complexity} exceeds maximum allowed complexity "
                    f"{self.settings.max_query_complexity}"
                )

        return errors


class _ComplexityVisitor(Visitor):
    def __init__(self, complexity_weights: Dict[str, int]):
        super().__init__()
        self.complexity_weights = complexity_weights
        self.current_depth = 0
        self.max_depth = 0
        self.total_complexity = 0

    def enter_field(self, node: FieldNode, *_):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)

        field_complexity = self.complexity_weights.get("field", 1)
        if self._is_list_field(node):
            field_complexity = self.complexity_weights.get("list_field", 2)
        elif self._is_connection_field(node):
            field_complexity = self.complexity_weights.get("connection", 3)

        if node.selection_set:
            field_complexity = max(
                field_complexity, self.complexity_weights.get("nested_object", 2)
            )

        self.total_complexity += field_complexity * self.current_depth

    def leave_field(self, node: FieldNode, *_):
        self.current_depth -= 1

    @staticmethod
    def _is_list_field(node: FieldNode) -> bool:
        field_name = node.name.value
        return field_name.startswith("all") or field_name.endswith("s")

    @staticmethod
    def _is_connection_field(node: FieldNode) -> bool:
        return any(
            arg.name.value in ["first", "last", "after", "before"]
            for arg in (node.arguments or [])
        )


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

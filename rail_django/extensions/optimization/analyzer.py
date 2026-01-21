"""
Query analyzer for extracting optimization strategies.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from graphql import GraphQLResolveInfo
from graphql.language.ast import FieldNode, FragmentSpreadNode, InlineFragmentNode

from .config import QueryOptimizationConfig

logger = logging.getLogger(__name__)


@dataclass
class QueryAnalysisResult:
    """Result of query analysis for optimization."""

    requested_fields: set[str] = field(default_factory=set)
    select_related_fields: list[str] = field(default_factory=list)
    prefetch_related_fields: list[str] = field(default_factory=list)
    complexity_score: int = 0
    depth: int = 0
    estimated_queries: int = 1


class QueryAnalyzer:
    """Analyzes GraphQL queries to extract optimization information."""

    def __init__(self, config: QueryOptimizationConfig):
        self.config = config

    def analyze_query(
        self, info: GraphQLResolveInfo, model: type[models.Model]
    ) -> QueryAnalysisResult:
        """
        Analyze a GraphQL query to determine optimization strategies.
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

    def _extract_requested_fields(self, info: GraphQLResolveInfo) -> set[str]:
        """Extract requested fields from GraphQL query including nested fields."""
        requested_fields: set[str] = set()
        fragments = getattr(info, "fragments", {}) or {}

        def collect(selection_set, parent_path=""):
            if not selection_set or not getattr(selection_set, "selections", None):
                return

            for selection in selection_set.selections:
                if isinstance(selection, FieldNode):
                    field_name = selection.name.value
                    if field_name.startswith("__"):
                        continue
                    current_path = (
                        f"{parent_path}__{field_name}" if parent_path else field_name
                    )
                    requested_fields.add(current_path)
                    if selection.selection_set:
                        collect(selection.selection_set, current_path)
                elif isinstance(selection, InlineFragmentNode):
                    collect(selection.selection_set, parent_path)
                elif isinstance(selection, FragmentSpreadNode):
                    fragment = fragments.get(selection.name.value)
                    if fragment:
                        collect(fragment.selection_set, parent_path)

        try:
            for node in info.field_nodes or []:
                if node.selection_set:
                    collect(node.selection_set)
            return requested_fields
        except Exception as e:
            logger.warning(f"Failed to extract requested fields: {e}")
            return set()

    def _walk_selection_set(
        self,
        selection_set,
        fragments: dict[str, Any],
        depth: int,
        on_field: Callable[[FieldNode, int], None],
    ) -> None:
        if not selection_set or not getattr(selection_set, "selections", None):
            return

        for selection in selection_set.selections:
            if isinstance(selection, FieldNode):
                on_field(selection, depth)
                if selection.selection_set:
                    self._walk_selection_set(
                        selection.selection_set, fragments, depth + 1, on_field
                    )
            elif isinstance(selection, InlineFragmentNode):
                self._walk_selection_set(
                    selection.selection_set, fragments, depth, on_field
                )
            elif isinstance(selection, FragmentSpreadNode):
                fragment = fragments.get(selection.name.value)
                if fragment:
                    self._walk_selection_set(fragment.selection_set, fragments, depth, on_field)

    def _get_select_related_fields(
        self, model: type[models.Model], requested_fields: set[str]
    ) -> list[str]:
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
                        is_valid_chain = False
                        break
                except FieldDoesNotExist:
                    is_valid_chain = False
                    break
            
            if is_valid_chain and valid_path:
                select_related.append("__".join(valid_path))

        return select_related

    def _get_prefetch_related_fields(
        self, model: type[models.Model], requested_fields: set[str]
    ) -> list[str]:
        """Determine which fields should use prefetch_related."""
        prefetch_related = []

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
                        prefetch_related.append("__".join(current_path))
                        break
                        
                except Exception:
                    break

        return prefetch_related

    def _calculate_complexity(self, info: GraphQLResolveInfo) -> int:
        """Calculate query complexity score."""
        complexity = 0

        def count_field(field: FieldNode, depth: int) -> None:
            nonlocal complexity
            if depth > self.config.max_query_depth:
                return
            complexity += 1 + depth

        try:
            fragments = getattr(info, "fragments", {}) or {}
            for node in info.field_nodes or []:
                if node.selection_set:
                    self._walk_selection_set(node.selection_set, fragments, 1, count_field)
        except Exception as e:
            logger.warning(f"Failed to calculate query complexity: {e}")
            complexity = 1

        return complexity

    def _calculate_depth(self, info: GraphQLResolveInfo) -> int:
        """Calculate maximum query depth."""
        max_depth = 0

        def update_depth(field: FieldNode, depth: int) -> None:
            nonlocal max_depth
            max_depth = max(max_depth, depth)

        try:
            fragments = getattr(info, "fragments", {}) or {}
            for node in info.field_nodes or []:
                if node.selection_set:
                    self._walk_selection_set(node.selection_set, fragments, 1, update_depth)
            return max_depth or 1
        except Exception as e:
            logger.warning(f"Failed to calculate query depth: {e}")
            return 1

    def _estimate_query_count(
        self, model: type[models.Model], requested_fields: set[str]
    ) -> int:
        """Estimate number of database queries without optimization."""
        query_count = 1  # Base query

        for field_name in requested_fields:
            root_field = field_name.split("__", 1)[0]
            try:
                field = model._meta.get_field(root_field)
                if isinstance(field, (ForeignKey, OneToOneField, ManyToManyField)):
                    query_count += 1
            except FieldDoesNotExist:
                if hasattr(model._meta, "related_objects"):
                    for rel in model._meta.related_objects:
                        if rel.get_accessor_name() == field_name:
                            query_count += 1
                            break
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

        return query_count

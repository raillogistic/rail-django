"""
Filter Analysis Module for Rail Django.

Provides classes for analyzing filter performance, generating filter metadata,
and representing filter operations for UI generation and introspection.

Classes:
    - PerformanceAnalyzer: Analyzes filter queries for performance and optimization
    - FilterOperation: Represents a single filter operation for a field
    - GroupedFieldFilter: Represents a grouped filter with multiple operations
    - FilterMetadataGenerator: Generates filter metadata for UI builders
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from django.core.exceptions import FieldDoesNotExist
from django.db import models

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """
    Analyzes filter queries for performance and suggests optimizations.

    Provides recommendations for select_related and prefetch_related
    based on the filters being applied.

    Example:
        analyzer = PerformanceAnalyzer()
        analysis = analyzer.analyze_query_performance(MyModel, where_input)
        print(analysis["recommendations"])
    """

    def analyze_query_performance(
        self,
        model: Type[models.Model],
        where_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyze the performance implications of applied filters.

        Args:
            model: Django model being filtered
            where_input: Where input dictionary

        Returns:
            Dictionary containing performance analysis and suggestions
        """
        analysis = {
            "model": model.__name__,
            "total_filters": 0,
            "nested_filters": 0,
            "max_depth": 0,
            "select_related_suggestions": set(),
            "prefetch_related_suggestions": set(),
            "potential_n_plus_one_risks": [],
            "performance_score": "good",
            "recommendations": [],
        }

        self._analyze_where_input(model, where_input, analysis, depth=0)

        # Calculate performance score
        if analysis["max_depth"] > 3 or analysis["nested_filters"] > 10:
            analysis["performance_score"] = "poor"
        elif analysis["max_depth"] > 2 or analysis["nested_filters"] > 5:
            analysis["performance_score"] = "moderate"

        # Generate recommendations
        if analysis["select_related_suggestions"]:
            select_list = sorted(analysis["select_related_suggestions"])
            analysis["recommendations"].append(
                f"Use select_related({', '.join(repr(s) for s in select_list)}) "
                f"to optimize forward relationship queries"
            )

        if analysis["prefetch_related_suggestions"]:
            prefetch_list = sorted(analysis["prefetch_related_suggestions"])
            analysis["recommendations"].append(
                f"Use prefetch_related({', '.join(repr(p) for p in prefetch_list)}) "
                f"to optimize reverse relationship queries"
            )

        if analysis["potential_n_plus_one_risks"]:
            analysis["recommendations"].append(
                f"Potential N+1 query risks: {', '.join(analysis['potential_n_plus_one_risks'])}"
            )

        # Convert sets to lists for JSON serialization
        analysis["select_related_suggestions"] = list(
            analysis["select_related_suggestions"]
        )
        analysis["prefetch_related_suggestions"] = list(
            analysis["prefetch_related_suggestions"]
        )

        return analysis

    def _analyze_where_input(
        self,
        model: Type[models.Model],
        where_input: Dict[str, Any],
        analysis: Dict[str, Any],
        depth: int,
        prefix: str = "",
    ) -> None:
        """
        Recursively analyze where input for performance implications.

        Args:
            model: Django model being filtered
            where_input: Where input dictionary to analyze
            analysis: Analysis dictionary to update
            depth: Current nesting depth
            prefix: Field path prefix for nested relations
        """
        for key, value in where_input.items():
            if value is None:
                continue

            analysis["total_filters"] += 1

            if key in ("AND", "OR"):
                if isinstance(value, list):
                    for item in value:
                        self._analyze_where_input(model, item, analysis, depth, prefix)
            elif key == "NOT":
                if isinstance(value, dict):
                    self._analyze_where_input(model, value, analysis, depth, prefix)
            elif key.endswith("_rel"):
                # Nested relation filter
                base_field = key[:-4]
                analysis["nested_filters"] += 1
                analysis["max_depth"] = max(analysis["max_depth"], depth + 1)

                # Add to select_related suggestions
                field_path = f"{prefix}{base_field}" if prefix else base_field
                analysis["select_related_suggestions"].add(field_path)

                if isinstance(value, dict):
                    self._analyze_where_input(
                        model, value, analysis, depth + 1, f"{field_path}__"
                    )
            elif key.endswith(("_some", "_every", "_none")):
                # Reverse relation filter
                base_field = key.rsplit("_", 1)[0]
                analysis["nested_filters"] += 1
                analysis["max_depth"] = max(analysis["max_depth"], depth + 1)

                field_path = f"{prefix}{base_field}" if prefix else base_field
                analysis["prefetch_related_suggestions"].add(field_path)
                analysis["potential_n_plus_one_risks"].append(field_path)
                if isinstance(value, dict):
                    self._analyze_where_input(
                        model, value, analysis, depth + 1, f"{field_path}__"
                    )

    def get_optimized_queryset(
        self,
        model: Type[models.Model],
        where_input: Dict[str, Any],
        base_queryset: Optional[models.QuerySet] = None,
    ) -> models.QuerySet:
        """
        Get an optimized queryset based on filters being applied.

        Args:
            model: Django model
            where_input: Where input dictionary
            base_queryset: Optional base queryset

        Returns:
            Optimized queryset with select_related/prefetch_related
        """
        if base_queryset is None:
            queryset = model.objects.all()
        else:
            queryset = base_queryset

        analysis = self.analyze_query_performance(model, where_input)

        if analysis["select_related_suggestions"]:
            try:
                queryset = queryset.select_related(
                    *analysis["select_related_suggestions"]
                )
            except (FieldDoesNotExist, TypeError, ValueError) as e:
                logger.debug(f"Could not apply select_related: {e}")

        if analysis["prefetch_related_suggestions"]:
            try:
                queryset = queryset.prefetch_related(
                    *analysis["prefetch_related_suggestions"]
                )
            except (FieldDoesNotExist, TypeError, ValueError) as e:
                logger.debug(f"Could not apply prefetch_related: {e}")

        return queryset


class FilterOperation:
    """
    Represents a single filter operation for a field.

    Attributes:
        name: Operation name (e.g., 'eq', 'contains', 'gt')
        filter_type: GraphQL type for the filter value
        lookup_expr: Django ORM lookup expression
        description: Human-readable description
        is_array: Whether the operation accepts array values
    """

    def __init__(
        self,
        name: str,
        filter_type: str,
        lookup_expr: str = None,
        description: str = None,
        is_array: bool = False,
    ):
        """
        Initialize a filter operation.

        Args:
            name: Operation name
            filter_type: GraphQL type for the filter value
            lookup_expr: Django ORM lookup expression (defaults to 'exact')
            description: Human-readable description
            is_array: Whether the operation accepts array values
        """
        self.name = name
        self.filter_type = filter_type
        self.lookup_expr = lookup_expr or "exact"
        self.description = description
        self.is_array = is_array

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the operation to a dictionary.

        Returns:
            Dictionary representation of the operation
        """
        return {
            "name": self.name,
            "filter_type": self.filter_type,
            "lookup_expr": self.lookup_expr,
            "description": self.description,
            "is_array": self.is_array,
        }


class GroupedFieldFilter:
    """
    Represents a grouped filter for a single field with multiple operations.

    Attributes:
        field_name: Name of the Django model field
        field_type: Django field class name
        operations: List of available filter operations
    """

    def __init__(
        self, field_name: str, field_type: str, operations: List[FilterOperation]
    ):
        """
        Initialize a grouped field filter.

        Args:
            field_name: Name of the Django model field
            field_type: Django field class name
            operations: List of available filter operations
        """
        self.field_name = field_name
        self.field_type = field_type
        self.operations = operations

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the grouped filter to a dictionary.

        Returns:
            Dictionary representation of the grouped filter
        """
        return {
            "field_name": self.field_name,
            "field_type": self.field_type,
            "operations": [op.to_dict() for op in self.operations],
        }


class FilterMetadataGenerator:
    """
    Generates filter metadata for UI builders and introspection.

    Provides structured information about available filters for each model,
    useful for dynamically building filter UIs.

    Example:
        generator = FilterMetadataGenerator(schema_name="default")
        filters = generator.get_grouped_filters(MyModel)
        for f in filters:
            print(f"{f.field_name}: {[op.name for op in f.operations]}")
    """

    def __init__(self, schema_name: str = "default"):
        """
        Initialize the metadata generator.

        Args:
            schema_name: Name of the schema for caching
        """
        self.schema_name = schema_name
        self._cache: Dict[str, List[GroupedFieldFilter]] = {}

    def get_grouped_filters(
        self, model: Type[models.Model]
    ) -> List[GroupedFieldFilter]:
        """
        Get grouped filters for a model.

        Args:
            model: Django model

        Returns:
            List of GroupedFieldFilter objects
        """
        cache_key = f"{self.schema_name}_{model.__name__}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        grouped_filters = []

        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue
            if field.name in ("polymorphic_ctype",) or "_ptr" in field.name:
                continue

            operations = self._generate_field_operations(field)
            if operations:
                grouped_filter = GroupedFieldFilter(
                    field_name=field.name,
                    field_type=field.__class__.__name__,
                    operations=operations,
                )
                grouped_filters.append(grouped_filter)

        self._cache[cache_key] = grouped_filters
        return grouped_filters

    def _generate_field_operations(self, field: models.Field) -> List[FilterOperation]:
        """
        Generate filter operations for a field type.

        Args:
            field: Django model field

        Returns:
            List of FilterOperation objects
        """
        operations = []
        field_name = field.name

        if isinstance(field, models.CharField) and getattr(field, "choices", None):
            operations.extend(self._get_choice_operations(field_name))
        elif isinstance(field, (models.CharField, models.TextField)):
            operations.extend(self._get_text_operations(field_name))
        elif isinstance(
            field, (models.IntegerField, models.FloatField, models.DecimalField)
        ):
            operations.extend(self._get_numeric_operations(field_name))
        elif isinstance(field, (models.DateField, models.DateTimeField)):
            operations.extend(self._get_date_operations(field_name))
        elif isinstance(field, models.BooleanField):
            operations.extend(self._get_boolean_operations(field_name))
        elif isinstance(field, models.ForeignKey):
            operations.extend(self._get_fk_operations(field_name))
        elif isinstance(field, models.ManyToManyField):
            operations.extend(self._get_m2m_operations(field_name))

        return operations

    def _get_text_operations(self, field_name: str) -> List[FilterOperation]:
        """Get filter operations for text fields."""
        return [
            FilterOperation("eq", "String", "exact", f"Exact match for {field_name}"),
            FilterOperation("neq", "String", "neq", f"Not equal to {field_name}"),
            FilterOperation(
                "contains", "String", "contains", f"Contains in {field_name}"
            ),
            FilterOperation(
                "icontains", "String", "icontains", f"Contains (case-insensitive)"
            ),
            FilterOperation("starts_with", "String", "startswith", f"Starts with"),
            FilterOperation("ends_with", "String", "endswith", f"Ends with"),
            FilterOperation("in", "StringList", "in", f"In list", is_array=True),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
            FilterOperation("regex", "String", "regex", f"Regex match"),
        ]

    def _get_numeric_operations(self, field_name: str) -> List[FilterOperation]:
        """Get filter operations for numeric fields."""
        return [
            FilterOperation("eq", "Number", "exact", f"Equal to"),
            FilterOperation("neq", "Number", "neq", f"Not equal to"),
            FilterOperation("gt", "Number", "gt", f"Greater than"),
            FilterOperation("gte", "Number", "gte", f"Greater than or equal"),
            FilterOperation("lt", "Number", "lt", f"Less than"),
            FilterOperation("lte", "Number", "lte", f"Less than or equal"),
            FilterOperation("in", "NumberList", "in", f"In list", is_array=True),
            FilterOperation("between", "NumberRange", "range", f"Between [min, max]"),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_date_operations(self, field_name: str) -> List[FilterOperation]:
        """Get filter operations for date fields."""
        return [
            FilterOperation("eq", "Date", "exact", f"Exact date"),
            FilterOperation("gt", "Date", "gt", f"After date"),
            FilterOperation("gte", "Date", "gte", f"On or after"),
            FilterOperation("lt", "Date", "lt", f"Before date"),
            FilterOperation("lte", "Date", "lte", f"On or before"),
            FilterOperation("between", "DateRange", "range", f"Date range"),
            FilterOperation("year", "Int", "year", f"Filter by year"),
            FilterOperation("month", "Int", "month", f"Filter by month"),
            FilterOperation("today", "Boolean", "today", f"Is today"),
            FilterOperation("this_week", "Boolean", "this_week", f"This week"),
            FilterOperation("this_month", "Boolean", "this_month", f"This month"),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_boolean_operations(self, field_name: str) -> List[FilterOperation]:
        """Get filter operations for boolean fields."""
        return [
            FilterOperation("eq", "Boolean", "exact", f"Equal to"),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_choice_operations(self, field_name: str) -> List[FilterOperation]:
        """Get filter operations for choice fields."""
        return [
            FilterOperation("eq", "String", "exact", f"Exact choice"),
            FilterOperation("in", "StringList", "in", f"In choices", is_array=True),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_fk_operations(self, field_name: str) -> List[FilterOperation]:
        """Get filter operations for foreign key fields."""
        return [
            FilterOperation("eq", "ID", "exact", f"Exact ID"),
            FilterOperation("in", "IDList", "in", f"In IDs", is_array=True),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_m2m_operations(self, field_name: str) -> List[FilterOperation]:
        """Get filter operations for many-to-many fields."""
        return [
            FilterOperation("eq", "ID", "exact", f"Has ID"),
            FilterOperation("in", "IDList", "in", f"Has any of IDs", is_array=True),
            FilterOperation("is_null", "Boolean", "isnull", f"Has none"),
            FilterOperation("count_eq", "Int", "count", f"Count equals"),
            FilterOperation("count_gt", "Int", "count_gt", f"Count greater than"),
            FilterOperation("count_lt", "Int", "count_lt", f"Count less than"),
        ]


__all__ = [
    "PerformanceAnalyzer",
    "FilterOperation",
    "GroupedFieldFilter",
    "FilterMetadataGenerator",
]

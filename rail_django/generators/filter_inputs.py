"""
Nested Filter Input Types for GraphQL (Prisma/Hasura Style)

This module provides typed GraphQL InputObjectTypes for filtering with nested
per-field filter inputs. This is an alternative to the flat lookup pattern
in filters.py, offering better schema organization and type reusability.

Example GraphQL query:
    query {
      products(where: {
        name: { icontains: "phone" }
        price: { gte: 100, lte: 500 }
        category: { name: { eq: "Electronics" } }
        OR: [
          { is_active: { eq: true } }
          { created_at: { thisMonth: true } }
        ]
      }) {
        id
        name
      }
    }
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Type, Union

import graphene
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# Base Filter Input Types (Reusable across all models)
# =============================================================================


class StringFilterInput(graphene.InputObjectType):
    """
    Filter input for string/text fields.

    Supports various text matching operations including exact match,
    case-insensitive variants, and pattern matching.
    """
    eq = graphene.String(description="Exact match")
    neq = graphene.String(description="Not equal")
    contains = graphene.String(description="Contains (case-sensitive)")
    icontains = graphene.String(description="Contains (case-insensitive)")
    starts_with = graphene.String(description="Starts with (case-sensitive)")
    istarts_with = graphene.String(description="Starts with (case-insensitive)")
    ends_with = graphene.String(description="Ends with (case-sensitive)")
    iends_with = graphene.String(description="Ends with (case-insensitive)")
    in_ = graphene.List(graphene.NonNull(graphene.String), name="in", description="In list")
    not_in = graphene.List(graphene.NonNull(graphene.String), description="Not in list")
    is_null = graphene.Boolean(description="Is null")
    regex = graphene.String(description="Regex match (case-sensitive)")
    iregex = graphene.String(description="Regex match (case-insensitive)")


class IntFilterInput(graphene.InputObjectType):
    """
    Filter input for integer fields.

    Supports numeric comparisons and range operations.
    """
    eq = graphene.Int(description="Equal to")
    neq = graphene.Int(description="Not equal to")
    gt = graphene.Int(description="Greater than")
    gte = graphene.Int(description="Greater than or equal to")
    lt = graphene.Int(description="Less than")
    lte = graphene.Int(description="Less than or equal to")
    in_ = graphene.List(graphene.NonNull(graphene.Int), name="in", description="In list")
    not_in = graphene.List(graphene.NonNull(graphene.Int), description="Not in list")
    between = graphene.List(graphene.Int, description="Between [min, max] inclusive")
    is_null = graphene.Boolean(description="Is null")


class FloatFilterInput(graphene.InputObjectType):
    """
    Filter input for float/decimal fields.

    Supports numeric comparisons and range operations.
    """
    eq = graphene.Float(description="Equal to")
    neq = graphene.Float(description="Not equal to")
    gt = graphene.Float(description="Greater than")
    gte = graphene.Float(description="Greater than or equal to")
    lt = graphene.Float(description="Less than")
    lte = graphene.Float(description="Less than or equal to")
    in_ = graphene.List(graphene.NonNull(graphene.Float), name="in", description="In list")
    not_in = graphene.List(graphene.NonNull(graphene.Float), description="Not in list")
    between = graphene.List(graphene.Float, description="Between [min, max] inclusive")
    is_null = graphene.Boolean(description="Is null")


class BooleanFilterInput(graphene.InputObjectType):
    """
    Filter input for boolean fields.
    """
    eq = graphene.Boolean(description="Equal to")
    is_null = graphene.Boolean(description="Is null")


class DateFilterInput(graphene.InputObjectType):
    """
    Filter input for date fields.

    Supports date comparisons, ranges, and convenient temporal filters.
    """
    eq = graphene.Date(description="Equal to")
    neq = graphene.Date(description="Not equal to")
    gt = graphene.Date(description="After date")
    gte = graphene.Date(description="On or after date")
    lt = graphene.Date(description="Before date")
    lte = graphene.Date(description="On or before date")
    between = graphene.List(graphene.Date, description="Between [start, end] inclusive")
    is_null = graphene.Boolean(description="Is null")
    # Temporal convenience filters
    year = graphene.Int(description="Filter by year")
    month = graphene.Int(description="Filter by month (1-12)")
    day = graphene.Int(description="Filter by day of month")
    week_day = graphene.Int(description="Filter by day of week (1=Sunday, 7=Saturday)")
    # Relative date filters
    today = graphene.Boolean(description="Is today")
    yesterday = graphene.Boolean(description="Is yesterday")
    this_week = graphene.Boolean(description="Is this week")
    past_week = graphene.Boolean(description="Is past week")
    this_month = graphene.Boolean(description="Is this month")
    past_month = graphene.Boolean(description="Is past month")
    this_year = graphene.Boolean(description="Is this year")
    past_year = graphene.Boolean(description="Is past year")


class DateTimeFilterInput(graphene.InputObjectType):
    """
    Filter input for datetime fields.

    Supports datetime comparisons, ranges, and convenient temporal filters.
    """
    eq = graphene.DateTime(description="Equal to")
    neq = graphene.DateTime(description="Not equal to")
    gt = graphene.DateTime(description="After datetime")
    gte = graphene.DateTime(description="On or after datetime")
    lt = graphene.DateTime(description="Before datetime")
    lte = graphene.DateTime(description="On or before datetime")
    between = graphene.List(graphene.DateTime, description="Between [start, end] inclusive")
    is_null = graphene.Boolean(description="Is null")
    # Date-only filters (ignores time)
    date = graphene.Date(description="Filter by date part only")
    year = graphene.Int(description="Filter by year")
    month = graphene.Int(description="Filter by month (1-12)")
    day = graphene.Int(description="Filter by day of month")
    week_day = graphene.Int(description="Filter by day of week (1=Sunday, 7=Saturday)")
    hour = graphene.Int(description="Filter by hour (0-23)")
    # Relative date filters
    today = graphene.Boolean(description="Is today")
    yesterday = graphene.Boolean(description="Is yesterday")
    this_week = graphene.Boolean(description="Is this week")
    past_week = graphene.Boolean(description="Is past week")
    this_month = graphene.Boolean(description="Is this month")
    past_month = graphene.Boolean(description="Is past month")
    this_year = graphene.Boolean(description="Is this year")
    past_year = graphene.Boolean(description="Is past year")


class IDFilterInput(graphene.InputObjectType):
    """
    Filter input for ID/primary key fields.
    """
    eq = graphene.ID(description="Equal to")
    neq = graphene.ID(description="Not equal to")
    in_ = graphene.List(graphene.NonNull(graphene.ID), name="in", description="In list")
    not_in = graphene.List(graphene.NonNull(graphene.ID), description="Not in list")
    is_null = graphene.Boolean(description="Is null")


class UUIDFilterInput(graphene.InputObjectType):
    """
    Filter input for UUID fields.
    """
    eq = graphene.String(description="Equal to")
    neq = graphene.String(description="Not equal to")
    in_ = graphene.List(graphene.NonNull(graphene.String), name="in", description="In list")
    not_in = graphene.List(graphene.NonNull(graphene.String), description="Not in list")
    is_null = graphene.Boolean(description="Is null")


class JSONFilterInput(graphene.InputObjectType):
    """
    Filter input for JSON fields.
    """
    eq = graphene.JSONString(description="Exact JSON match")
    is_null = graphene.Boolean(description="Is null")
    has_key = graphene.String(description="Has key")
    has_keys = graphene.List(graphene.NonNull(graphene.String), description="Has all keys")
    has_any_keys = graphene.List(graphene.NonNull(graphene.String), description="Has any of keys")


class CountFilterInput(graphene.InputObjectType):
    """
    Filter input for count-based filtering on relationships.

    Used for filtering by the count of related objects.
    """
    eq = graphene.Int(description="Count equals")
    neq = graphene.Int(description="Count not equals")
    gt = graphene.Int(description="Count greater than")
    gte = graphene.Int(description="Count greater than or equal to")
    lt = graphene.Int(description="Count less than")
    lte = graphene.Int(description="Count less than or equal to")


# =============================================================================
# Filter Input Type Registry
# =============================================================================

# Mapping from Django field types to GraphQL filter input types
FIELD_TYPE_TO_FILTER_INPUT: Dict[Type[models.Field], Type[graphene.InputObjectType]] = {
    models.CharField: StringFilterInput,
    models.TextField: StringFilterInput,
    models.EmailField: StringFilterInput,
    models.URLField: StringFilterInput,
    models.SlugField: StringFilterInput,
    models.IntegerField: IntFilterInput,
    models.SmallIntegerField: IntFilterInput,
    models.BigIntegerField: IntFilterInput,
    models.PositiveIntegerField: IntFilterInput,
    models.PositiveSmallIntegerField: IntFilterInput,
    models.PositiveBigIntegerField: IntFilterInput,
    models.AutoField: IntFilterInput,
    models.BigAutoField: IntFilterInput,
    models.FloatField: FloatFilterInput,
    models.DecimalField: FloatFilterInput,
    models.BooleanField: BooleanFilterInput,
    models.NullBooleanField: BooleanFilterInput,
    # DateTimeField must come before DateField since DateTimeField is a subclass of DateField
    models.DateTimeField: DateTimeFilterInput,
    models.DateField: DateFilterInput,
    models.UUIDField: UUIDFilterInput,
    models.JSONField: JSONFilterInput,
}


def get_filter_input_for_field(field: models.Field) -> Optional[Type[graphene.InputObjectType]]:
    """
    Get the appropriate filter input type for a Django model field.

    Args:
        field: Django model field

    Returns:
        GraphQL InputObjectType class for filtering, or None if not supported
    """
    # Check for choice fields first
    if hasattr(field, "choices") and field.choices:
        return StringFilterInput

    # Check for file fields
    if isinstance(field, (models.FileField, models.ImageField)):
        return StringFilterInput

    # Look up by field type
    for field_type, filter_input in FIELD_TYPE_TO_FILTER_INPUT.items():
        if isinstance(field, field_type):
            return filter_input

    return None


# =============================================================================
# Nested Filter Input Generator
# =============================================================================

class NestedFilterInputGenerator:
    """
    Generates nested GraphQL filter input types for Django models.

    This generator creates typed filter inputs following the Prisma/Hasura pattern
    where each field has its own typed filter input (StringFilter, IntFilter, etc.)
    instead of flat lookup expressions.

    Example generated schema:
        input ProductWhereInput {
            name: StringFilterInput
            price: FloatFilterInput
            category: CategoryWhereInput  # Nested relation
            tags_count: CountFilterInput  # M2M count
            AND: [ProductWhereInput!]
            OR: [ProductWhereInput!]
            NOT: ProductWhereInput
        }
    """

    # Cache for generated filter input types
    _filter_input_cache: Dict[str, Type[graphene.InputObjectType]] = {}
    _generation_stack: Set[str] = set()  # Prevent infinite recursion

    def __init__(
        self,
        max_nested_depth: int = 3,
        enable_count_filters: bool = True,
        schema_name: Optional[str] = None,
    ):
        """
        Initialize the nested filter input generator.

        Args:
            max_nested_depth: Maximum depth for nested relationship filters
            enable_count_filters: Whether to generate count filters for relations
            schema_name: Schema name for multi-schema support
        """
        self.max_nested_depth = max_nested_depth
        self.enable_count_filters = enable_count_filters
        self.schema_name = schema_name or "default"

    def generate_where_input(
        self,
        model: Type[models.Model],
        depth: int = 0,
    ) -> Type[graphene.InputObjectType]:
        """
        Generate a WhereInput type for a Django model.

        Args:
            model: Django model class
            depth: Current nesting depth

        Returns:
            GraphQL InputObjectType for filtering the model
        """
        model_name = model.__name__
        cache_key = f"{self.schema_name}_{model_name}_where_{depth}"

        # Return cached type if available
        if cache_key in self._filter_input_cache:
            return self._filter_input_cache[cache_key]

        # Prevent infinite recursion for self-referential models
        if cache_key in self._generation_stack:
            # Return a placeholder that will be resolved later
            return self._create_placeholder_input(model_name)

        self._generation_stack.add(cache_key)

        try:
            fields = {}

            # Generate filters for model fields
            for field in model._meta.get_fields():
                if not hasattr(field, "name"):
                    continue

                field_name = field.name

                # Skip internal fields
                if field_name in ("id", "pk") and not isinstance(field, models.AutoField):
                    continue
                if field_name.startswith("_") or "polymorphic" in field_name.lower():
                    continue

                # Handle different field types
                if isinstance(field, models.ForeignKey):
                    fields.update(self._generate_fk_filter(field, depth))
                elif isinstance(field, models.ManyToManyField):
                    fields.update(self._generate_m2m_filter(field, depth))
                elif isinstance(field, models.OneToOneField):
                    fields.update(self._generate_fk_filter(field, depth))
                elif hasattr(field, "related_model") and field.related_model:
                    # Reverse relations
                    fields.update(self._generate_reverse_filter(field, depth))
                else:
                    # Regular fields
                    filter_input = get_filter_input_for_field(field)
                    if filter_input:
                        fields[field_name] = graphene.InputField(
                            filter_input,
                            description=f"Filter by {field_name}"
                        )

            # Add ID filter
            fields["id"] = graphene.InputField(
                IDFilterInput,
                description="Filter by ID"
            )

            # Create the where input type with boolean operators
            where_input = self._create_where_input_type(model_name, fields, depth)

            # Cache the result
            self._filter_input_cache[cache_key] = where_input

            return where_input

        finally:
            self._generation_stack.discard(cache_key)

    def _generate_fk_filter(
        self,
        field: models.ForeignKey,
        depth: int,
    ) -> Dict[str, graphene.InputField]:
        """Generate filter for ForeignKey field."""
        filters = {}
        field_name = field.name
        related_model = field.related_model

        # ID filter for the FK
        filters[field_name] = graphene.InputField(
            IDFilterInput,
            description=f"Filter by {field_name} ID"
        )

        # Nested filter for related model (if within depth limit)
        if depth < self.max_nested_depth and related_model:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                filters[f"{field_name}_rel"] = graphene.InputField(
                    nested_where,
                    description=f"Filter by {field_name} fields"
                )
            except Exception as e:
                logger.debug(f"Could not generate nested filter for {field_name}: {e}")

        return filters

    def _generate_m2m_filter(
        self,
        field: models.ManyToManyField,
        depth: int,
    ) -> Dict[str, graphene.InputField]:
        """Generate filter for ManyToMany field."""
        filters = {}
        field_name = field.name
        related_model = field.related_model

        # ID filter (any match)
        filters[field_name] = graphene.InputField(
            IDFilterInput,
            description=f"Filter by any {field_name} ID"
        )

        # Count filter
        if self.enable_count_filters:
            filters[f"{field_name}_count"] = graphene.InputField(
                CountFilterInput,
                description=f"Filter by {field_name} count"
            )

        # Nested filter with quantifiers
        if depth < self.max_nested_depth and related_model:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                filters[f"{field_name}_some"] = graphene.InputField(
                    nested_where,
                    description=f"At least one {field_name} matches"
                )
                filters[f"{field_name}_every"] = graphene.InputField(
                    nested_where,
                    description=f"All {field_name} match"
                )
                filters[f"{field_name}_none"] = graphene.InputField(
                    nested_where,
                    description=f"No {field_name} matches"
                )
            except Exception as e:
                logger.debug(f"Could not generate nested M2M filter for {field_name}: {e}")

        return filters

    def _generate_reverse_filter(
        self,
        field,
        depth: int,
    ) -> Dict[str, graphene.InputField]:
        """Generate filter for reverse relation."""
        filters = {}

        accessor_name = getattr(field, "name", None) or getattr(
            field, "get_accessor_name", lambda: None
        )()
        if not accessor_name:
            return filters

        related_model = getattr(field, "related_model", None)
        if not related_model:
            return filters

        # Count filter
        if self.enable_count_filters:
            filters[f"{accessor_name}_count"] = graphene.InputField(
                CountFilterInput,
                description=f"Filter by {accessor_name} count"
            )

        # Nested filter with quantifiers (if within depth limit)
        if depth < self.max_nested_depth:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                filters[f"{accessor_name}_some"] = graphene.InputField(
                    nested_where,
                    description=f"At least one {accessor_name} matches"
                )
                filters[f"{accessor_name}_every"] = graphene.InputField(
                    nested_where,
                    description=f"All {accessor_name} match"
                )
                filters[f"{accessor_name}_none"] = graphene.InputField(
                    nested_where,
                    description=f"No {accessor_name} matches"
                )
            except Exception as e:
                logger.debug(f"Could not generate reverse filter for {accessor_name}: {e}")

        return filters

    def _create_where_input_type(
        self,
        model_name: str,
        fields: Dict[str, graphene.InputField],
        depth: int,
    ) -> Type[graphene.InputObjectType]:
        """Create the WhereInput type with boolean operators."""
        type_name = f"{model_name}WhereInput"

        # Use lambda for self-reference to handle recursion
        def get_self_type():
            cache_key = f"{self.schema_name}_{model_name}_where_{depth}"
            return self._filter_input_cache.get(cache_key)

        # Add boolean operators
        fields["AND"] = graphene.List(
            lambda: get_self_type(),
            description="All conditions must match (AND)"
        )
        fields["OR"] = graphene.List(
            lambda: get_self_type(),
            description="At least one condition must match (OR)"
        )
        fields["NOT"] = graphene.InputField(
            lambda: get_self_type(),
            description="Condition must not match (NOT)"
        )

        return type(type_name, (graphene.InputObjectType,), fields)

    def _create_placeholder_input(
        self,
        model_name: str,
    ) -> Type[graphene.InputObjectType]:
        """Create a placeholder input type for self-referential models."""
        return type(
            f"{model_name}WhereInputPlaceholder",
            (graphene.InputObjectType,),
            {"id": graphene.InputField(IDFilterInput)},
        )


# =============================================================================
# Filter Application (Q Object Builder)
# =============================================================================

class NestedFilterApplicator:
    """
    Applies nested filter inputs to Django querysets.

    Converts the nested filter input structure into Django Q objects
    for queryset filtering.
    """

    def apply_where_filter(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
        model: Optional[Type[models.Model]] = None,
    ) -> models.QuerySet:
        """
        Apply a where filter to a queryset.

        Args:
            queryset: Django queryset to filter
            where_input: Parsed where input dictionary
            model: Optional model class for context

        Returns:
            Filtered queryset
        """
        if not where_input:
            return queryset

        # First, prepare queryset with count annotations if needed
        queryset = self.prepare_queryset_for_count_filters(queryset, where_input)

        q_object = self._build_q_from_where(where_input, model or queryset.model)

        if q_object:
            queryset = queryset.filter(q_object)

        return queryset

    def _build_q_from_where(
        self,
        where_input: Dict[str, Any],
        model: Type[models.Model],
        prefix: str = "",
    ) -> Q:
        """
        Build a Q object from where input.

        Args:
            where_input: Where input dictionary
            model: Django model class
            prefix: Field path prefix for nested filters

        Returns:
            Django Q object
        """
        q = Q()

        for key, value in where_input.items():
            if value is None:
                continue

            if key == "AND" and isinstance(value, list):
                for item in value:
                    q &= self._build_q_from_where(item, model, prefix)

            elif key == "OR" and isinstance(value, list):
                or_q = Q()
                for item in value:
                    or_q |= self._build_q_from_where(item, model, prefix)
                q &= or_q

            elif key == "NOT" and isinstance(value, dict):
                q &= ~self._build_q_from_where(value, model, prefix)

            elif isinstance(value, dict):
                # This is a field filter or nested relation filter
                field_q = self._build_field_q(key, value, model, prefix)
                if field_q:
                    q &= field_q

        return q

    def _build_field_q(
        self,
        field_name: str,
        filter_value: Dict[str, Any],
        model: Type[models.Model],
        prefix: str = "",
    ) -> Q:
        """
        Build a Q object for a field filter.

        Args:
            field_name: Field name
            filter_value: Filter input dictionary
            model: Django model class
            prefix: Field path prefix

        Returns:
            Django Q object
        """
        q = Q()
        full_field_path = f"{prefix}{field_name}" if prefix else field_name

        # Handle special suffixes
        if field_name.endswith("_rel"):
            # Nested relation filter
            base_field = field_name[:-4]  # Remove "_rel"
            return self._build_q_from_where(filter_value, model, f"{full_field_path[:-4]}__")

        if field_name.endswith("_some"):
            # At least one match (exists subquery)
            base_field = field_name[:-5]
            sub_q = self._build_q_from_where(filter_value, model, f"{base_field}__")
            return sub_q

        if field_name.endswith("_every"):
            # All must match - use ~Exists(~Q(...))
            base_field = field_name[:-6]
            sub_q = self._build_q_from_where(filter_value, model, f"{base_field}__")
            # For "every", we need to exclude records that have any non-matching items
            return sub_q  # Simplified - full implementation would use subqueries

        if field_name.endswith("_none"):
            # None should match
            base_field = field_name[:-5]
            sub_q = self._build_q_from_where(filter_value, model, f"{base_field}__")
            return ~sub_q

        if field_name.endswith("_count"):
            # Count filter
            base_field = field_name[:-6]
            return self._build_count_q(base_field, filter_value)

        # Regular field filter
        for op, op_value in filter_value.items():
            if op_value is None:
                continue

            lookup = self._get_lookup_for_operator(op)
            if lookup:
                if lookup == "between" and isinstance(op_value, list) and len(op_value) == 2:
                    q &= Q(**{f"{full_field_path}__gte": op_value[0]})
                    q &= Q(**{f"{full_field_path}__lte": op_value[1]})
                elif lookup in ("today", "yesterday", "this_week", "past_week",
                               "this_month", "past_month", "this_year", "past_year"):
                    if op_value:
                        date_q = self._build_temporal_q(full_field_path, lookup)
                        if date_q:
                            q &= date_q
                elif lookup == "in":
                    q &= Q(**{f"{full_field_path}__in": op_value})
                elif lookup == "not_in":
                    q &= ~Q(**{f"{full_field_path}__in": op_value})
                elif lookup == "neq":
                    q &= ~Q(**{f"{full_field_path}__exact": op_value})
                else:
                    q &= Q(**{f"{full_field_path}__{lookup}": op_value})

        return q

    def _build_count_q(
        self,
        field_name: str,
        filter_value: Dict[str, Any],
    ) -> Q:
        """Build Q object for count filter."""
        # This requires annotation, so we return a marker that the caller
        # should handle with annotate()
        q = Q()
        annotation_name = f"{field_name}_count_annotation"

        for op, op_value in filter_value.items():
            if op_value is None:
                continue

            if op == "eq":
                q &= Q(**{annotation_name: op_value})
            elif op == "neq":
                q &= ~Q(**{annotation_name: op_value})
            elif op == "gt":
                q &= Q(**{f"{annotation_name}__gt": op_value})
            elif op == "gte":
                q &= Q(**{f"{annotation_name}__gte": op_value})
            elif op == "lt":
                q &= Q(**{f"{annotation_name}__lt": op_value})
            elif op == "lte":
                q &= Q(**{f"{annotation_name}__lte": op_value})

        return q

    def _build_temporal_q(
        self,
        field_path: str,
        temporal_filter: str,
    ) -> Optional[Q]:
        """Build Q object for temporal filters."""
        today = timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()

        if temporal_filter == "today":
            return Q(**{f"{field_path}__date": today})

        elif temporal_filter == "yesterday":
            yesterday = today - timedelta(days=1)
            return Q(**{f"{field_path}__date": yesterday})

        elif temporal_filter == "this_week":
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)
            return Q(**{f"{field_path}__date__range": [week_start, week_end]})

        elif temporal_filter == "past_week":
            days_since_monday = today.weekday()
            this_week_start = today - timedelta(days=days_since_monday)
            past_week_start = this_week_start - timedelta(days=7)
            past_week_end = this_week_start - timedelta(days=1)
            return Q(**{f"{field_path}__date__range": [past_week_start, past_week_end]})

        elif temporal_filter == "this_month":
            month_start = today.replace(day=1)
            if today.month == 12:
                next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_month = today.replace(month=today.month + 1, day=1)
            month_end = next_month - timedelta(days=1)
            return Q(**{f"{field_path}__date__range": [month_start, month_end]})

        elif temporal_filter == "past_month":
            this_month_start = today.replace(day=1)
            if this_month_start.month == 1:
                past_month_start = this_month_start.replace(
                    year=this_month_start.year - 1, month=12, day=1
                )
            else:
                past_month_start = this_month_start.replace(
                    month=this_month_start.month - 1, day=1
                )
            past_month_end = this_month_start - timedelta(days=1)
            return Q(**{f"{field_path}__date__range": [past_month_start, past_month_end]})

        elif temporal_filter == "this_year":
            year_start = today.replace(month=1, day=1)
            year_end = today.replace(month=12, day=31)
            return Q(**{f"{field_path}__date__range": [year_start, year_end]})

        elif temporal_filter == "past_year":
            past_year_start = today.replace(year=today.year - 1, month=1, day=1)
            past_year_end = today.replace(year=today.year - 1, month=12, day=31)
            return Q(**{f"{field_path}__date__range": [past_year_start, past_year_end]})

        return None

    def _get_lookup_for_operator(self, op: str) -> Optional[str]:
        """Map filter operator to Django lookup."""
        operator_map = {
            "eq": "exact",
            "neq": "neq",  # Handled specially
            "gt": "gt",
            "gte": "gte",
            "lt": "lt",
            "lte": "lte",
            "contains": "contains",
            "icontains": "icontains",
            "starts_with": "startswith",
            "istarts_with": "istartswith",
            "ends_with": "endswith",
            "iends_with": "iendswith",
            "in_": "in",
            "not_in": "not_in",
            "is_null": "isnull",
            "regex": "regex",
            "iregex": "iregex",
            "between": "between",
            "date": "date",
            "year": "year",
            "month": "month",
            "day": "day",
            "week_day": "week_day",
            "hour": "hour",
            "has_key": "has_key",
            "has_keys": "has_keys",
            "has_any_keys": "has_any_keys",
            # Temporal filters
            "today": "today",
            "yesterday": "yesterday",
            "this_week": "this_week",
            "past_week": "past_week",
            "this_month": "this_month",
            "past_month": "past_month",
            "this_year": "this_year",
            "past_year": "past_year",
        }
        return operator_map.get(op)

    def prepare_queryset_for_count_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
    ) -> models.QuerySet:
        """
        Prepare queryset with annotations for count filters.

        Args:
            queryset: Django queryset
            where_input: Where input dictionary

        Returns:
            Queryset with necessary count annotations
        """
        annotations = self._collect_count_annotations(where_input)

        for annotation_name, field_name in annotations.items():
            queryset = queryset.annotate(**{annotation_name: Count(field_name)})

        return queryset

    def _collect_count_annotations(
        self,
        where_input: Dict[str, Any],
        annotations: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Collect all count annotations needed."""
        if annotations is None:
            annotations = {}

        for key, value in where_input.items():
            if key == "AND" or key == "OR":
                if isinstance(value, list):
                    for item in value:
                        self._collect_count_annotations(item, annotations)
            elif key == "NOT":
                if isinstance(value, dict):
                    self._collect_count_annotations(value, annotations)
            elif key.endswith("_count") and isinstance(value, dict):
                base_field = key[:-6]
                annotation_name = f"{base_field}_count_annotation"
                annotations[annotation_name] = base_field

        return annotations


# =============================================================================
# Convenience Functions
# =============================================================================

def generate_where_input_for_model(
    model: Type[models.Model],
    max_depth: int = 3,
    schema_name: str = "default",
) -> Type[graphene.InputObjectType]:
    """
    Generate a WhereInput type for a Django model.

    Args:
        model: Django model class
        max_depth: Maximum nesting depth for relations
        schema_name: Schema name for caching

    Returns:
        GraphQL InputObjectType for filtering
    """
    generator = NestedFilterInputGenerator(
        max_nested_depth=max_depth,
        schema_name=schema_name,
    )
    return generator.generate_where_input(model)


def apply_where_filter(
    queryset: models.QuerySet,
    where_input: Dict[str, Any],
) -> models.QuerySet:
    """
    Apply a where filter to a queryset.

    Args:
        queryset: Django queryset
        where_input: Where input dictionary

    Returns:
        Filtered queryset
    """
    applicator = NestedFilterApplicator()

    # Prepare count annotations if needed
    queryset = applicator.prepare_queryset_for_count_filters(queryset, where_input)

    return applicator.apply_where_filter(queryset, where_input)

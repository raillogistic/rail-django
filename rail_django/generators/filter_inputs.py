"""
Nested Filter Input Types for GraphQL (Prisma/Hasura Style)

This module provides typed GraphQL InputObjectTypes for filtering with nested
per-field filter inputs following the Prisma/Hasura pattern, offering better
schema organization and type reusability.

Features:
- Typed filter inputs (StringFilterInput, IntFilterInput, etc.)
- Boolean operators (AND, OR, NOT)
- Relationship quantifiers (_some, _every, _none)
- Count filters for relationships
- Quick filter (multi-field search)
- Include filter (ID union)
- Historical model support (django-simple-history)
- GraphQLMeta integration
- Performance analysis and optimization suggestions

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
        quick: "search term"
        include: ["1", "2", "3"]
      }) {
        id
        name
      }
    }
"""

from __future__ import annotations
from django.core.exceptions import FieldDoesNotExist

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

import graphene
from graphene.utils.str_converters import to_camel_case
from django.db import models
from django.db.models import (
    Avg,
    Case,
    Count,
    Exists,
    F,
    Max,
    Min,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
    Window,
)
from django.db.models.fields import IntegerField, FloatField
from django.db.models.functions import (
    Rank,
    DenseRank,
    RowNumber,
    PercentRank,
    Lag,
    Lead,
    TruncYear,
    TruncQuarter,
    TruncMonth,
    TruncWeek,
    TruncDay,
    TruncHour,
    TruncMinute,
    ExtractYear,
    ExtractMonth,
    ExtractDay,
    ExtractWeekDay,
    ExtractIsoWeekDay,
    ExtractWeek,
    ExtractIsoYear,
    ExtractQuarter,
    ExtractHour,
    ExtractMinute,
    ExtractSecond,
)
from django.utils import timezone

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_MAX_NESTED_DEPTH = 3
MAX_ALLOWED_NESTED_DEPTH = 5
DEFAULT_CACHE_MAX_SIZE = 100

# Security constants (defaults, can be overridden via FilteringSettings)
DEFAULT_MAX_REGEX_LENGTH = 500
DEFAULT_MAX_FILTER_DEPTH = 10
DEFAULT_MAX_FILTER_CLAUSES = 50


# =============================================================================
# Security Validation Functions
# =============================================================================


class FilterSecurityError(ValueError):
    """Raised when a filter violates security constraints."""

    pass


def validate_regex_pattern(
    pattern: str,
    max_length: int = DEFAULT_MAX_REGEX_LENGTH,
    check_redos: bool = True,
) -> str:
    """
    Validate regex pattern for safety.

    Checks for:
    - Pattern length limits
    - Valid regex syntax
    - Known ReDoS (Regular Expression Denial of Service) patterns

    Args:
        pattern: The regex pattern to validate
        max_length: Maximum allowed pattern length
        check_redos: Whether to check for ReDoS patterns

    Returns:
        The validated pattern (unchanged if valid)

    Raises:
        FilterSecurityError: If pattern is invalid or potentially dangerous
    """
    import re

    if not pattern:
        return pattern

    # Length limit
    if len(pattern) > max_length:
        raise FilterSecurityError(
            f"Regex pattern too long: {len(pattern)} chars (max {max_length})"
        )

    # Try to compile to check validity
    try:
        re.compile(pattern)
    except re.error as e:
        raise FilterSecurityError(f"Invalid regex pattern: {e}")

    # Check for known ReDoS patterns (catastrophic backtracking)
    # These patterns can cause exponential time complexity
    if check_redos:
        redos_patterns = [
            r"\(\.\*\)\+",  # (.*)+
            r"\(\.\+\)\+",  # (.+)+
            r"\(\[^\]]*\]\+\)\+",  # ([abc]+)+
            r"\(.*\|.*\)\+",  # (a|b)+ with complex alternatives
            r"\(\.\*\)\*",  # (.*)*
            r"\(\.\+\)\*",  # (.+)*
        ]

        for dangerous in redos_patterns:
            if re.search(dangerous, pattern):
                raise FilterSecurityError(
                    "Regex pattern contains potentially dangerous constructs that could cause "
                    "catastrophic backtracking. Avoid nested quantifiers like (.*)+, (.+)+, etc."
                )

    return pattern


def validate_filter_depth(
    where_input: Dict,
    current_depth: int = 0,
    max_allowed_depth: int = DEFAULT_MAX_FILTER_DEPTH,
) -> int:
    """
    Validate that filter nesting depth doesn't exceed the limit.

    Args:
        where_input: The where filter dictionary
        current_depth: Current nesting depth
        max_allowed_depth: Maximum allowed nesting depth

    Returns:
        Maximum depth found

    Raises:
        FilterSecurityError: If depth exceeds max_allowed_depth
    """
    if current_depth > max_allowed_depth:
        raise FilterSecurityError(
            f"Filter nesting too deep: depth {current_depth} exceeds maximum {max_allowed_depth}"
        )

    found_max_depth = current_depth

    for key, value in where_input.items():
        if value is None:
            continue

        if key in ("AND", "OR") and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    depth = validate_filter_depth(
                        item, current_depth + 1, max_allowed_depth
                    )
                    found_max_depth = max(found_max_depth, depth)

        elif key == "NOT" and isinstance(value, dict):
            depth = validate_filter_depth(value, current_depth + 1, max_allowed_depth)
            found_max_depth = max(found_max_depth, depth)

        elif isinstance(value, dict):
            # Nested field filter or relation filter
            depth = validate_filter_depth(value, current_depth + 1, max_allowed_depth)
            found_max_depth = max(found_max_depth, depth)

    return found_max_depth


def count_filter_clauses(where_input: Dict) -> int:
    """
    Count the total number of filter clauses in a where input.

    Args:
        where_input: The where filter dictionary

    Returns:
        Total number of filter clauses
    """
    count = 0

    for key, value in where_input.items():
        if value is None:
            continue

        count += 1

        if key in ("AND", "OR") and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    count += count_filter_clauses(item)

        elif key == "NOT" and isinstance(value, dict):
            count += count_filter_clauses(value)

        elif isinstance(value, dict):
            count += count_filter_clauses(value)

    return count


def validate_filter_complexity(
    where_input: Dict,
    max_depth: int = DEFAULT_MAX_FILTER_DEPTH,
    max_clauses: int = DEFAULT_MAX_FILTER_CLAUSES,
) -> None:
    """
    Validate that filter complexity doesn't exceed limits.

    Checks both depth and total clause count.

    Args:
        where_input: The where filter dictionary
        max_depth: Maximum allowed nesting depth
        max_clauses: Maximum allowed filter clauses

    Raises:
        FilterSecurityError: If filter exceeds complexity limits
    """
    if not where_input:
        return

    # Check depth
    validate_filter_depth(where_input, max_allowed_depth=max_depth)

    # Check clause count
    clause_count = count_filter_clauses(where_input)
    if clause_count > max_clauses:
        raise FilterSecurityError(
            f"Filter too complex: {clause_count} clauses (max {max_clauses})"
        )


# =============================================================================
# Singleton Registries for Filter Generators and Applicators
# =============================================================================

_filter_applicator_registry: Dict[str, "NestedFilterApplicator"] = {}
_filter_generator_registry: Dict[str, "NestedFilterInputGenerator"] = {}


def get_nested_filter_applicator(
    schema_name: str = "default",
) -> "NestedFilterApplicator":
    """
    Get or create a filter applicator for the schema (singleton pattern).

    This ensures filter applicators are reused across requests, avoiding
    repeated initialization overhead.

    Args:
        schema_name: Schema name for multi-schema support

    Returns:
        NestedFilterApplicator instance for the schema
    """
    if schema_name not in _filter_applicator_registry:
        _filter_applicator_registry[schema_name] = NestedFilterApplicator(schema_name)
    return _filter_applicator_registry[schema_name]


def get_nested_filter_generator(
    schema_name: str = "default",
) -> "NestedFilterInputGenerator":
    """
    Get or create a filter generator for the schema (singleton pattern).

    This ensures filter generators are reused across requests, avoiding
    repeated initialization and cache misses.

    Args:
        schema_name: Schema name for multi-schema support

    Returns:
        NestedFilterInputGenerator instance for the schema
    """
    if schema_name not in _filter_generator_registry:
        _filter_generator_registry[schema_name] = NestedFilterInputGenerator(
            schema_name=schema_name
        )
    return _filter_generator_registry[schema_name]


def clear_filter_caches(schema_name: Optional[str] = None) -> None:
    """
    Clear filter caches. Call on schema reload or in tests.

    Args:
        schema_name: Specific schema to clear, or None for all schemas
    """
    if schema_name:
        # Clear specific schema
        applicator = _filter_applicator_registry.pop(schema_name, None)
        generator = _filter_generator_registry.pop(schema_name, None)
        # Clear instance caches if they exist
        if generator:
            generator.clear_cache()
    else:
        # Clear all schemas
        for generator in _filter_generator_registry.values():
            generator.clear_cache()
        _filter_applicator_registry.clear()
        _filter_generator_registry.clear()


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
    starts_with = graphene.String(
        name="startsWith", description="Starts with (case-sensitive)"
    )
    istarts_with = graphene.String(
        name="istartsWith", description="Starts with (case-insensitive)"
    )
    ends_with = graphene.String(
        name="endsWith", description="Ends with (case-sensitive)"
    )
    iends_with = graphene.String(
        name="iendsWith", description="Ends with (case-insensitive)"
    )
    in_ = graphene.List(
        graphene.NonNull(graphene.String), name="in", description="In list"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.String), name="notIn", description="Not in list"
    )
    is_null = graphene.Boolean(name="isNull", description="Is null")
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
    in_ = graphene.List(
        graphene.NonNull(graphene.Int), name="in", description="In list"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.Int), name="notIn", description="Not in list"
    )
    between = graphene.List(graphene.Int, description="Between [min, max] inclusive")
    is_null = graphene.Boolean(name="isNull", description="Is null")


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
    in_ = graphene.List(
        graphene.NonNull(graphene.Float), name="in", description="In list"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.Float), name="notIn", description="Not in list"
    )
    between = graphene.List(graphene.Float, description="Between [min, max] inclusive")
    is_null = graphene.Boolean(name="isNull", description="Is null")


class BooleanFilterInput(graphene.InputObjectType):
    """
    Filter input for boolean fields.
    """

    eq = graphene.Boolean(description="Equal to")
    is_null = graphene.Boolean(name="isNull", description="Is null")


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
    is_null = graphene.Boolean(name="isNull", description="Is null")
    # Temporal convenience filters
    year = graphene.Int(description="Filter by year")
    month = graphene.Int(description="Filter by month (1-12)")
    day = graphene.Int(description="Filter by day of month")
    week_day = graphene.Int(
        name="weekDay", description="Filter by day of week (1=Sunday, 7=Saturday)"
    )
    # Relative date filters
    today = graphene.Boolean(description="Is today")
    yesterday = graphene.Boolean(description="Is yesterday")
    this_week = graphene.Boolean(name="thisWeek", description="Is this week")
    past_week = graphene.Boolean(name="pastWeek", description="Is past week")
    this_month = graphene.Boolean(name="thisMonth", description="Is this month")
    past_month = graphene.Boolean(name="pastMonth", description="Is past month")
    this_year = graphene.Boolean(name="thisYear", description="Is this year")
    past_year = graphene.Boolean(name="pastYear", description="Is past year")


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
    between = graphene.List(
        graphene.DateTime, description="Between [start, end] inclusive"
    )
    is_null = graphene.Boolean(name="isNull", description="Is null")
    # Date-only filters (ignores time)
    date = graphene.Date(description="Filter by date part only")
    year = graphene.Int(description="Filter by year")
    month = graphene.Int(description="Filter by month (1-12)")
    day = graphene.Int(description="Filter by day of month")
    week_day = graphene.Int(
        name="weekDay", description="Filter by day of week (1=Sunday, 7=Saturday)"
    )
    hour = graphene.Int(description="Filter by hour (0-23)")
    # Relative date filters
    today = graphene.Boolean(description="Is today")
    yesterday = graphene.Boolean(description="Is yesterday")
    this_week = graphene.Boolean(name="thisWeek", description="Is this week")
    past_week = graphene.Boolean(name="pastWeek", description="Is past week")
    this_month = graphene.Boolean(name="thisMonth", description="Is this month")
    past_month = graphene.Boolean(name="pastMonth", description="Is past month")
    this_year = graphene.Boolean(name="thisYear", description="Is this year")
    past_year = graphene.Boolean(name="pastYear", description="Is past year")


class IDFilterInput(graphene.InputObjectType):
    """
    Filter input for ID/primary key fields.
    """

    eq = graphene.ID(description="Equal to")
    neq = graphene.ID(description="Not equal to")
    in_ = graphene.List(graphene.NonNull(graphene.ID), name="in", description="In list")
    not_in = graphene.List(
        graphene.NonNull(graphene.ID), name="notIn", description="Not in list"
    )
    is_null = graphene.Boolean(name="isNull", description="Is null")


class UUIDFilterInput(graphene.InputObjectType):
    """
    Filter input for UUID fields.
    """

    eq = graphene.String(description="Equal to")
    neq = graphene.String(description="Not equal to")
    in_ = graphene.List(
        graphene.NonNull(graphene.String), name="in", description="In list"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.String), name="notIn", description="Not in list"
    )
    is_null = graphene.Boolean(name="isNull", description="Is null")


class JSONFilterInput(graphene.InputObjectType):
    """
    Filter input for JSON fields.
    """

    eq = graphene.JSONString(description="Exact JSON match")
    is_null = graphene.Boolean(name="isNull", description="Is null")
    has_key = graphene.String(name="hasKey", description="Has key")
    has_keys = graphene.List(
        graphene.NonNull(graphene.String), name="hasKeys", description="Has all keys"
    )
    has_any_keys = graphene.List(
        graphene.NonNull(graphene.String),
        name="hasAnyKeys",
        description="Has any of keys",
    )


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


class AggregationFilterInput(graphene.InputObjectType):
    """
    Filter input for aggregated values on related objects.

    Supports SUM, AVG, MIN, MAX, COUNT, and COUNT_DISTINCT on a selected field.
    """

    field = graphene.String(required=True, description="Field to aggregate")
    sum = graphene.InputField(FloatFilterInput, description="Filter by SUM")
    avg = graphene.InputField(FloatFilterInput, description="Filter by AVG")
    min = graphene.InputField(FloatFilterInput, description="Filter by MIN")
    max = graphene.InputField(FloatFilterInput, description="Filter by MAX")
    count = graphene.InputField(IntFilterInput, description="Filter by COUNT")
    count_distinct = graphene.InputField(
        IntFilterInput,
        name="countDistinct",
        description="Filter by COUNT of distinct values",
    )


class ConditionalAggregationFilterInput(graphene.InputObjectType):
    """
    Filter input for conditional aggregation on related objects.

    Counts or sums only records matching a specific condition.
    """

    field = graphene.String(required=True, description="Field to aggregate")
    filter = graphene.Argument(
        lambda: graphene.JSONString,
        description="Filter condition for records to include in aggregation (JSON)",
    )
    sum = graphene.InputField(FloatFilterInput, description="Filter by conditional SUM")
    avg = graphene.InputField(FloatFilterInput, description="Filter by conditional AVG")
    count = graphene.InputField(
        IntFilterInput, description="Filter by conditional COUNT"
    )


class WindowFunctionEnum(graphene.Enum):
    """Supported window function types."""

    RANK = "rank"
    DENSE_RANK = "dense_rank"
    ROW_NUMBER = "row_number"
    PERCENT_RANK = "percent_rank"


class WindowFilterInput(graphene.InputObjectType):
    """
    Filter input for window function filters.

    Enables filtering by ranking, percentile, or row number within partitions.
    """

    function = graphene.Field(
        WindowFunctionEnum,
        required=True,
        description="Window function to use: rank, dense_rank, row_number, percent_rank",
    )
    partition_by = graphene.List(
        graphene.NonNull(graphene.String),
        name="partitionBy",
        description="Fields to partition by",
    )
    order_by = graphene.List(
        graphene.NonNull(graphene.String),
        required=True,
        name="orderBy",
        description="Fields to order by within partition (prefix with '-' for descending)",
    )
    # Filter conditions
    rank = graphene.InputField(IntFilterInput, description="Filter by rank value")
    percentile = graphene.InputField(
        FloatFilterInput, description="Filter by percentile (0.0-1.0)"
    )


class SubqueryFilterInput(graphene.InputObjectType):
    """
    Filter input for correlated subquery filters.

    Enables filtering by values from the latest/first related record.
    """

    relation = graphene.String(required=True, description="Related field name")
    order_by = graphene.List(
        graphene.NonNull(graphene.String),
        name="orderBy",
        description="Order by fields to determine which related record to use (prefix with '-' for desc)",
    )
    filter = graphene.Argument(
        lambda: graphene.JSONString,
        description="Additional filter on related records (JSON)",
    )
    field = graphene.String(
        required=True, description="Field from related record to compare"
    )
    # Comparison conditions - apply to the subquery result
    # Using JSONString for flexibility since we don't know the field type
    eq = graphene.JSONString(description="Subquery result equals (value as JSON)")
    neq = graphene.JSONString(description="Subquery result not equals (value as JSON)")
    gt = graphene.Float(description="Subquery result greater than")
    gte = graphene.Float(description="Subquery result greater than or equal")
    lt = graphene.Float(description="Subquery result less than")
    lte = graphene.Float(description="Subquery result less than or equal")
    is_null = graphene.Boolean(name="isNull", description="Subquery result is null")


class ExistsFilterInput(graphene.InputObjectType):
    """
    Filter input for existence checks on related records.

    More efficient than _some for simple existence checks.
    """

    relation = graphene.String(required=True, description="Related field name")
    filter = graphene.Argument(
        lambda: graphene.JSONString,
        description="Filter condition for related records (JSON)",
    )
    exists = graphene.Boolean(
        default_value=True,
        description="True to check existence, False to check non-existence",
    )


class ArrayFilterInput(graphene.InputObjectType):
    """
    Filter input for PostgreSQL ArrayField.

    Supports contains, overlap, contained_by, and length operations.
    """

    contains = graphene.List(
        graphene.NonNull(graphene.String),
        description="Array contains all these values",
    )
    contained_by = graphene.List(
        graphene.NonNull(graphene.String),
        description="Array is contained by these values",
    )
    overlaps = graphene.List(
        graphene.NonNull(graphene.String),
        name="overlaps",
        description="Array overlaps with any of these values",
    )
    length = graphene.InputField(IntFilterInput, description="Filter by array length")
    is_null = graphene.Boolean(name="isNull", description="Array is null")


# =============================================================================
# F() Expression Comparison Filter
# =============================================================================


class CompareOperatorEnum(graphene.Enum):
    """Comparison operators for field-to-field comparisons."""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class FieldCompareFilterInput(graphene.InputObjectType):
    """
    Filter input for comparing fields to each other using F() expressions.

    Enables queries like "price > cost_price" or "updated_at > created_at".
    """

    left = graphene.String(
        required=True,
        description="Left-hand field name to compare",
    )
    operator = graphene.Field(
        CompareOperatorEnum,
        required=True,
        description="Comparison operator: eq, neq, gt, gte, lt, lte",
    )
    right = graphene.String(
        required=True,
        description="Right-hand field name to compare against",
    )
    right_multiplier = graphene.Float(
        name="rightMultiplier",
        description="Optional multiplier for the right-hand field (e.g., 1.5 for right * 1.5)",
    )
    right_offset = graphene.Float(
        name="rightOffset",
        description="Optional offset to add to the right-hand field (e.g., 10 for right + 10)",
    )


# =============================================================================
# Date Truncation Filter
# =============================================================================


class DateTruncPrecisionEnum(graphene.Enum):
    """Date truncation precision levels."""

    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"


class DateTruncFilterInput(graphene.InputObjectType):
    """
    Filter input for date truncation comparisons.

    Enables filtering by truncated date parts (e.g., all orders in Q1 2024).
    """

    precision = graphene.Field(
        DateTruncPrecisionEnum,
        required=True,
        description="Truncation precision: year, quarter, month, week, day, hour, minute",
    )
    # Filter by specific value
    value = graphene.String(
        description="Date value to match (ISO format: 2024-01-01 or 2024-03 for month)",
    )
    year = graphene.Int(description="Filter by year")
    quarter = graphene.Int(description="Filter by quarter (1-4)")
    month = graphene.Int(description="Filter by month (1-12)")
    week = graphene.Int(description="Filter by week number (1-53)")
    # Relative period filters
    this_period = graphene.Boolean(
        name="thisPeriod",
        description="Filter by current period (this year/quarter/month/week/day)",
    )
    last_period = graphene.Boolean(
        name="lastPeriod",
        description="Filter by previous period (last year/quarter/month/week/day)",
    )


class ExtractDateFilterInput(graphene.InputObjectType):
    """
    Filter input for extracting and filtering by date/time components.

    Unlike truncation which rounds to period boundaries, extraction pulls out
    specific parts of a date for comparison. Useful for recurring patterns
    like "all orders on Fridays" or "all invoices due on the 15th".
    """

    year = graphene.InputField(
        IntFilterInput,
        description="Filter by year (e.g., 2024)",
    )
    month = graphene.InputField(
        IntFilterInput,
        description="Filter by month (1-12)",
    )
    day = graphene.InputField(
        IntFilterInput,
        description="Filter by day of month (1-31)",
    )
    quarter = graphene.InputField(
        IntFilterInput,
        description="Filter by quarter (1-4)",
    )
    week = graphene.InputField(
        IntFilterInput,
        description="Filter by ISO week number (1-53)",
    )
    day_of_week = graphene.InputField(
        IntFilterInput,
        name="dayOfWeek",
        description="Filter by day of week (1=Sunday, 7=Saturday)",
    )
    day_of_year = graphene.InputField(
        IntFilterInput,
        name="dayOfYear",
        description="Filter by day of year (1-366)",
    )
    iso_week_day = graphene.InputField(
        IntFilterInput,
        name="isoWeekDay",
        description="Filter by ISO week day (1=Monday, 7=Sunday)",
    )
    iso_year = graphene.InputField(
        IntFilterInput,
        name="isoYear",
        description="Filter by ISO week-numbering year",
    )
    hour = graphene.InputField(
        IntFilterInput,
        description="Filter by hour (0-23)",
    )
    minute = graphene.InputField(
        IntFilterInput,
        description="Filter by minute (0-59)",
    )
    second = graphene.InputField(
        IntFilterInput,
        description="Filter by second (0-59)",
    )


class FullTextSearchTypeEnum(graphene.Enum):
    """Supported full-text search query modes."""

    PLAIN = "plain"
    PHRASE = "phrase"
    WEBSEARCH = "websearch"
    RAW = "raw"


class FullTextSearchInput(graphene.InputObjectType):
    """
    Full-text search configuration.
    """

    query = graphene.String(required=True, description="Search query")
    fields = graphene.List(
        graphene.NonNull(graphene.String),
        description="Fields to search (supports relations: 'author__name')",
    )
    config = graphene.String(description="Text search configuration (Postgres only)")
    rank_threshold = graphene.Float(description="Minimum search rank (0.0-1.0)")
    search_type = graphene.Field(
        lambda: FullTextSearchTypeEnum,
        description="Search type: plain, phrase, websearch, raw",
        default_value=FullTextSearchTypeEnum.WEBSEARCH,
    )


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


def get_filter_input_for_field(
    field: models.Field,
) -> Optional[Type[graphene.InputObjectType]]:
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

    Note: Use get_nested_filter_generator() to obtain singleton instances
    for better cache reuse across requests.
    """

    def __init__(
        self,
        max_nested_depth: int = 3,
        enable_count_filters: bool = True,
        schema_name: Optional[str] = None,
        cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
    ):
        """
        Initialize the nested filter input generator.

        Args:
            max_nested_depth: Maximum depth for nested relationship filters
            enable_count_filters: Whether to generate count filters for relations
            schema_name: Schema name for multi-schema support
            cache_max_size: Maximum number of cached filter input types
        """
        self.max_nested_depth = max_nested_depth
        self.enable_count_filters = enable_count_filters
        self.schema_name = schema_name or "default"
        self.cache_max_size = cache_max_size

        # Instance-level cache (not class-level) for better isolation
        self._filter_input_cache: Dict[str, Type[graphene.InputObjectType]] = {}
        self._generation_stack: Set[str] = set()  # Prevent infinite recursion

        try:
            from ..core.settings import FilteringSettings

            self.filtering_settings = FilteringSettings.from_schema(self.schema_name)
        except (ImportError, AttributeError, KeyError):
            self.filtering_settings = None

    def clear_cache(self) -> None:
        """Clear the filter input cache for this generator."""
        self._filter_input_cache.clear()
        self._generation_stack.clear()

    def _evict_cache_if_needed(self) -> None:
        """Evict oldest cache entries if cache exceeds max size."""
        if len(self._filter_input_cache) >= self.cache_max_size:
            # Remove first 10% of entries (oldest due to insertion order in Python 3.7+)
            keys_to_remove = list(self._filter_input_cache.keys())[
                : self.cache_max_size // 10 or 1
            ]
            for key in keys_to_remove:
                del self._filter_input_cache[key]
            logger.debug(
                f"Evicted {len(keys_to_remove)} cache entries from {self.schema_name} filter generator"
            )

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

        # Evict old entries if cache is full
        self._evict_cache_if_needed()

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
                if field_name in ("id", "pk") and not isinstance(
                    field, models.AutoField
                ):
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
                            name=to_camel_case(field_name),
                            description=f"Filter by {field_name}",
                        )

            # Add ID filter
            fields["id"] = graphene.InputField(
                IDFilterInput, description="Filter by ID"
            )

            # Add quick filter for multi-field search
            fields["quick"] = graphene.InputField(
                graphene.String, description="Quick search across multiple text fields"
            )

            # Add full-text search filter if enabled
            if self.filtering_settings and getattr(
                self.filtering_settings, "enable_full_text_search", False
            ):
                fields["search"] = graphene.InputField(
                    FullTextSearchInput,
                    description="Full-text search (Postgres) with icontains fallback",
                )

            # Add window function filter if enabled
            if self.filtering_settings and getattr(
                self.filtering_settings, "enable_window_filters", False
            ):
                fields["_window"] = graphene.InputField(
                    WindowFilterInput,
                    name="_window",
                    description="Filter by window function (rank, percentile, row_number)",
                )

            # Add subquery filter if enabled
            if self.filtering_settings and getattr(
                self.filtering_settings, "enable_subquery_filters", False
            ):
                fields["_subquery"] = graphene.InputField(
                    SubqueryFilterInput,
                    name="_subquery",
                    description="Filter by correlated subquery (e.g., latest related record)",
                )
                fields["_exists"] = graphene.InputField(
                    ExistsFilterInput,
                    name="_exists",
                    description="Filter by existence of related records",
                )

            # Add array filter fields for ArrayField columns
            if self.filtering_settings and getattr(
                self.filtering_settings, "enable_array_filters", False
            ):
                fields.update(self._generate_array_field_filters(model))

            # Add field comparison filter if enabled
            if self.filtering_settings and getattr(
                self.filtering_settings, "enable_field_comparison", False
            ):
                fields["_compare"] = graphene.InputField(
                    FieldCompareFilterInput,
                    name="_compare",
                    description="Compare fields to each other (e.g., price > cost_price)",
                )

            # Add date truncation filters for date/datetime fields
            if self.filtering_settings and getattr(
                self.filtering_settings, "enable_date_trunc_filters", False
            ):
                fields.update(self._generate_date_trunc_filters(model))

            # Add date extraction filters for date/datetime fields
            if self.filtering_settings and getattr(
                self.filtering_settings, "enable_extract_date_filters", False
            ):
                fields.update(self._generate_date_extract_filters(model))

            # Add include filter for ID union
            fields["include"] = graphene.InputField(
                graphene.List(graphene.NonNull(graphene.ID)),
                description="Include specific IDs regardless of other filters",
            )

            # Add historical filters if applicable
            if self._is_historical_model(model):
                fields.update(self._generate_historical_filters(model))

            # Add computed filters if defined in GraphQLMeta
            fields.update(self._generate_computed_filters(model))

            # Create the where input type with boolean operators
            where_input = self._create_where_input_type(model_name, fields, depth)

            # Cache the result
            self._filter_input_cache[cache_key] = where_input

            return where_input

        finally:
            self._generation_stack.discard(cache_key)

    def _generate_computed_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """Generate inputs for computed/expression filters."""
        fields = {}
        try:
            from ..core.meta import get_model_graphql_meta

            graphql_meta = get_model_graphql_meta(model)
            computed_defs = getattr(graphql_meta, "computed_filters", {})

            for field_name, definition in computed_defs.items():
                filter_type_name = definition.get("filter_type", "string")
                description = definition.get(
                    "description", f"Filter by computed {field_name}"
                )

                filter_type_map = {
                    "string": StringFilterInput,
                    "int": IntFilterInput,
                    "float": FloatFilterInput,
                    "boolean": BooleanFilterInput,
                    "date": DateFilterInput,
                    "datetime": DateTimeFilterInput,
                    "id": IDFilterInput,
                    "uuid": UUIDFilterInput,
                }

                input_type = filter_type_map.get(
                    filter_type_name.lower(), StringFilterInput
                )
                fields[field_name] = graphene.InputField(
                    input_type, name=to_camel_case(field_name), description=description
                )

        except Exception as e:
            logger.debug(f"Error generating computed filters for {model.__name__}: {e}")
            pass

        return fields

    def _generate_array_field_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """Generate filters for ArrayField columns (PostgreSQL)."""
        fields = {}
        try:
            from django.contrib.postgres.fields import ArrayField

            for field in model._meta.get_fields():
                if isinstance(field, ArrayField):
                    field_name = field.name
                    fields[field_name] = graphene.InputField(
                        ArrayFilterInput,
                        name=to_camel_case(field_name),
                        description=f"Filter by {field_name} array field",
                    )
        except ImportError:
            # PostgreSQL not available
            pass
        except Exception as e:
            logger.debug(f"Error generating array filters for {model.__name__}: {e}")

        return fields

    def _generate_date_trunc_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """Generate date truncation filters for date/datetime fields."""
        fields = {}

        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue

            if isinstance(field, (models.DateField, models.DateTimeField)):
                field_name = field.name
                trunc_field_name = f"{field_name}_trunc"
                fields[trunc_field_name] = graphene.InputField(
                    DateTruncFilterInput,
                    name=to_camel_case(trunc_field_name),
                    description=f"Filter {field_name} by truncated date parts",
                )

        return fields

    def _generate_date_extract_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """Generate date extraction filters for date/datetime fields.

        Unlike truncation which rounds to period boundaries, extraction pulls
        out specific components like day_of_week, hour, quarter, etc.
        """
        fields = {}

        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue

            if isinstance(field, (models.DateField, models.DateTimeField)):
                field_name = field.name
                extract_field_name = f"{field_name}_extract"
                fields[extract_field_name] = graphene.InputField(
                    ExtractDateFilterInput,
                    name=to_camel_case(extract_field_name),
                    description=f"Filter {field_name} by extracted date parts (day_of_week, hour, etc.)",
                )

        return fields

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
            name=to_camel_case(field_name),
            description=f"Filter by {field_name} ID",
        )

        # Nested filter for related model (if within depth limit)
        if depth < self.max_nested_depth and related_model:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                rel_name = f"{field_name}_rel"
                filters[rel_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(rel_name),
                    description=f"Filter by {field_name} fields",
                )
            except (FieldDoesNotExist, RecursionError, AttributeError, TypeError) as e:
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
            name=to_camel_case(field_name),
            description=f"Filter by any {field_name} ID",
        )

        # Aggregation filter
        agg_name = f"{field_name}_agg"
        filters[agg_name] = graphene.InputField(
            AggregationFilterInput,
            name=to_camel_case(agg_name),
            description=f"Filter by aggregated {field_name} values",
        )

        # Conditional aggregation filter (if enabled)
        if self.filtering_settings and getattr(
            self.filtering_settings, "enable_conditional_aggregation", False
        ):
            cond_agg_name = f"{field_name}_cond_agg"
            filters[cond_agg_name] = graphene.InputField(
                ConditionalAggregationFilterInput,
                name=to_camel_case(cond_agg_name),
                description=f"Filter by conditional aggregation on {field_name}",
            )

        # Count filter
        if self.enable_count_filters:
            count_name = f"{field_name}_count"
            filters[count_name] = graphene.InputField(
                CountFilterInput,
                name=to_camel_case(count_name),
                description=f"Filter by {field_name} count",
            )

        # Nested filter with quantifiers
        if depth < self.max_nested_depth and related_model:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                some_name = f"{field_name}_some"
                filters[some_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(some_name),
                    description=f"At least one {field_name} matches",
                )
                every_name = f"{field_name}_every"
                filters[every_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(every_name),
                    description=f"All {field_name} match",
                )
                none_name = f"{field_name}_none"
                filters[none_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(none_name),
                    description=f"No {field_name} matches",
                )
            except (FieldDoesNotExist, RecursionError, AttributeError, TypeError) as e:
                logger.debug(
                    f"Could not generate nested M2M filter for {field_name}: {e}"
                )

        return filters

    def _generate_reverse_filter(
        self,
        field,
        depth: int,
    ) -> Dict[str, graphene.InputField]:
        """Generate filter for reverse relation."""
        filters = {}

        accessor_name = (
            getattr(field, "name", None)
            or getattr(field, "get_accessor_name", lambda: None)()
        )
        if not accessor_name:
            return filters

        related_model = getattr(field, "related_model", None)
        if not related_model:
            return filters

        # Aggregation filter
        agg_name = f"{accessor_name}_agg"
        filters[agg_name] = graphene.InputField(
            AggregationFilterInput,
            name=to_camel_case(agg_name),
            description=f"Filter by aggregated {accessor_name} values",
        )

        # Conditional aggregation filter (if enabled)
        if self.filtering_settings and getattr(
            self.filtering_settings, "enable_conditional_aggregation", False
        ):
            cond_agg_name = f"{accessor_name}_cond_agg"
            filters[cond_agg_name] = graphene.InputField(
                ConditionalAggregationFilterInput,
                name=to_camel_case(cond_agg_name),
                description=f"Filter by conditional aggregation on {accessor_name}",
            )

        # Count filter
        if self.enable_count_filters:
            count_name = f"{accessor_name}_count"
            filters[count_name] = graphene.InputField(
                CountFilterInput,
                name=to_camel_case(count_name),
                description=f"Filter by {accessor_name} count",
            )

        # Nested filter with quantifiers (if within depth limit)
        if depth < self.max_nested_depth:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                some_name = f"{accessor_name}_some"
                filters[some_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(some_name),
                    description=f"At least one {accessor_name} matches",
                )
                every_name = f"{accessor_name}_every"
                filters[every_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(every_name),
                    description=f"All {accessor_name} match",
                )
                none_name = f"{accessor_name}_none"
                filters[none_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(none_name),
                    description=f"No {accessor_name} matches",
                )
            except (FieldDoesNotExist, RecursionError, AttributeError, TypeError) as e:
                logger.debug(
                    f"Could not generate reverse filter for {accessor_name}: {e}"
                )

        return filters

    def _create_where_input_type(
        self,
        model_name: str,
        fields: Dict[str, graphene.InputField],
        depth: int,
    ) -> Type[graphene.InputObjectType]:
        """Create the WhereInput type with boolean operators."""
        type_name = f"{model_name}WhereInput"

        # Use a mutable container to hold the type reference.
        # This allows lambdas to reference the type after it's created.
        type_ref = [None]

        # Add boolean operators using lambdas that reference the container
        fields["AND"] = graphene.List(
            lambda: type_ref[0], description="All conditions must match (AND)"
        )
        fields["OR"] = graphene.List(
            lambda: type_ref[0],
            description="At least one condition must match (OR)",
        )
        fields["NOT"] = graphene.InputField(
            lambda: type_ref[0], description="Condition must not match (NOT)"
        )

        # Create the type
        where_input_type = type(type_name, (graphene.InputObjectType,), fields)

        # Store reference for the lambdas to use
        type_ref[0] = where_input_type

        return where_input_type

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

    def _is_historical_model(self, model: Type[models.Model]) -> bool:
        """Check if model is from django-simple-history."""
        try:
            name = getattr(model, "__name__", "")
            module = getattr(model, "__module__", "")
        except (AttributeError, TypeError):
            return False

        if name.startswith("Historical"):
            return True
        return "simple_history" in module

    def _generate_historical_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """Generate filters specific to historical models."""
        filters = {}

        # Instance filter - filter by original instance IDs
        filters["instance_in"] = graphene.InputField(
            graphene.List(graphene.NonNull(graphene.ID)),
            description="Filter by original instance IDs",
        )

        # History type filter
        try:
            history_field = model._meta.get_field("history_type")
            choices = getattr(history_field, "choices", None)
            if choices:
                filters["history_type_in"] = graphene.InputField(
                    graphene.List(graphene.NonNull(graphene.String)),
                    description="Filter by history type (create, update, delete)",
                )
        except FieldDoesNotExist:
            pass

        return filters


# =============================================================================
# Filter Application (Q Object Builder)
# =============================================================================


class NestedFilterApplicator:
    """
    Applies nested filter inputs to Django querysets.

    Converts the nested filter input structure into Django Q objects
    for queryset filtering. Includes support for quick filter, include
    filter, and historical model filters.
    """

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name
        # Lazy-initialized mixins to avoid circular reference
        self._quick_mixin = None
        self._include_mixin = None
        self._historical_mixin = None
        # self._geo_mixin = None
        try:
            from ..core.settings import FilteringSettings

            self.filtering_settings = FilteringSettings.from_schema(self.schema_name)
        except (ImportError, AttributeError, KeyError):
            self.filtering_settings = None

    def _get_quick_mixin(self):
        if self._quick_mixin is None:
            self._quick_mixin = QuickFilterMixin()
        return self._quick_mixin

    def _get_include_mixin(self):
        if self._include_mixin is None:
            self._include_mixin = IncludeFilterMixin()
        return self._include_mixin

    def _get_historical_mixin(self):
        if self._historical_mixin is None:
            self._historical_mixin = HistoricalModelMixin()
        return self._historical_mixin

    # def _get_geo_mixin(self):
    #     if self._geo_mixin is None:
    #         self._geo_mixin = GeoFilterMixin()
    #     return self._geo_mixin

    def apply_presets(
        self,
        where_input: Dict[str, Any],
        presets: List[str],
        model: Type[models.Model],
    ) -> Dict[str, Any]:
        """
        Merge preset filters with user-provided filters.

        Args:
            where_input: User provided where input
            presets: List of preset names to apply
            model: Django model class

        Returns:
            Merged where input dictionary
        """
        if not presets:
            return where_input

        # Lazy import to avoid circular dependency
        from ..core.meta import get_model_graphql_meta

        graphql_meta = get_model_graphql_meta(model)
        if not graphql_meta or not graphql_meta.filter_presets:
            return where_input

        merged = {}

        # Apply presets in order
        for preset_name in presets:
            preset_def = graphql_meta.filter_presets.get(preset_name)
            if preset_def:
                merged = self._deep_merge(merged, preset_def)

        # User filters override presets
        if where_input:
            merged = self._deep_merge(merged, where_input)

        return merged

    def _deep_merge(
        self, dict1: Dict[str, Any], dict2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep merge two dictionaries.

        Args:
            dict1: Base dictionary
            dict2: Override dictionary (takes precedence)

        Returns:
            Merged dictionary
        """
        result = dict1.copy()

        for key, value in dict2.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            elif (
                key == "AND"
                and key in result
                and isinstance(result[key], list)
                and isinstance(value, list)
            ):
                # For AND lists, we combine them
                result[key] = result[key] + value
            else:
                result[key] = value

        return result

    def apply_where_filter(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
        model: Optional[Type[models.Model]] = None,
        quick_filter_fields: Optional[List[str]] = None,
    ) -> models.QuerySet:
        """
        Apply a where filter to a queryset.

        Args:
            queryset: Django queryset to filter
            where_input: Parsed where input dictionary
            model: Optional model class for context
            quick_filter_fields: Optional list of fields for quick search

        Returns:
            Filtered queryset
        """
        if not where_input:
            return queryset

        model = model or queryset.model

        # Try to get quick fields from GraphQLMeta if not provided
        if quick_filter_fields is None and model:
            try:
                from ..core.meta import get_model_graphql_meta

                meta = get_model_graphql_meta(model)
                if meta and meta.quick_filter_fields:
                    quick_filter_fields = meta.quick_filter_fields
            except (ImportError, AttributeError):
                pass

        # Security validation: check filter depth and complexity
        # Use configurable limits from FilteringSettings
        max_depth = DEFAULT_MAX_FILTER_DEPTH
        max_clauses = DEFAULT_MAX_FILTER_CLAUSES
        if self.filtering_settings:
            max_depth = getattr(self.filtering_settings, "max_filter_depth", max_depth)
            max_clauses = getattr(
                self.filtering_settings, "max_filter_clauses", max_clauses
            )

        try:
            validate_filter_complexity(
                where_input, max_depth=max_depth, max_clauses=max_clauses
            )
        except FilterSecurityError as e:
            logger.warning(
                f"Rejected filter due to security constraints: {e}",
                extra={"model": model.__name__ if model else "unknown"},
            )
            # Return empty queryset for security violations
            return queryset.none()

        # Work on a copy to avoid mutating caller's dictionary
        where_input = dict(where_input)

        # Extract special filters before processing
        include_ids = where_input.pop("include", None)
        quick_value = where_input.pop("quick", None)
        search_input = where_input.pop("search", None)

        # Handle historical filters
        instance_in = where_input.pop("instance_in", None)
        history_type_in = where_input.pop("history_type_in", None)

        # Extract advanced filter types
        window_filter = where_input.pop("_window", None)
        subquery_filter = where_input.pop("_subquery", None)
        exists_filter = where_input.pop("_exists", None)
        compare_filter = where_input.pop("_compare", None)

        # Extract date trunc filters (they have _trunc suffix)
        date_trunc_filters = {}
        for key in list(where_input.keys()):
            if key.endswith("_trunc"):
                date_trunc_filters[key] = where_input.pop(key)

        # Extract date extract filters (they have _extract suffix)
        date_extract_filters = {}
        for key in list(where_input.keys()):
            if key.endswith("_extract"):
                date_extract_filters[key] = where_input.pop(key)

        # First, prepare queryset with aggregation annotations if needed
        queryset = self.prepare_queryset_for_aggregation_filters(queryset, where_input)

        # Prepare queryset with conditional aggregation annotations if needed
        queryset = self.prepare_queryset_for_conditional_aggregation_filters(
            queryset, where_input
        )

        # Then, prepare queryset with count annotations if needed
        queryset = self.prepare_queryset_for_count_filters(queryset, where_input)

        # Then, prepare queryset with computed filters annotations if needed
        queryset = self.prepare_queryset_for_computed_filters(
            queryset, where_input, model
        )

        # Prepare queryset with window function annotations if needed
        if (
            window_filter
            and self.filtering_settings
            and getattr(self.filtering_settings, "enable_window_filters", False)
        ):
            queryset = self.prepare_queryset_for_window_filter(queryset, window_filter)

        # Build and apply main Q object
        q_object = self._build_q_from_where(where_input, model)

        # Apply full-text search
        if (
            search_input
            and self.filtering_settings
            and self.filtering_settings.enable_full_text_search
        ):
            if isinstance(search_input, str):
                search_input = {"query": search_input}
            search_q, search_annotations = self._build_fts_q(search_input, model)
            if search_annotations:
                queryset = queryset.annotate(**search_annotations)
            if search_q:
                q_object &= search_q

        # Apply quick filter
        if quick_value:
            quick_q = self._get_quick_mixin().build_quick_filter_q(
                model, quick_value, quick_filter_fields
            )
            if quick_q:
                q_object &= quick_q

        # Apply historical filters
        if instance_in:
            q_object &= self._get_historical_mixin().build_historical_filter_q(
                "instance_in", instance_in
            )
        if history_type_in:
            q_object &= self._get_historical_mixin().build_historical_filter_q(
                "history_type_in", history_type_in
            )

        # Apply window function filter
        if (
            window_filter
            and self.filtering_settings
            and getattr(self.filtering_settings, "enable_window_filters", False)
        ):
            window_q = self._build_window_filter_q(window_filter)
            if window_q:
                q_object &= window_q

        # Apply subquery filter
        if (
            subquery_filter
            and self.filtering_settings
            and getattr(self.filtering_settings, "enable_subquery_filters", False)
        ):
            subquery_q, subquery_annotations = self._build_subquery_filter_q(
                subquery_filter, model
            )
            if subquery_annotations:
                queryset = queryset.annotate(**subquery_annotations)
            if subquery_q:
                q_object &= subquery_q

        # Apply exists filter
        if (
            exists_filter
            and self.filtering_settings
            and getattr(self.filtering_settings, "enable_subquery_filters", False)
        ):
            exists_q = self._build_exists_filter_q(exists_filter, model)
            if exists_q:
                q_object &= exists_q

        # Apply field comparison filter
        if (
            compare_filter
            and self.filtering_settings
            and getattr(self.filtering_settings, "enable_field_comparison", False)
        ):
            compare_q = self._build_field_compare_q(compare_filter)
            if compare_q:
                q_object &= compare_q

        # Apply date truncation filters
        if (
            date_trunc_filters
            and self.filtering_settings
            and getattr(self.filtering_settings, "enable_date_trunc_filters", False)
        ):
            for field_key, trunc_filter in date_trunc_filters.items():
                # field_key is like "created_at_trunc", base field is "created_at"
                base_field = field_key[:-6]  # Remove "_trunc"
                trunc_q, trunc_annotations = self._build_date_trunc_filter_q(
                    base_field, trunc_filter
                )
                if trunc_annotations:
                    queryset = queryset.annotate(**trunc_annotations)
                if trunc_q:
                    q_object &= trunc_q

        # Apply date extraction filters
        if (
            date_extract_filters
            and self.filtering_settings
            and getattr(self.filtering_settings, "enable_extract_date_filters", False)
        ):
            for field_key, extract_filter in date_extract_filters.items():
                # field_key is like "created_at_extract", base field is "created_at"
                base_field = field_key[:-8]  # Remove "_extract"
                extract_q, extract_annotations = self._build_date_extract_filter_q(
                    base_field, extract_filter
                )
                if extract_annotations:
                    queryset = queryset.annotate(**extract_annotations)
                if extract_q:
                    q_object &= extract_q

        if q_object:
            queryset = queryset.filter(q_object)

        # Apply include filter last (unions IDs into results)
        if include_ids:
            queryset = self._get_include_mixin().apply_include_filter(
                queryset, include_ids
            )

        return queryset

    def prepare_queryset_for_computed_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
        model: Type[models.Model],
    ) -> models.QuerySet:
        """
        Prepare queryset with annotations for computed fields.

        Args:
            queryset: Django queryset
            where_input: Where input dictionary
            model: Django model

        Returns:
            Queryset with necessary computed annotations
        """
        try:
            from ..core.meta import get_model_graphql_meta

            graphql_meta = get_model_graphql_meta(model)
            computed_defs = getattr(graphql_meta, "computed_filters", {})
        except Exception:
            return queryset

        if not computed_defs:
            return queryset

        annotations = {}

        # Flatten input to find all keys used
        # This is a bit simplistic, ideally we'd traverse properly
        # But for annotation purposes, we just need to know if the key exists
        def collect_keys(d, keys):
            for k, v in d.items():
                keys.add(k)
                if isinstance(v, dict):
                    collect_keys(v, keys)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            collect_keys(item, keys)

        used_keys = set()
        collect_keys(where_input, used_keys)

        for field_name, definition in computed_defs.items():
            if field_name in used_keys:
                expression = definition.get("expression")
                if expression:
                    annotations[field_name] = expression

        if annotations:
            queryset = queryset.annotate(**annotations)

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
            return self._build_q_from_where(
                filter_value, model, f"{full_field_path[:-4]}__"
            )

        if field_name.endswith("_some"):
            # At least one match (exists subquery)
            base_field = field_name[:-5]
            sub_q = self._build_q_from_where(filter_value, model, f"{base_field}__")
            return sub_q

        if field_name.endswith("_every"):
            """
            _every means: ALL related objects must match the condition.
            Implementation: Exclude records where ANY related object does NOT match.

            SQL equivalent:
                NOT EXISTS (
                    SELECT 1 FROM related_table
                    WHERE related_table.fk = main.id
                    AND NOT (condition)
                )
            """
            base_field = field_name[:-6]

            # Try to build proper subquery-based filter
            try:
                from django.db.models import Exists, OuterRef

                # Get the relation field to find the related model
                relation_field = self._get_relation_field(model, base_field)
                if relation_field is not None:
                    related_model = getattr(relation_field, "related_model", None)
                    if related_model is not None:
                        # Build condition that matches the filter
                        matching_q = self._build_q_from_where(
                            filter_value, related_model, ""
                        )

                        # Find the FK field pointing back to parent
                        fk_field = self._get_fk_to_parent(related_model, model)
                        if fk_field:
                            # Build subquery for non-matching related objects
                            non_matching = related_model.objects.filter(
                                **{fk_field: OuterRef("pk")}
                            ).exclude(matching_q)

                            # Exclude parents that have ANY non-matching children
                            # Also ensure parent has at least one child (empty set vacuously matches "every")
                            has_children = related_model.objects.filter(
                                **{fk_field: OuterRef("pk")}
                            )

                            return Q(Exists(has_children)) & ~Q(Exists(non_matching))
            except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
                logger.debug(
                    f"Could not build optimized _every filter for {base_field}: {e}"
                )

            # Fallback: use simple approach (may have edge cases with empty sets)
            # This matches records where at least one child matches
            sub_q = self._build_q_from_where(filter_value, model, f"{base_field}__")
            logger.debug(
                f"_every filter for {base_field} using fallback implementation"
            )
            return sub_q

        if field_name.endswith("_none"):
            # None should match
            base_field = field_name[:-5]
            sub_q = self._build_q_from_where(filter_value, model, f"{base_field}__")
            return ~sub_q

        if field_name.endswith("_cond_agg"):
            # Conditional aggregation filter (must check before _agg)
            base_field = full_field_path[:-9]
            return self._build_conditional_aggregation_q(base_field, filter_value)

        if field_name.endswith("_agg"):
            # Aggregation filter
            base_field = full_field_path[:-4]
            return self._build_aggregation_q(base_field, filter_value)

        # Check if this is an ArrayField filter
        try:
            field_obj = model._meta.get_field(field_name)
            try:
                from django.contrib.postgres.fields import ArrayField

                if isinstance(field_obj, ArrayField):
                    return self._build_array_field_q(full_field_path, filter_value)
            except ImportError:
                pass
        except FieldDoesNotExist:
            pass

        if field_name.endswith("_count"):
            # Check if this is a real field first (e.g. inventory_count)
            is_real_field = False
            try:
                model._meta.get_field(field_name)
                is_real_field = True
            except FieldDoesNotExist:
                pass

            if not is_real_field:
                # Count filter
                base_field = field_name[:-6]
                return self._build_count_q(base_field, filter_value)

        # Regular field filter
        for op, op_value in filter_value.items():
            if op_value is None:
                continue

            lookup = self._get_lookup_for_operator(op)
            if lookup:
                # Validate regex patterns for security
                if lookup in ("regex", "iregex"):
                    # Get configurable limits from settings
                    max_regex_len = DEFAULT_MAX_REGEX_LENGTH
                    reject_unsafe = True
                    if self.filtering_settings:
                        max_regex_len = getattr(
                            self.filtering_settings, "max_regex_length", max_regex_len
                        )
                        reject_unsafe = getattr(
                            self.filtering_settings, "reject_unsafe_regex", True
                        )

                    try:
                        op_value = validate_regex_pattern(
                            op_value,
                            max_length=max_regex_len,
                            check_redos=reject_unsafe,
                        )
                    except FilterSecurityError as e:
                        logger.warning(f"Rejected unsafe regex filter: {e}")
                        continue  # Skip this filter clause

                if (
                    lookup == "between"
                    and isinstance(op_value, list)
                    and len(op_value) == 2
                ):
                    q &= Q(**{f"{full_field_path}__gte": op_value[0]})
                    q &= Q(**{f"{full_field_path}__lte": op_value[1]})
                elif lookup in (
                    "today",
                    "yesterday",
                    "this_week",
                    "past_week",
                    "this_month",
                    "past_month",
                    "this_year",
                    "past_year",
                ):
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

    def _build_numeric_q(
        self,
        field_path: str,
        filter_value: Dict[str, Any],
    ) -> Q:
        """Build Q object for numeric-like filters on a field or annotation."""
        q = Q()

        for op, op_value in filter_value.items():
            if op_value is None:
                continue

            lookup = self._get_lookup_for_operator(op)
            if not lookup:
                continue

            if (
                lookup == "between"
                and isinstance(op_value, list)
                and len(op_value) == 2
            ):
                q &= Q(**{f"{field_path}__gte": op_value[0]})
                q &= Q(**{f"{field_path}__lte": op_value[1]})
            elif lookup == "in":
                q &= Q(**{f"{field_path}__in": op_value})
            elif lookup == "not_in":
                q &= ~Q(**{f"{field_path}__in": op_value})
            elif lookup == "neq":
                q &= ~Q(**{f"{field_path}__exact": op_value})
            else:
                q &= Q(**{f"{field_path}__{lookup}": op_value})

        return q

    def _aggregation_annotation_name(
        self,
        relation_path: str,
        target_field: str,
        agg_type: str,
    ) -> str:
        """Build a stable annotation name for aggregation filters."""
        safe_relation = relation_path.replace("__", "_")
        safe_target = (target_field or "id").replace("__", "_")
        return f"{safe_relation}_agg_{safe_target}_{agg_type}"

    def _build_aggregation_q(
        self,
        field_path: str,
        agg_filter: Dict[str, Any],
    ) -> Q:
        """Build Q object for aggregation filters."""
        q = Q()
        target_field = agg_filter.get("field") or "id"

        for agg_type in ("sum", "avg", "min", "max", "count", "count_distinct"):
            agg_value = agg_filter.get(agg_type)
            if not isinstance(agg_value, dict):
                continue
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, agg_type
            )
            q &= self._build_numeric_q(annotation_name, agg_value)

        return q

    def _build_fts_q(
        self,
        search_input: Dict[str, Any],
        model: Type[models.Model],
    ) -> tuple[Q, Dict[str, Any]]:
        """Build full-text search Q object and annotations."""
        from django.db import connection

        query_text = (
            search_input.get("query") if isinstance(search_input, dict) else None
        )
        if not query_text:
            return Q(), {}

        fields = search_input.get("fields") if isinstance(search_input, dict) else None
        if isinstance(fields, str):
            fields = [fields]
        if not fields:
            fields = self._get_quick_mixin().get_default_quick_filter_fields(model)
        fields = [f for f in fields if isinstance(f, str) and f]
        if not fields:
            return Q(), {}

        config = search_input.get("config") or (
            self.filtering_settings.fts_config if self.filtering_settings else "english"
        )
        search_type = search_input.get("search_type") or (
            self.filtering_settings.fts_search_type
            if self.filtering_settings
            else "websearch"
        )
        if search_type is not None and not isinstance(search_type, str):
            search_type = getattr(search_type, "value", str(search_type))
        rank_threshold = search_input.get("rank_threshold")
        if rank_threshold is None and self.filtering_settings:
            rank_threshold = self.filtering_settings.fts_rank_threshold

        if connection.vendor == "postgresql":
            try:
                from django.contrib.postgres.search import (
                    SearchVector,
                    SearchQuery,
                    SearchRank,
                )

                vector = SearchVector(*fields, config=config)
                query = SearchQuery(query_text, config=config, search_type=search_type)

                annotations = {
                    "_search_vector": vector,
                    "_search_rank": SearchRank(vector, query),
                }

                q = Q(_search_vector=query)
                if rank_threshold is not None:
                    q &= Q(_search_rank__gte=rank_threshold)

                return q, annotations
            except (ImportError, TypeError, ValueError) as e:
                logger.debug(f"Full-text search setup failed, falling back: {e}")

        fallback_q = Q()
        for field_path in fields:
            field = self._get_quick_mixin()._get_field_from_path(model, field_path)
            if field and isinstance(
                field, (models.CharField, models.TextField, models.EmailField)
            ):
                fallback_q |= Q(**{f"{field_path}__icontains": query_text})

        return fallback_q, {}

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

    def prepare_queryset_for_aggregation_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
    ) -> models.QuerySet:
        """
        Prepare queryset with annotations for aggregation filters.

        Args:
            queryset: Django queryset
            where_input: Where input dictionary

        Returns:
            Queryset with necessary aggregation annotations
        """
        annotations = self._collect_aggregation_annotations(where_input)

        if annotations:
            queryset = queryset.annotate(**annotations)

        return queryset

    def _collect_aggregation_annotations(
        self,
        where_input: Dict[str, Any],
        annotations: Optional[Dict[str, Any]] = None,
        prefix: str = "",
    ) -> Dict[str, Any]:
        """Collect all aggregation annotations needed."""
        if annotations is None:
            annotations = {}

        for key, value in where_input.items():
            if value is None:
                continue

            if key in ("AND", "OR") and isinstance(value, list):
                for item in value:
                    self._collect_aggregation_annotations(item, annotations, prefix)
                continue

            if key == "NOT" and isinstance(value, dict):
                self._collect_aggregation_annotations(value, annotations, prefix)
                continue

            if not isinstance(value, dict):
                continue

            if key.endswith("_rel"):
                base_field = key[:-4]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            if key.endswith("_some"):
                base_field = key[:-5]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            if key.endswith("_every"):
                base_field = key[:-6]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            if key.endswith("_none"):
                base_field = key[:-5]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            # Skip conditional aggregation filters - they're handled separately
            if key.endswith("_cond_agg"):
                continue

            if key.endswith("_agg"):
                base_field = key[:-4]
                full_field_path = f"{prefix}{base_field}" if prefix else base_field
                annotations.update(
                    self._build_aggregation_annotations(full_field_path, value)
                )

        return annotations

    def _build_aggregation_annotations(
        self,
        field_path: str,
        agg_filter: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build annotations for aggregation filters."""
        annotations: Dict[str, Any] = {}
        target_field = agg_filter.get("field") or "id"

        if target_field:
            lookup_path = f"{field_path}__{target_field}"
        else:
            lookup_path = field_path

        if agg_filter.get("sum") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "sum"
            )
            annotations[annotation_name] = Sum(lookup_path)

        if agg_filter.get("avg") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "avg"
            )
            annotations[annotation_name] = Avg(lookup_path)

        if agg_filter.get("min") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "min"
            )
            annotations[annotation_name] = Min(lookup_path)

        if agg_filter.get("max") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "max"
            )
            annotations[annotation_name] = Max(lookup_path)

        if agg_filter.get("count") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "count"
            )
            annotations[annotation_name] = Count(lookup_path)

        if agg_filter.get("count_distinct") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "count_distinct"
            )
            annotations[annotation_name] = Count(lookup_path, distinct=True)

        return annotations

    # =========================================================================
    # Conditional Aggregation Filter Methods
    # =========================================================================

    def prepare_queryset_for_conditional_aggregation_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
    ) -> models.QuerySet:
        """Prepare queryset with conditional aggregation annotations."""
        annotations = self._collect_conditional_aggregation_annotations(where_input)
        if annotations:
            queryset = queryset.annotate(**annotations)
        return queryset

    def _collect_conditional_aggregation_annotations(
        self,
        where_input: Dict[str, Any],
        annotations: Optional[Dict[str, Any]] = None,
        prefix: str = "",
    ) -> Dict[str, Any]:
        """Collect all conditional aggregation annotations needed."""
        if annotations is None:
            annotations = {}

        for key, value in where_input.items():
            if value is None:
                continue

            if key in ("AND", "OR") and isinstance(value, list):
                for item in value:
                    self._collect_conditional_aggregation_annotations(
                        item, annotations, prefix
                    )
                continue

            if key == "NOT" and isinstance(value, dict):
                self._collect_conditional_aggregation_annotations(
                    value, annotations, prefix
                )
                continue

            if not isinstance(value, dict):
                continue

            if key.endswith("_cond_agg"):
                base_field = key[:-9]
                full_field_path = f"{prefix}{base_field}" if prefix else base_field
                annotations.update(
                    self._build_conditional_aggregation_annotations(
                        full_field_path, value
                    )
                )

        return annotations

    def _build_conditional_aggregation_annotations(
        self,
        field_path: str,
        cond_agg_filter: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build annotations for conditional aggregation filters."""
        import json

        annotations: Dict[str, Any] = {}
        target_field = cond_agg_filter.get("field") or "id"
        condition_json = cond_agg_filter.get("filter")

        # Parse the filter condition JSON
        condition_q = Q()
        if condition_json:
            try:
                if isinstance(condition_json, str):
                    condition_dict = json.loads(condition_json)
                else:
                    condition_dict = condition_json
                # Build Q object from the condition (simple key-value for now)
                for k, v in condition_dict.items():
                    if isinstance(v, dict):
                        for op, op_val in v.items():
                            lookup = self._get_lookup_for_operator(op)
                            if lookup:
                                condition_q &= Q(
                                    **{f"{field_path}__{k}__{lookup}": op_val}
                                )
                    else:
                        condition_q &= Q(**{f"{field_path}__{k}": v})
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.debug(f"Failed to parse conditional filter: {e}")

        lookup_path = f"{field_path}__{target_field}"

        if cond_agg_filter.get("sum") is not None:
            annotation_name = f"{field_path.replace('__', '_')}_cond_sum"
            annotations[annotation_name] = Sum(lookup_path, filter=condition_q)

        if cond_agg_filter.get("avg") is not None:
            annotation_name = f"{field_path.replace('__', '_')}_cond_avg"
            annotations[annotation_name] = Avg(lookup_path, filter=condition_q)

        if cond_agg_filter.get("count") is not None:
            annotation_name = f"{field_path.replace('__', '_')}_cond_count"
            annotations[annotation_name] = Count(lookup_path, filter=condition_q)

        return annotations

    def _build_conditional_aggregation_q(
        self,
        field_path: str,
        cond_agg_filter: Dict[str, Any],
    ) -> Q:
        """Build Q object for conditional aggregation filters."""
        q = Q()

        for agg_type in ("sum", "avg", "count"):
            agg_value = cond_agg_filter.get(agg_type)
            if not isinstance(agg_value, dict):
                continue
            annotation_name = f"{field_path.replace('__', '_')}_cond_{agg_type}"
            q &= self._build_numeric_q(annotation_name, agg_value)

        return q

    # =========================================================================
    # Window Function Filter Methods
    # =========================================================================

    def prepare_queryset_for_window_filter(
        self,
        queryset: models.QuerySet,
        window_filter: Dict[str, Any],
    ) -> models.QuerySet:
        """Prepare queryset with window function annotation."""
        function_name = window_filter.get("function")
        if isinstance(function_name, str):
            function_name = function_name.lower()
        else:
            # Handle enum value
            function_name = getattr(function_name, "value", str(function_name)).lower()

        partition_by = window_filter.get("partition_by") or []
        order_by_fields = window_filter.get("order_by") or []

        # Build order_by expressions
        order_by_exprs = []
        for field in order_by_fields:
            if field.startswith("-"):
                order_by_exprs.append(F(field[1:]).desc())
            else:
                order_by_exprs.append(F(field).asc())

        # Build partition_by expressions
        partition_exprs = [F(field) for field in partition_by] if partition_by else None

        # Select window function
        window_func_map = {
            "rank": Rank,
            "dense_rank": DenseRank,
            "row_number": RowNumber,
            "percent_rank": PercentRank,
        }

        func_class = window_func_map.get(function_name, Rank)
        window_expr = Window(
            expression=func_class(),
            partition_by=partition_exprs,
            order_by=order_by_exprs,
        )

        queryset = queryset.annotate(_window_rank=window_expr)
        return queryset

    def _build_window_filter_q(
        self,
        window_filter: Dict[str, Any],
    ) -> Q:
        """Build Q object for window function filter."""
        q = Q()

        # Filter by rank value
        if window_filter.get("rank"):
            q &= self._build_numeric_q("_window_rank", window_filter["rank"])

        # Filter by percentile (for percent_rank)
        if window_filter.get("percentile"):
            q &= self._build_numeric_q("_window_rank", window_filter["percentile"])

        return q

    # =========================================================================
    # Subquery Filter Methods
    # =========================================================================

    def _build_subquery_filter_q(
        self,
        subquery_filter: Dict[str, Any],
        model: Type[models.Model],
    ) -> tuple[Q, Dict[str, Any]]:
        """Build Q object and annotations for subquery filter."""
        import json

        annotations = {}
        q = Q()

        relation_name = subquery_filter.get("relation")
        if not relation_name:
            return q, annotations

        order_by_fields = subquery_filter.get("order_by") or ["-pk"]
        target_field = subquery_filter.get("field") or "id"
        filter_json = subquery_filter.get("filter")

        try:
            # Get the related model
            relation_field = self._get_relation_field(model, relation_name)
            if relation_field is None:
                return q, annotations

            related_model = getattr(relation_field, "related_model", None)
            if related_model is None:
                return q, annotations

            # Find the FK field pointing back to parent
            fk_field = self._get_fk_to_parent(related_model, model)
            if not fk_field:
                return q, annotations

            # Build base subquery
            subquery_qs = related_model.objects.filter(**{fk_field: OuterRef("pk")})

            # Apply additional filter if provided
            if filter_json:
                try:
                    if isinstance(filter_json, str):
                        filter_dict = json.loads(filter_json)
                    else:
                        filter_dict = filter_json
                    for k, v in filter_dict.items():
                        if isinstance(v, dict):
                            for op, op_val in v.items():
                                lookup = self._get_lookup_for_operator(op)
                                if lookup == "neq":
                                    subquery_qs = subquery_qs.exclude(
                                        **{f"{k}__exact": op_val}
                                    )
                                elif lookup:
                                    subquery_qs = subquery_qs.filter(
                                        **{f"{k}__{lookup}": op_val}
                                    )
                        else:
                            subquery_qs = subquery_qs.filter(**{k: v})
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.debug(f"Failed to parse subquery filter: {e}")

            # Apply ordering and limit to first
            order_by_exprs = []
            for field in order_by_fields:
                if field.startswith("-"):
                    order_by_exprs.append(f"-{field[1:]}")
                else:
                    order_by_exprs.append(field)

            subquery_qs = subquery_qs.order_by(*order_by_exprs)

            # Create the subquery annotation
            annotation_name = f"_subquery_{relation_name}_{target_field}"
            annotations[annotation_name] = Subquery(
                subquery_qs.values(target_field)[:1]
            )

            # Build comparison Q object
            for op in ("eq", "neq", "gt", "gte", "lt", "lte", "is_null"):
                op_value = subquery_filter.get(op)
                if op_value is None:
                    continue

                if op == "eq":
                    q &= Q(**{annotation_name: op_value})
                elif op == "neq":
                    q &= ~Q(**{annotation_name: op_value})
                elif op == "is_null":
                    q &= Q(**{f"{annotation_name}__isnull": op_value})
                else:
                    q &= Q(**{f"{annotation_name}__{op}": op_value})

        except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Failed to build subquery filter: {e}")

        return q, annotations

    def _build_exists_filter_q(
        self,
        exists_filter: Dict[str, Any],
        model: Type[models.Model],
    ) -> Q:
        """Build Q object for exists filter."""
        import json

        q = Q()

        relation_name = exists_filter.get("relation")
        if not relation_name:
            return q

        should_exist = exists_filter.get("exists", True)
        filter_json = exists_filter.get("filter")

        try:
            # Get the related model
            relation_field = self._get_relation_field(model, relation_name)
            if relation_field is None:
                return q

            related_model = getattr(relation_field, "related_model", None)
            if related_model is None:
                return q

            # Find the FK field pointing back to parent
            fk_field = self._get_fk_to_parent(related_model, model)
            if not fk_field:
                return q

            # Build exists subquery
            subquery_qs = related_model.objects.filter(**{fk_field: OuterRef("pk")})

            # Apply filter condition if provided
            if filter_json:
                try:
                    if isinstance(filter_json, str):
                        filter_dict = json.loads(filter_json)
                    else:
                        filter_dict = filter_json
                    for k, v in filter_dict.items():
                        if isinstance(v, dict):
                            for op, op_val in v.items():
                                lookup = self._get_lookup_for_operator(op)
                                if lookup == "neq":
                                    subquery_qs = subquery_qs.exclude(
                                        **{f"{k}__exact": op_val}
                                    )
                                elif lookup:
                                    subquery_qs = subquery_qs.filter(
                                        **{f"{k}__{lookup}": op_val}
                                    )
                        else:
                            subquery_qs = subquery_qs.filter(**{k: v})
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.debug(f"Failed to parse exists filter: {e}")

            exists_expr = Exists(subquery_qs)

            if should_exist:
                q &= Q(exists_expr)
            else:
                q &= ~Q(exists_expr)

        except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Failed to build exists filter: {e}")

        return q

    # =========================================================================
    # Array Field Filter Methods
    # =========================================================================

    def _build_array_field_q(
        self,
        field_name: str,
        array_filter: Dict[str, Any],
    ) -> Q:
        """Build Q object for PostgreSQL ArrayField filters."""
        q = Q()

        if array_filter.get("contains"):
            q &= Q(**{f"{field_name}__contains": array_filter["contains"]})

        if array_filter.get("contained_by"):
            q &= Q(**{f"{field_name}__contained_by": array_filter["contained_by"]})

        if array_filter.get("overlaps"):
            q &= Q(**{f"{field_name}__overlap": array_filter["overlaps"]})

        if array_filter.get("is_null") is not None:
            q &= Q(**{f"{field_name}__isnull": array_filter["is_null"]})

        # Length filter requires annotation
        if array_filter.get("length"):
            # This would need annotation with array_length, handled separately
            pass

        return q

    # =========================================================================
    # F() Expression Comparison Filter Methods
    # =========================================================================

    def _build_field_compare_q(
        self,
        compare_filter: Dict[str, Any],
    ) -> Q:
        """Build Q object for F() expression field comparisons.

        Allows comparing one field to another, with optional multiplier/offset.
        Example: price > cost_price * 1.5 + 10
        """
        q = Q()

        left_field = compare_filter.get("left")
        operator = compare_filter.get("operator")
        right_field = compare_filter.get("right")

        if not left_field or not operator or not right_field:
            return q

        # Get operator value (handle enum)
        if hasattr(operator, "value"):
            operator = operator.value

        # Build the right-hand side F() expression
        right_expr = F(right_field)

        # Apply multiplier if provided
        multiplier = compare_filter.get("right_multiplier")
        if multiplier is not None:
            right_expr = right_expr * multiplier

        # Apply offset if provided
        offset = compare_filter.get("right_offset")
        if offset is not None:
            right_expr = right_expr + offset

        # Build the comparison Q object
        operator_map = {
            "eq": "exact",
            "neq": "exact",  # Will be negated
            "gt": "gt",
            "gte": "gte",
            "lt": "lt",
            "lte": "lte",
        }

        lookup = operator_map.get(operator)
        if not lookup:
            return q

        if operator == "neq":
            q = ~Q(**{f"{left_field}__{lookup}": right_expr})
        else:
            q = Q(**{f"{left_field}__{lookup}": right_expr})

        return q

    # =========================================================================
    # Date Truncation Filter Methods
    # =========================================================================

    def _build_date_trunc_filter_q(
        self,
        base_field: str,
        trunc_filter: Dict[str, Any],
    ) -> tuple[Q, Dict[str, Any]]:
        """Build Q object and annotations for date truncation filters.

        Allows filtering by truncated date parts (year, quarter, month, etc.).
        """
        from datetime import date

        q = Q()
        annotations: Dict[str, Any] = {}

        precision = trunc_filter.get("precision")
        if not precision:
            return q, annotations

        # Get precision value (handle enum)
        if hasattr(precision, "value"):
            precision = precision.value

        # Map precision to Trunc function
        trunc_functions = {
            "year": TruncYear,
            "quarter": TruncQuarter,
            "month": TruncMonth,
            "week": TruncWeek,
            "day": TruncDay,
            "hour": TruncHour,
            "minute": TruncMinute,
        }

        trunc_func = trunc_functions.get(precision)
        if not trunc_func:
            return q, annotations

        # Create annotation name
        annotation_name = f"_{base_field}_trunc_{precision}"
        annotations[annotation_name] = trunc_func(base_field)

        # Filter by specific value if provided
        if trunc_filter.get("value"):
            try:
                # Parse the ISO date string
                from dateutil.parser import parse as parse_date

                target_date = parse_date(trunc_filter["value"])
                q &= Q(**{annotation_name: target_date})
            except (ValueError, ImportError):
                # Fall back to simple string parsing for common formats
                try:
                    value_str = trunc_filter["value"]
                    if precision == "year":
                        q &= Q(**{f"{annotation_name}__year": int(value_str[:4])})
                    elif precision == "month":
                        parts = value_str.split("-")
                        if len(parts) >= 2:
                            q &= Q(**{f"{annotation_name}__year": int(parts[0])})
                            q &= Q(**{f"{annotation_name}__month": int(parts[1])})
                except (ValueError, IndexError):
                    pass

        # Filter by specific parts
        if trunc_filter.get("year") is not None:
            q &= Q(**{f"{annotation_name}__year": trunc_filter["year"]})

        if trunc_filter.get("quarter") is not None:
            # Django doesn't have quarter lookup, compute from month
            quarter = trunc_filter["quarter"]
            if 1 <= quarter <= 4:
                start_month = (quarter - 1) * 3 + 1
                end_month = quarter * 3
                q &= Q(**{f"{annotation_name}__month__gte": start_month})
                q &= Q(**{f"{annotation_name}__month__lte": end_month})

        if trunc_filter.get("month") is not None:
            q &= Q(**{f"{annotation_name}__month": trunc_filter["month"]})

        if trunc_filter.get("week") is not None:
            q &= Q(**{f"{annotation_name}__week": trunc_filter["week"]})

        # Handle this_period / last_period
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        now = timezone.now() if timezone.is_aware(timezone.now()) else datetime.now()

        if trunc_filter.get("this_period"):
            if precision == "year":
                q &= Q(**{f"{annotation_name}__year": today.year})
            elif precision == "quarter":
                current_quarter = (today.month - 1) // 3 + 1
                start_month = (current_quarter - 1) * 3 + 1
                end_month = current_quarter * 3
                q &= Q(**{f"{annotation_name}__year": today.year})
                q &= Q(**{f"{annotation_name}__month__gte": start_month})
                q &= Q(**{f"{annotation_name}__month__lte": end_month})
            elif precision == "month":
                q &= Q(**{f"{annotation_name}__year": today.year})
                q &= Q(**{f"{annotation_name}__month": today.month})
            elif precision == "week":
                q &= Q(**{f"{annotation_name}__year": today.year})
                q &= Q(**{f"{annotation_name}__week": today.isocalendar()[1]})
            elif precision == "day":
                q &= Q(**{annotation_name: trunc_func(now)})
            elif precision == "hour":
                q &= Q(**{annotation_name: trunc_func(now)})

        if trunc_filter.get("last_period"):
            if precision == "year":
                q &= Q(**{f"{annotation_name}__year": today.year - 1})
            elif precision == "quarter":
                current_quarter = (today.month - 1) // 3 + 1
                if current_quarter == 1:
                    last_quarter = 4
                    year = today.year - 1
                else:
                    last_quarter = current_quarter - 1
                    year = today.year
                start_month = (last_quarter - 1) * 3 + 1
                end_month = last_quarter * 3
                q &= Q(**{f"{annotation_name}__year": year})
                q &= Q(**{f"{annotation_name}__month__gte": start_month})
                q &= Q(**{f"{annotation_name}__month__lte": end_month})
            elif precision == "month":
                if today.month == 1:
                    q &= Q(**{f"{annotation_name}__year": today.year - 1})
                    q &= Q(**{f"{annotation_name}__month": 12})
                else:
                    q &= Q(**{f"{annotation_name}__year": today.year})
                    q &= Q(**{f"{annotation_name}__month": today.month - 1})
            elif precision == "week":
                last_week = today.isocalendar()[1] - 1
                if last_week == 0:
                    # First week of year, go to last week of previous year
                    q &= Q(**{f"{annotation_name}__year": today.year - 1})
                    q &= Q(**{f"{annotation_name}__week": 52})  # Simplified
                else:
                    q &= Q(**{f"{annotation_name}__year": today.year})
                    q &= Q(**{f"{annotation_name}__week": last_week})
            elif precision == "day":
                yesterday = today - timedelta(days=1)
                q &= Q(**{f"{base_field}__date": yesterday})

        return q, annotations

    # =========================================================================
    # Date Extraction Filter Methods
    # =========================================================================

    def _build_date_extract_filter_q(
        self,
        base_field: str,
        extract_filter: Dict[str, Any],
    ) -> tuple[Q, Dict[str, Any]]:
        """Build Q object and annotations for date extraction filters.

        Unlike truncation which rounds to period boundaries, extraction pulls
        out specific components like day_of_week, hour, quarter, etc.
        """
        q = Q()
        annotations: Dict[str, Any] = {}

        # Map filter keys to Extract functions
        extract_functions = {
            "year": ExtractYear,
            "month": ExtractMonth,
            "day": ExtractDay,
            "quarter": ExtractQuarter,
            "week": ExtractWeek,
            "day_of_week": ExtractWeekDay,
            "day_of_year": lambda f: ExtractDay(f),  # Will use custom annotation
            "iso_week_day": ExtractIsoWeekDay,
            "iso_year": ExtractIsoYear,
            "hour": ExtractHour,
            "minute": ExtractMinute,
            "second": ExtractSecond,
        }

        for extract_key, filter_value in extract_filter.items():
            if filter_value is None:
                continue

            # Get the extract function
            extract_func = extract_functions.get(extract_key)
            if not extract_func:
                continue

            # Create annotation name
            annotation_name = f"_{base_field}_extract_{extract_key}"

            # Handle special case for day_of_year (Django doesn't have ExtractDayOfYear)
            if extract_key == "day_of_year":
                # Use raw SQL for day of year extraction
                from django.db.models import Func, IntegerField as DjIntegerField

                class ExtractDayOfYear(Func):
                    function = "EXTRACT"
                    template = "%(function)s(DOY FROM %(expressions)s)"
                    output_field = DjIntegerField()

                annotations[annotation_name] = ExtractDayOfYear(base_field)
            else:
                annotations[annotation_name] = extract_func(base_field)

            # Build the Q object from the IntFilterInput
            extract_q = self._build_numeric_q(annotation_name, filter_value)
            if extract_q:
                q &= extract_q

        return q, annotations

    def _build_temporal_q(
        self,
        field_path: str,
        temporal_filter: str,
    ) -> Optional[Q]:
        """Build Q object for temporal filters."""
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )

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
            return Q(
                **{f"{field_path}__date__range": [past_month_start, past_month_end]}
            )

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

    def _get_relation_field(
        self, model: Type[models.Model], field_name: str
    ) -> Optional[models.Field]:
        """
        Get the relation field from model by name.

        Checks both forward relations and reverse relations.

        Args:
            model: Django model class
            field_name: Name of the relation field

        Returns:
            Django field instance or None if not found
        """
        try:
            return model._meta.get_field(field_name)
        except FieldDoesNotExist:
            pass

        # Check reverse relations by accessor name
        try:
            for rel in model._meta.related_objects:
                if rel.get_accessor_name() == field_name:
                    return rel
        except (AttributeError, TypeError):
            pass

        return None

    def _get_fk_to_parent(
        self, related_model: Type[models.Model], parent_model: Type[models.Model]
    ) -> Optional[str]:
        """
        Find the FK field in related_model pointing to parent_model.

        Args:
            related_model: The related model to search in
            parent_model: The parent model to find FK to

        Returns:
            Field name of the FK, or None if not found
        """
        try:
            for field in related_model._meta.get_fields():
                if (
                    hasattr(field, "related_model")
                    and field.related_model == parent_model
                ):
                    return field.name
        except (AttributeError, TypeError):
            pass

        return None

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
        annotations = self._collect_count_annotations(where_input, model=queryset.model)

        for annotation_name, field_name in annotations.items():
            queryset = queryset.annotate(**{annotation_name: Count(field_name)})

        return queryset

    def _collect_count_annotations(
        self,
        where_input: Dict[str, Any],
        annotations: Optional[Dict[str, str]] = None,
        model: Optional[Type[models.Model]] = None,
    ) -> Dict[str, str]:
        """Collect all count annotations needed."""
        if annotations is None:
            annotations = {}

        for key, value in where_input.items():
            if key == "AND" or key == "OR":
                if isinstance(value, list):
                    for item in value:
                        self._collect_count_annotations(item, annotations, model)
            elif key == "NOT":
                if isinstance(value, dict):
                    self._collect_count_annotations(value, annotations, model)
            elif key.endswith("_count") and isinstance(value, dict):
                # Check if this is a real field first (e.g. inventory_count)
                is_real_field = False
                if model:
                    try:
                        model._meta.get_field(key)
                        is_real_field = True
                    except FieldDoesNotExist:
                        pass

                if not is_real_field:
                    base_field = key[:-6]
                    annotation_name = f"{base_field}_count_annotation"
                    annotations[annotation_name] = base_field

        return annotations


# =============================================================================
# Quick Filter Support
# =============================================================================


class QuickFilterMixin:
    """
    Mixin for quick filter (multi-field search) functionality.

    Provides the ability to search across multiple text fields with a single
    search term, similar to a search box in a UI.
    """

    def _get_field_from_path(
        self, model: Type[models.Model], field_path: str
    ) -> Optional[models.Field]:
        """
        Get Django field from a field path (e.g., 'user__profile__name').

        Args:
            model: Starting model
            field_path: Field path with double underscores for relationships

        Returns:
            Django field instance or None if not found
        """
        try:
            current_model = model
            field_parts = field_path.split("__")

            for i, part in enumerate(field_parts):
                field = current_model._meta.get_field(part)

                if i == len(field_parts) - 1:
                    return field

                if hasattr(field, "related_model"):
                    current_model = field.related_model
                else:
                    return None

            return None
        except Exception:
            return None

    def get_default_quick_filter_fields(self, model: Type[models.Model]) -> List[str]:
        """
        Get default searchable fields for quick filter.

        Args:
            model: Django model to get searchable fields for

        Returns:
            List of field names suitable for quick search
        """
        searchable_fields = []

        for field in model._meta.get_fields():
            if hasattr(field, "name"):
                if isinstance(field, (models.CharField, models.TextField)):
                    # Skip very short fields and sensitive fields
                    if (
                        (
                            hasattr(field, "max_length")
                            and field.max_length
                            and field.max_length < 10
                        )
                        or "password" in field.name.lower()
                        or "token" in field.name.lower()
                        or "secret" in field.name.lower()
                    ):
                        continue
                    searchable_fields.append(field.name)
                elif isinstance(field, models.EmailField):
                    searchable_fields.append(field.name)

        return searchable_fields

    def build_quick_filter_q(
        self,
        model: Type[models.Model],
        search_value: str,
        quick_filter_fields: Optional[List[str]] = None,
    ) -> Q:
        """
        Build a Q object for quick filter search.

        Args:
            model: Django model to search
            search_value: Search term
            quick_filter_fields: Optional list of fields to search

        Returns:
            Django Q object for the search
        """
        if not search_value:
            return Q()

        if quick_filter_fields is None:
            quick_filter_fields = self.get_default_quick_filter_fields(model)

        q_objects = Q()
        for field_path in quick_filter_fields:
            try:
                field = self._get_field_from_path(model, field_path)
                if field:
                    if isinstance(
                        field, (models.CharField, models.TextField, models.EmailField)
                    ):
                        q_objects |= Q(**{f"{field_path}__icontains": search_value})
                    elif isinstance(
                        field,
                        (models.IntegerField, models.FloatField, models.DecimalField),
                    ):
                        try:
                            numeric_value = float(search_value)
                            q_objects |= Q(**{field_path: numeric_value})
                        except (ValueError, TypeError):
                            continue
                    elif isinstance(field, models.BooleanField):
                        if search_value.lower() in ["true", "1", "yes", "on"]:
                            q_objects |= Q(**{field_path: True})
                        elif search_value.lower() in ["false", "0", "no", "off"]:
                            q_objects |= Q(**{field_path: False})
            except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
                logger.debug(f"Error processing quick filter field {field_path}: {e}")
                continue

        return q_objects


# =============================================================================
# Include Filter Support
# =============================================================================


class IncludeFilterMixin:
    """
    Mixin for include filter (ID union) functionality.

    Allows including specific IDs in results regardless of other filters,
    useful for ensuring selected items always appear in results.
    """

    def apply_include_filter(
        self,
        queryset: models.QuerySet,
        include_ids: List[Any],
    ) -> models.QuerySet:
        """
        Apply include filter to union specified IDs into results.

        Args:
            queryset: The current filtered queryset
            include_ids: List of IDs to include

        Returns:
            Combined queryset with included IDs
        """
        if not include_ids:
            return queryset

        try:
            # Sanitize IDs
            sanitized_ids = []
            for v in include_ids:
                try:
                    if isinstance(v, str) and v.isdigit():
                        sanitized_ids.append(int(v))
                    else:
                        sanitized_ids.append(v)
                except (ValueError, TypeError):
                    sanitized_ids.append(v)

            model_cls = queryset.model

            # Build combined queryset
            combined_qs = model_cls.objects.filter(
                Q(pk__in=sanitized_ids) | Q(pk__in=queryset.values("pk"))
            ).distinct()

            # Preserve tenant filter if present
            tenant_filter = getattr(queryset, "_rail_tenant_filter", None)
            if tenant_filter:
                try:
                    tenant_path, tenant_id = tenant_filter
                    if tenant_path and tenant_id is not None:
                        combined_qs = combined_qs.filter(**{tenant_path: tenant_id})
                except (ValueError, TypeError, AttributeError):
                    pass

            # Deterministic ordering: included IDs first
            combined_qs = combined_qs.annotate(
                _include_priority=Case(
                    When(pk__in=sanitized_ids, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("_include_priority", "pk")

            return combined_qs

        except (FieldDoesNotExist, TypeError, ValueError, AttributeError) as e:
            logger.warning(f"Failed to apply include filter: {e}")
            return queryset


# =============================================================================
# Historical Model Support
# =============================================================================


class HistoricalModelMixin:
    """
    Mixin for django-simple-history model support.

    Provides special filters for historical models including
    instance filtering and history type filtering.
    """

    def is_historical_model(self, model: Type[models.Model]) -> bool:
        """Check if model is from django-simple-history."""
        try:
            name = getattr(model, "__name__", "")
            module = getattr(model, "__module__", "")
        except Exception:
            return False

        if name.startswith("Historical"):
            return True
        return "simple_history" in module

    def generate_historical_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """
        Generate filters specific to historical models.

        Args:
            model: Historical model class

        Returns:
            Dictionary of historical filter fields
        """
        filters = {}

        # Instance filter - filter by original instance IDs
        filters["instance_in"] = graphene.InputField(
            graphene.List(graphene.NonNull(graphene.ID)),
            description="Filter by original instance IDs",
        )

        # History type filter
        try:
            history_field = model._meta.get_field("history_type")
            choices = getattr(history_field, "choices", None)
            if choices:
                filters["history_type_in"] = graphene.InputField(
                    graphene.List(graphene.NonNull(graphene.String)),
                    description="Filter by history type (create, update, delete)",
                )
        except FieldDoesNotExist:
            pass

        return filters

    def build_historical_filter_q(
        self,
        filter_name: str,
        filter_value: Any,
    ) -> Q:
        """
        Build Q object for historical model filters.

        Args:
            filter_name: Name of the historical filter
            filter_value: Filter value

        Returns:
            Django Q object
        """
        if filter_name == "instance_in" and filter_value:
            return Q(id__in=filter_value)
        elif filter_name == "history_type_in" and filter_value:
            return Q(history_type__in=filter_value)
        return Q()


# =============================================================================
# GraphQLMeta Integration
# =============================================================================


class GraphQLMetaIntegrationMixin:
    """
    Mixin for GraphQLMeta integration.

    Reads filter configuration from model's GraphQLMeta class to
    customize filter generation.
    """

    def get_graphql_meta(self, model: Type[models.Model]) -> Optional[Any]:
        """Get GraphQLMeta for a model."""
        try:
            from ..core.meta import get_model_graphql_meta

            return get_model_graphql_meta(model)
        except ImportError:
            return None

    def apply_field_config_overrides(
        self,
        field_name: str,
        model: Type[models.Model],
    ) -> Optional[Dict[str, Any]]:
        """
        Get field-specific filter configuration from GraphQLMeta.

        Args:
            field_name: Name of the field
            model: Django model class

        Returns:
            Field configuration dictionary or None
        """
        graphql_meta = self.get_graphql_meta(model)
        if not graphql_meta:
            return None

        try:
            field_config = graphql_meta.filtering.fields.get(field_name)
            return field_config
        except AttributeError:
            return None

    def get_custom_filters(self, model: Type[models.Model]) -> Dict[str, Any]:
        """
        Get custom filters defined in GraphQLMeta.

        Args:
            model: Django model class

        Returns:
            Dictionary of custom filter definitions
        """
        graphql_meta = self.get_graphql_meta(model)
        if not graphql_meta:
            return {}

        try:
            if graphql_meta.custom_filters:
                return graphql_meta.get_custom_filters()
        except AttributeError:
            pass

        return {}

    def get_quick_filter_fields(self, model: Type[models.Model]) -> List[str]:
        """
        Get quick filter fields from GraphQLMeta or auto-detect.

        Args:
            model: Django model class

        Returns:
            List of field names for quick filter
        """
        graphql_meta = self.get_graphql_meta(model)
        if graphql_meta:
            try:
                quick_fields = list(getattr(graphql_meta, "quick_filter_fields", []))
                if quick_fields:
                    return quick_fields
            except (TypeError, AttributeError):
                pass

        # Fall back to auto-detection
        return QuickFilterMixin().get_default_quick_filter_fields(model)


# =============================================================================
# Schema Settings Integration
# =============================================================================


class SchemaSettingsMixin:
    """
    Mixin for schema settings integration.

    Checks if models/apps are excluded from the schema.
    """

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name

    def is_model_excluded(self, model: Type[models.Model]) -> bool:
        """
        Check if model is excluded from schema.

        Args:
            model: Django model class

        Returns:
            True if model should be excluded
        """
        if model is None or not hasattr(model, "_meta"):
            return False

        try:
            from ..core.settings import SchemaSettings

            settings = SchemaSettings.from_schema(self.schema_name)
        except (ImportError, AttributeError, KeyError):
            return False

        app_label = getattr(model._meta, "app_label", "")
        if app_label in (settings.excluded_apps or []):
            return True

        excluded_models = set(settings.excluded_models or [])
        if not excluded_models:
            return False

        model_name = getattr(model, "__name__", "")
        model_label = getattr(model._meta, "model_name", "")
        full_model_name = f"{app_label}.{model_name}" if app_label else model_name

        return (
            model_name in excluded_models
            or model_label in excluded_models
            or full_model_name in excluded_models
        )


# =============================================================================
# Performance Analysis
# =============================================================================


class PerformanceAnalyzer:
    """
    Analyzes filter queries for performance and suggests optimizations.

    Provides recommendations for select_related and prefetch_related
    based on the filters being applied.
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
    ):
        """Recursively analyze where input for performance implications."""
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


# =============================================================================
# Filter Metadata (for UI generation)
# =============================================================================


class FilterOperation:
    """
    Represents a single filter operation for a field.
    """

    def __init__(
        self,
        name: str,
        filter_type: str,
        lookup_expr: str = None,
        description: str = None,
        is_array: bool = False,
    ):
        self.name = name
        self.filter_type = filter_type
        self.lookup_expr = lookup_expr or "exact"
        self.description = description
        self.is_array = is_array

    def to_dict(self) -> Dict[str, Any]:
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
    """

    def __init__(
        self, field_name: str, field_type: str, operations: List[FilterOperation]
    ):
        self.field_name = field_name
        self.field_type = field_type
        self.operations = operations

    def to_dict(self) -> Dict[str, Any]:
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
    """

    def __init__(self, schema_name: str = "default"):
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
        """Generate filter operations for a field type."""
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
        return [
            FilterOperation("eq", "Boolean", "exact", f"Equal to"),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_choice_operations(self, field_name: str) -> List[FilterOperation]:
        return [
            FilterOperation("eq", "String", "exact", f"Exact choice"),
            FilterOperation("in", "StringList", "in", f"In choices", is_array=True),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_fk_operations(self, field_name: str) -> List[FilterOperation]:
        return [
            FilterOperation("eq", "ID", "exact", f"Exact ID"),
            FilterOperation("in", "IDList", "in", f"In IDs", is_array=True),
            FilterOperation("is_null", "Boolean", "isnull", f"Is null"),
        ]

    def _get_m2m_operations(self, field_name: str) -> List[FilterOperation]:
        return [
            FilterOperation("eq", "ID", "exact", f"Has ID"),
            FilterOperation("in", "IDList", "in", f"Has any of IDs", is_array=True),
            FilterOperation("is_null", "Boolean", "isnull", f"Has none"),
            FilterOperation("count_eq", "Int", "count", f"Count equals"),
            FilterOperation("count_gt", "Int", "count_gt", f"Count greater than"),
            FilterOperation("count_lt", "Int", "count_lt", f"Count less than"),
        ]


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
        schema_name=to_camel_case(schema_name),
    )
    return generator.generate_where_input(model)


def apply_where_filter(
    queryset: models.QuerySet,
    where_input: Dict[str, Any],
    schema_name: str = "default",
) -> models.QuerySet:
    """
    Apply a where filter to a queryset.

    Args:
        queryset: Django queryset
        where_input: Where input dictionary

    Returns:
        Filtered queryset
    """
    applicator = NestedFilterApplicator(schema_name=to_camel_case(schema_name))

    # Prepare count annotations if needed
    queryset = applicator.prepare_queryset_for_count_filters(queryset, where_input)

    return applicator.apply_where_filter(queryset, where_input)


# =============================================================================
# Legacy Compatibility Layer
# =============================================================================


class AdvancedFilterGenerator(
    SchemaSettingsMixin, HistoricalModelMixin, GraphQLMetaIntegrationMixin
):
    """
    Legacy-compatible filter generator that provides the same API as the old
    filters.py AdvancedFilterGenerator, but uses the new nested filter system.

    This class is provided for backwards compatibility with code that imports
    AdvancedFilterGenerator. New code should use NestedFilterInputGenerator directly.
    """

    def __init__(
        self,
        max_nested_depth: int = DEFAULT_MAX_NESTED_DEPTH,
        enable_nested_filters: bool = True,
        schema_name: Optional[str] = None,
    ):
        self.max_nested_depth = min(max_nested_depth, MAX_ALLOWED_NESTED_DEPTH)
        self.enable_nested_filters = enable_nested_filters
        self.schema_name = schema_name or "default"
        self._filter_cache: Dict[str, Any] = {}
        self._visited_models: Set = set()

        # Create the nested generator
        self._nested_generator = NestedFilterInputGenerator(
            max_nested_depth=self.max_nested_depth,
            enable_count_filters=True,
            schema_name=self.schema_name,
        )
        self._filter_applicator = NestedFilterApplicator(schema_name=self.schema_name)
        self._metadata_generator = FilterMetadataGenerator(schema_name=self.schema_name)

    def generate_filter_set(
        self, model: Type[models.Model], current_depth: int = 0
    ) -> Type:
        """
        Generate a FilterSet-like class for the given Django model.

        For backwards compatibility, this returns a class that can be used
        with django-filter's DjangoFilterConnectionField.

        Args:
            model: Django model to generate filters for
            current_depth: Current nesting depth

        Returns:
            FilterSet class (uses django_filters if available)
        """
        cache_key = f"{model.__name__}_{current_depth}"

        if cache_key in self._filter_cache:
            return self._filter_cache[cache_key]

        # Try to create a real django-filter FilterSet for Relay compatibility
        try:
            import django_filters
            from django_filters import FilterSet

            # Generate basic filters for the model
            filters = {}
            for field in model._meta.get_fields():
                if not hasattr(field, "name"):
                    continue

                field_name = field.name
                if field_name in ("polymorphic_ctype",) or "_ptr" in field_name:
                    continue

                # Add basic filters based on field type
                if isinstance(field, (models.CharField, models.TextField)):
                    filters[field_name] = django_filters.CharFilter(
                        field_name=field_name,
                        lookup_expr="icontains",
                    )
                    filters[f"{field_name}__exact"] = django_filters.CharFilter(
                        field_name=field_name,
                        lookup_expr="exact",
                    )
                elif isinstance(
                    field, (models.IntegerField, models.FloatField, models.DecimalField)
                ):
                    filters[field_name] = django_filters.NumberFilter(
                        field_name=field_name
                    )
                    filters[f"{field_name}__gt"] = django_filters.NumberFilter(
                        field_name=field_name, lookup_expr="gt"
                    )
                    filters[f"{field_name}__lt"] = django_filters.NumberFilter(
                        field_name=field_name, lookup_expr="lt"
                    )
                elif isinstance(field, (models.DateField, models.DateTimeField)):
                    filters[field_name] = django_filters.DateFilter(
                        field_name=field_name
                    )
                    filters[f"{field_name}__gt"] = django_filters.DateFilter(
                        field_name=field_name, lookup_expr="gt"
                    )
                    filters[f"{field_name}__lt"] = django_filters.DateFilter(
                        field_name=field_name, lookup_expr="lt"
                    )
                elif isinstance(field, models.BooleanField):
                    filters[field_name] = django_filters.BooleanFilter(
                        field_name=field_name
                    )
                elif isinstance(field, models.ForeignKey):
                    filters[field_name] = django_filters.NumberFilter(
                        field_name=field_name
                    )

            # Add quick filter for text search across multiple fields
            # This enables the quick=... top-level argument in queries
            text_fields = [
                f.name
                for f in model._meta.get_fields()
                if hasattr(f, "name")
                and isinstance(f, (models.CharField, models.TextField))
                and f.name not in ("polymorphic_ctype",)
                and "_ptr" not in f.name
            ]
            if text_fields:
                filters["quick"] = django_filters.CharFilter(
                    method="filter_quick", help_text="Quick search across text fields"
                )

            def make_filter_quick_method(text_fields_list):
                """Create a filter_quick method that searches across text fields."""

                def filter_quick(self, queryset, name, value):
                    if not value:
                        return queryset
                    from django.db.models import Q

                    q_objects = Q()
                    for field_name in text_fields_list:
                        q_objects |= Q(**{f"{field_name}__icontains": value})
                    return queryset.filter(q_objects)

                return filter_quick

            filter_set_class = type(
                f"{model.__name__}FilterSet",
                (FilterSet,),
                {
                    **filters,
                    "filter_quick": make_filter_quick_method(text_fields),
                    "Meta": type(
                        "Meta",
                        (),
                        {
                            "model": model,
                            "fields": list(filters.keys()),
                            "strict": False,
                        },
                    ),
                },
            )

            self._filter_cache[cache_key] = filter_set_class
            return filter_set_class

        except ImportError:
            # django-filter not available, return a placeholder
            logger.warning(
                "django-filter not available, returning placeholder FilterSet"
            )
            return type(
                f"{model.__name__}FilterSet",
                (),
                {"Meta": type("Meta", (), {"model": model})},
            )

    def generate_where_input(
        self, model: Type[models.Model]
    ) -> Type[graphene.InputObjectType]:
        """
        Generate a WhereInput type for GraphQL filtering.

        Args:
            model: Django model class

        Returns:
            GraphQL InputObjectType for filtering
        """
        return self._nested_generator.generate_where_input(model)

    def apply_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
        model: Optional[Type[models.Model]] = None,
    ) -> models.QuerySet:
        """
        Apply filters to a queryset.

        Args:
            queryset: Django queryset
            where_input: Filter input dictionary
            model: Optional model class

        Returns:
            Filtered queryset
        """
        return self._filter_applicator.apply_where_filter(queryset, where_input, model)

    def analyze_query_performance(
        self, model: Type[models.Model], filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze the performance implications of applied filters.

        Args:
            model: Django model being filtered
            filters: Dictionary of applied filters

        Returns:
            Performance analysis dictionary
        """
        analyzer = PerformanceAnalyzer()
        return analyzer.analyze_query_performance(model, filters)

    def get_optimized_queryset(
        self,
        model: Type[models.Model],
        filters: Dict[str, Any],
        base_queryset: Optional[models.QuerySet] = None,
    ) -> models.QuerySet:
        """
        Get an optimized queryset based on the filters being applied.

        Args:
            model: Django model
            filters: Dictionary of filters
            base_queryset: Optional base queryset

        Returns:
            Optimized queryset
        """
        analyzer = PerformanceAnalyzer()
        return analyzer.get_optimized_queryset(model, filters, base_queryset)


class EnhancedFilterGenerator:
    """
    Legacy-compatible enhanced filter generator for metadata generation.

    This class provides the same API as the old filters.py EnhancedFilterGenerator,
    but uses the new FilterMetadataGenerator under the hood.
    """

    def __init__(
        self,
        max_nested_depth: int = DEFAULT_MAX_NESTED_DEPTH,
        enable_nested_filters: bool = True,
        schema_name: Optional[str] = None,
        enable_quick_filter: bool = False,
    ):
        self.max_nested_depth = min(max_nested_depth, MAX_ALLOWED_NESTED_DEPTH)
        self.enable_nested_filters = enable_nested_filters
        self.schema_name = schema_name or "default"
        self.enable_quick_filter = enable_quick_filter
        self._metadata_generator = FilterMetadataGenerator(schema_name=self.schema_name)
        self._grouped_filter_cache: Dict[
            Type[models.Model], List[GroupedFieldFilter]
        ] = {}

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
        return self._metadata_generator.get_grouped_filters(model)

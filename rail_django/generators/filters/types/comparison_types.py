"""
Comparison and Search Filter Input Types for GraphQL.

This module provides GraphQL InputObjectTypes for advanced comparison operations,
including subquery filters, existence checks, field-to-field comparisons,
date truncation/extraction filters, and full-text search.
"""

from __future__ import annotations

import graphene

from .base_types import IntFilterInput, FloatFilterInput


class SubqueryFilterInput(graphene.InputObjectType):
    """
    Filter input for correlated subquery filters.

    Enables filtering by values from the latest/first related record. This is
    useful for queries like "customers whose most recent order was placed today"
    or "products with highest rated review >= 4.5".

    Example GraphQL query:
        query {
          customers(where: {
            _subquery: {
              relation: "orders"
              orderBy: ["-created_at"]
              field: "status"
              eq: "\\"completed\\""
            }
          }) {
            id
            name
          }
        }
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

    More efficient than _some for simple existence checks. Uses SQL EXISTS
    subquery which is optimized by most databases.

    Example GraphQL query:
        query {
          products(where: {
            _exists: {
              relation: "reviews"
              filter: "{\\"rating\\": {\\"gte\\": 4}}"
              exists: true
            }
          }) {
            id
            name
          }
        }
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


class CompareOperatorEnum(graphene.Enum):
    """
    Comparison operators for field-to-field comparisons.

    These operators are used with FieldCompareFilterInput to compare
    two fields from the same record.
    """

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class FieldCompareFilterInput(graphene.InputObjectType):
    """
    Filter input for comparing fields to each other using F() expressions.

    Enables queries like "products where price > cost_price" or
    "orders where updated_at > created_at + 1 day".

    Example GraphQL query:
        query {
          products(where: {
            _fieldCompare: {
              left: "sale_price"
              operator: LT
              right: "original_price"
              rightMultiplier: 0.5
            }
          }) {
            id
            name
            sale_price
            original_price
          }
        }
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


class DateTruncPrecisionEnum(graphene.Enum):
    """
    Date truncation precision levels.

    These precision levels are used with DateTruncFilterInput to truncate
    datetime values to specific boundaries for comparison.
    """

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

    Enables filtering by truncated date parts. Truncation rounds dates down
    to the specified precision boundary, useful for period-based queries
    like "all orders in Q1 2024" or "all sessions this month".

    Example GraphQL query:
        query {
          orders(where: {
            created_at_trunc: {
              precision: QUARTER
              year: 2024
              quarter: 1
            }
          }) {
            id
            total
          }
        }
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

    Example GraphQL query:
        query {
          orders(where: {
            created_at_extract: {
              dayOfWeek: { eq: 6 }
              hour: { gte: 9, lte: 17 }
            }
          }) {
            id
            created_at
          }
        }
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
    """
    Supported full-text search query modes.

    Different search modes provide varying levels of flexibility and
    performance for text search operations.
    """

    PLAIN = "plain"
    PHRASE = "phrase"
    WEBSEARCH = "websearch"
    RAW = "raw"


class FullTextSearchInput(graphene.InputObjectType):
    """
    Full-text search configuration.

    Enables powerful text search capabilities using database full-text search
    features. Supports PostgreSQL's built-in search and can be extended for
    other databases.

    Example GraphQL query:
        query {
          products(where: {
            _search: {
              query: "wireless bluetooth headphones"
              fields: ["name", "description", "category__name"]
              searchType: WEBSEARCH
              rankThreshold: 0.1
            }
          }) {
            id
            name
            description
          }
        }
    """

    query = graphene.String(required=True, description="Search query")
    fields = graphene.List(
        graphene.NonNull(graphene.String),
        description="Fields to search (supports relations: 'author__name')",
    )
    config = graphene.String(description="Text search configuration (Postgres only)")
    rank_threshold = graphene.Float(
        name="rankThreshold",
        description="Minimum search rank (0.0-1.0)",
    )
    search_type = graphene.Field(
        lambda: FullTextSearchTypeEnum,
        name="searchType",
        description="Search type: plain, phrase, websearch, raw",
        default_value=FullTextSearchTypeEnum.WEBSEARCH,
    )


__all__ = [
    "SubqueryFilterInput",
    "ExistsFilterInput",
    "CompareOperatorEnum",
    "FieldCompareFilterInput",
    "DateTruncPrecisionEnum",
    "DateTruncFilterInput",
    "ExtractDateFilterInput",
    "FullTextSearchTypeEnum",
    "FullTextSearchInput",
]

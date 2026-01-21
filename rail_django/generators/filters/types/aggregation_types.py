"""
Aggregation Filter Input Types for GraphQL.

This module provides GraphQL InputObjectTypes for aggregation-based filtering,
including SUM, AVG, MIN, MAX, COUNT operations on related objects, conditional
aggregations, and window function filters.
"""

from __future__ import annotations

import graphene

from .base_types import IntFilterInput, FloatFilterInput


class AggregationFilterInput(graphene.InputObjectType):
    """
    Filter input for aggregated values on related objects.

    Supports SUM, AVG, MIN, MAX, COUNT, and COUNT_DISTINCT on a selected field.
    Enables queries like "customers with total orders sum > 1000" or
    "products with average rating >= 4.5".

    Example GraphQL query:
        query {
          customers(where: {
            orders_aggregate: {
              field: "total"
              sum: { gte: 1000 }
            }
          }) {
            id
            name
          }
        }
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

    Counts or sums only records matching a specific condition. This is useful
    for complex analytics queries like "customers with more than 5 completed orders"
    or "products with total value of discounted items > 500".

    Example GraphQL query:
        query {
          customers(where: {
            orders_conditional_aggregate: {
              field: "total"
              filter: "{\\"status\\": \\"completed\\"}"
              count: { gte: 5 }
            }
          }) {
            id
            name
          }
        }
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
    """
    Supported window function types.

    Window functions perform calculations across a set of table rows that are
    related to the current row. These are useful for ranking, percentile, and
    relative position queries.
    """

    RANK = "rank"
    DENSE_RANK = "dense_rank"
    ROW_NUMBER = "row_number"
    PERCENT_RANK = "percent_rank"


class WindowFilterInput(graphene.InputObjectType):
    """
    Filter input for window function filters.

    Enables filtering by ranking, percentile, or row number within partitions.
    Useful for queries like "top 3 products in each category" or
    "employees in the top 10% salary within their department".

    Example GraphQL query:
        query {
          products(where: {
            _window: {
              function: RANK
              partitionBy: ["category_id"]
              orderBy: ["-sales_count"]
              rank: { lte: 3 }
            }
          }) {
            id
            name
            category { name }
          }
        }
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


__all__ = [
    "AggregationFilterInput",
    "ConditionalAggregationFilterInput",
    "WindowFunctionEnum",
    "WindowFilterInput",
]

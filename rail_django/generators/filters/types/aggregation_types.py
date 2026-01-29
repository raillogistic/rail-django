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

    field = graphene.String(required=True, description="Champ à agréger")
    sum = graphene.InputField(FloatFilterInput, description="Filtrer par SOMME")
    avg = graphene.InputField(FloatFilterInput, description="Filtrer par MOYENNE")
    min = graphene.InputField(FloatFilterInput, description="Filtrer par MIN")
    max = graphene.InputField(FloatFilterInput, description="Filtrer par MAX")
    count = graphene.InputField(IntFilterInput, description="Filtrer par COMPTE")
    count_distinct = graphene.InputField(
        IntFilterInput,
        name="countDistinct",
        description="Filtrer par COMPTE de valeurs distinctes",
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

    field = graphene.String(required=True, description="Champ à agréger")
    filter = graphene.Argument(
        lambda: graphene.JSONString,
        description="Condition de filtrage pour les enregistrements à inclure dans l'agrégation (JSON)",
    )
    sum = graphene.InputField(FloatFilterInput, description="Filtrer par SOMME conditionnelle")
    avg = graphene.InputField(FloatFilterInput, description="Filtrer par MOYENNE conditionnelle")
    count = graphene.InputField(
        IntFilterInput, description="Filtrer par COMPTE conditionnel"
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
        description="Fonction de fenêtre à utiliser: rank, dense_rank, row_number, percent_rank",
    )
    partition_by = graphene.List(
        graphene.NonNull(graphene.String),
        name="partitionBy",
        description="Champs pour le partitionnement",
    )
    order_by = graphene.List(
        graphene.NonNull(graphene.String),
        required=True,
        name="orderBy",
        description="Champs pour trier au sein de la partition (préfixer avec '-' pour descendant)",
    )
    # Filter conditions
    rank = graphene.InputField(IntFilterInput, description="Filtrer par valeur de rang")
    percentile = graphene.InputField(
        FloatFilterInput, description="Filtrer par percentile (0.0-1.0)"
    )


__all__ = [
    "AggregationFilterInput",
    "ConditionalAggregationFilterInput",
    "WindowFunctionEnum",
    "WindowFilterInput",
]

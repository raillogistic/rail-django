"""
Base Filter Input Types for GraphQL.

This module provides the fundamental typed GraphQL InputObjectTypes for filtering,
including string, numeric, boolean, ID, and UUID filter inputs.
"""

from __future__ import annotations

import graphene


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


__all__ = [
    "StringFilterInput",
    "IntFilterInput",
    "FloatFilterInput",
    "BooleanFilterInput",
    "IDFilterInput",
    "UUIDFilterInput",
]

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

    eq = graphene.String(description="Correspondance exacte")
    neq = graphene.String(description="Différent de")
    contains = graphene.String(description="Contient (sensible à la casse)")
    icontains = graphene.String(description="Contient (insensible à la casse)")
    starts_with = graphene.String(
        name="startsWith", description="Commence par (sensible à la casse)"
    )
    istarts_with = graphene.String(
        name="istartsWith", description="Commence par (insensible à la casse)"
    )
    ends_with = graphene.String(
        name="endsWith", description="Se termine par (sensible à la casse)"
    )
    iends_with = graphene.String(
        name="iendsWith", description="Se termine par (insensible à la casse)"
    )
    in_ = graphene.List(
        graphene.NonNull(graphene.String), name="in", description="Dans la liste"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.String), name="notIn", description="Pas dans la liste"
    )
    is_null = graphene.Boolean(name="isNull", description="Est nul")
    regex = graphene.String(description="Correspondance Regex (sensible à la casse)")
    iregex = graphene.String(description="Correspondance Regex (insensible à la casse)")


class IntFilterInput(graphene.InputObjectType):
    """
    Filter input for integer fields.

    Supports numeric comparisons and range operations.
    """

    eq = graphene.Int(description="Égal à")
    neq = graphene.Int(description="Différent de")
    gt = graphene.Int(description="Supérieur à")
    gte = graphene.Int(description="Supérieur ou égal à")
    lt = graphene.Int(description="Inférieur à")
    lte = graphene.Int(description="Inférieur ou égal à")
    in_ = graphene.List(
        graphene.NonNull(graphene.Int), name="in", description="Dans la liste"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.Int), name="notIn", description="Pas dans la liste"
    )
    between = graphene.List(graphene.Int, description="Entre [min, max] inclus")
    is_null = graphene.Boolean(name="isNull", description="Est nul")


class FloatFilterInput(graphene.InputObjectType):
    """
    Filter input for float/decimal fields.

    Supports numeric comparisons and range operations.
    """

    eq = graphene.Float(description="Égal à")
    neq = graphene.Float(description="Différent de")
    gt = graphene.Float(description="Supérieur à")
    gte = graphene.Float(description="Supérieur ou égal à")
    lt = graphene.Float(description="Inférieur à")
    lte = graphene.Float(description="Inférieur ou égal à")
    in_ = graphene.List(
        graphene.NonNull(graphene.Float), name="in", description="Dans la liste"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.Float), name="notIn", description="Pas dans la liste"
    )
    between = graphene.List(graphene.Float, description="Entre [min, max] inclus")
    is_null = graphene.Boolean(name="isNull", description="Est nul")


class BooleanFilterInput(graphene.InputObjectType):
    """
    Filter input for boolean fields.
    """

    eq = graphene.Boolean(description="Égal à")
    is_null = graphene.Boolean(name="isNull", description="Est nul")


class IDFilterInput(graphene.InputObjectType):
    """
    Filter input for ID/primary key fields.
    """

    eq = graphene.ID(description="Égal à")
    neq = graphene.ID(description="Différent de")
    in_ = graphene.List(graphene.NonNull(graphene.ID), name="in", description="Dans la liste")
    not_in = graphene.List(
        graphene.NonNull(graphene.ID), name="notIn", description="Pas dans la liste"
    )
    is_null = graphene.Boolean(name="isNull", description="Est nul")


class UUIDFilterInput(graphene.InputObjectType):
    """
    Filter input for UUID fields.
    """

    eq = graphene.String(description="Égal à")
    neq = graphene.String(description="Différent de")
    in_ = graphene.List(
        graphene.NonNull(graphene.String), name="in", description="Dans la liste"
    )
    not_in = graphene.List(
        graphene.NonNull(graphene.String), name="notIn", description="Pas dans la liste"
    )
    is_null = graphene.Boolean(name="isNull", description="Est nul")


__all__ = [
    "StringFilterInput",
    "IntFilterInput",
    "FloatFilterInput",
    "BooleanFilterInput",
    "IDFilterInput",
    "UUIDFilterInput",
]

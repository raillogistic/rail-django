"""
Advanced Filter Input Types for GraphQL.

This module provides specialized GraphQL InputObjectTypes for filtering
JSON fields, array fields (PostgreSQL), and count-based filtering on relationships.
"""

from __future__ import annotations

import graphene

from .base_types import IntFilterInput


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


__all__ = [
    "JSONFilterInput",
    "ArrayFilterInput",
    "CountFilterInput",
]

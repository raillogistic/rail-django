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

    eq = graphene.JSONString(description="Correspondance JSON exacte")
    is_null = graphene.Boolean(name="isNull", description="Est nul")
    has_key = graphene.String(name="hasKey", description="A la clé")
    has_keys = graphene.List(
        graphene.NonNull(graphene.String), name="hasKeys", description="A toutes les clés"
    )
    has_any_keys = graphene.List(
        graphene.NonNull(graphene.String),
        name="hasAnyKeys",
        description="A n'importe quelle clé",
    )


class ArrayFilterInput(graphene.InputObjectType):
    """
    Filter input for PostgreSQL ArrayField.

    Supports contains, overlap, contained_by, and length operations.
    """

    contains = graphene.List(
        graphene.NonNull(graphene.String),
        description="Le tableau contient toutes ces valeurs",
    )
    contained_by = graphene.List(
        graphene.NonNull(graphene.String),
        description="Le tableau est contenu par ces valeurs",
    )
    overlaps = graphene.List(
        graphene.NonNull(graphene.String),
        name="overlaps",
        description="Le tableau chevauche n'importe laquelle de ces valeurs",
    )
    length = graphene.InputField(IntFilterInput, description="Filtrer par longueur du tableau")
    is_null = graphene.Boolean(name="isNull", description="Le tableau est nul")


class CountFilterInput(graphene.InputObjectType):
    """
    Filter input for count-based filtering on relationships.

    Used for filtering by the count of related objects.
    """

    eq = graphene.Int(description="Compte égal à")
    neq = graphene.Int(description="Compte différent de")
    gt = graphene.Int(description="Compte supérieur à")
    gte = graphene.Int(description="Compte supérieur ou égal à")
    lt = graphene.Int(description="Compte inférieur à")
    lte = graphene.Int(description="Compte inférieur ou égal à")


__all__ = [
    "JSONFilterInput",
    "ArrayFilterInput",
    "CountFilterInput",
]

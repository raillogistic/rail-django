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

    relation = graphene.String(required=True, description="Nom du champ lié")
    order_by = graphene.List(
        graphene.NonNull(graphene.String),
        name="orderBy",
        description="Champs de tri pour déterminer quel enregistrement lié utiliser (préfixer avec '-' pour descendant)",
    )
    filter = graphene.Argument(
        lambda: graphene.JSONString,
        description="Filtre supplémentaire sur les enregistrements liés (JSON)",
    )
    field = graphene.String(
        required=True, description="Champ de l'enregistrement lié à comparer"
    )
    # Comparison conditions - apply to the subquery result
    # Using JSONString for flexibility since we don't know the field type
    eq = graphene.JSONString(description="Résultat de la sous-requête égal à (valeur en JSON)")
    neq = graphene.JSONString(description="Résultat de la sous-requête différent de (valeur en JSON)")
    gt = graphene.Float(description="Résultat de la sous-requête supérieur à")
    gte = graphene.Float(description="Résultat de la sous-requête supérieur ou égal à")
    lt = graphene.Float(description="Résultat de la sous-requête inférieur à")
    lte = graphene.Float(description="Résultat de la sous-requête inférieur ou égal à")
    is_null = graphene.Boolean(name="isNull", description="Le résultat de la sous-requête est nul")


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

    relation = graphene.String(required=True, description="Nom du champ lié")
    filter = graphene.Argument(
        lambda: graphene.JSONString,
        description="Condition de filtrage pour les enregistrements liés (JSON)",
    )
    exists = graphene.Boolean(
        default_value=True,
        description="Vrai pour vérifier l'existence, Faux pour vérifier la non-existence",
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
        description="Nom du champ de gauche à comparer",
    )
    operator = graphene.Field(
        CompareOperatorEnum,
        required=True,
        description="Opérateur de comparaison : eq, neq, gt, gte, lt, lte",
    )
    right = graphene.String(
        required=True,
        description="Nom du champ de droite à comparer",
    )
    right_multiplier = graphene.Float(
        name="rightMultiplier",
        description="Multiplicateur optionnel pour le champ de droite (ex: 1.5 pour droite * 1.5)",
    )
    right_offset = graphene.Float(
        name="rightOffset",
        description="Décalage optionnel à ajouter au champ de droite (ex: 10 pour droite + 10)",
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
        description="Précision de troncature : année, trimestre, mois, semaine, jour, heure, minute",
    )
    # Filter by specific value
    value = graphene.String(
        description="Valeur de date à faire correspondre (format ISO : 2024-01-01 ou 2024-03 pour le mois)",
    )
    year = graphene.Int(description="Filtrer par année")
    quarter = graphene.Int(description="Filtrer par trimestre (1-4)")
    month = graphene.Int(description="Filtrer par mois (1-12)")
    week = graphene.Int(description="Filtrer par numéro de semaine (1-53)")
    # Relative period filters
    this_period = graphene.Boolean(
        name="thisPeriod",
        description="Filtrer par la période actuelle (cette année/trimestre/mois/semaine/jour)",
    )
    last_period = graphene.Boolean(
        name="lastPeriod",
        description="Filtrer par la période précédente (année/trimestre/mois/semaine/jour dernier)",
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
        description="Filtrer par année (ex: 2024)",
    )
    month = graphene.InputField(
        IntFilterInput,
        description="Filtrer par mois (1-12)",
    )
    day = graphene.InputField(
        IntFilterInput,
        description="Filtrer par jour du mois (1-31)",
    )
    quarter = graphene.InputField(
        IntFilterInput,
        description="Filtrer par trimestre (1-4)",
    )
    week = graphene.InputField(
        IntFilterInput,
        description="Filtrer par numéro de semaine ISO (1-53)",
    )
    day_of_week = graphene.InputField(
        IntFilterInput,
        name="dayOfWeek",
        description="Filtrer par jour de la semaine (1=Dimanche, 7=Samedi)",
    )
    day_of_year = graphene.InputField(
        IntFilterInput,
        name="dayOfYear",
        description="Filtrer par jour de l'année (1-366)",
    )
    iso_week_day = graphene.InputField(
        IntFilterInput,
        name="isoWeekDay",
        description="Filtrer par jour de semaine ISO (1=Lundi, 7=Dimanche)",
    )
    iso_year = graphene.InputField(
        IntFilterInput,
        name="isoYear",
        description="Filtrer par année de numérotation de semaine ISO",
    )
    hour = graphene.InputField(
        IntFilterInput,
        description="Filtrer par heure (0-23)",
    )
    minute = graphene.InputField(
        IntFilterInput,
        description="Filtrer par minute (0-59)",
    )
    second = graphene.InputField(
        IntFilterInput,
        description="Filtrer par seconde (0-59)",
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

    query = graphene.String(required=True, description="Requête de recherche")
    fields = graphene.List(
        graphene.NonNull(graphene.String),
        description="Champs à rechercher (supporte les relations : 'auteur__nom')",
    )
    config = graphene.String(description="Configuration de la recherche textuelle (Postgres uniquement)")
    rank_threshold = graphene.Float(
        name="rankThreshold",
        description="Rang de recherche minimum (0.0-1.0)",
    )
    search_type = graphene.Field(
        lambda: FullTextSearchTypeEnum,
        name="searchType",
        description="Type de recherche : plain, phrase, websearch, raw",
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

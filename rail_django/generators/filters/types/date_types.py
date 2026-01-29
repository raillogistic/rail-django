"""
Date and DateTime Filter Input Types for GraphQL.

This module provides typed GraphQL InputObjectTypes for filtering date
and datetime fields, including temporal convenience filters.
"""

from __future__ import annotations

import graphene


class DateFilterInput(graphene.InputObjectType):
    """
    Filter input for date fields.

    Supports date comparisons, ranges, and convenient temporal filters.
    """

    eq = graphene.Date(description="Égal à")
    neq = graphene.Date(description="Différent de")
    gt = graphene.Date(description="Après la date")
    gte = graphene.Date(description="Le ou après la date")
    lt = graphene.Date(description="Avant la date")
    lte = graphene.Date(description="Le ou avant la date")
    between = graphene.List(graphene.Date, description="Entre [début, fin] inclus")
    is_null = graphene.Boolean(name="isNull", description="Est nul")
    # Temporal convenience filters
    year = graphene.Int(description="Filtrer par année")
    month = graphene.Int(description="Filtrer par mois (1-12)")
    day = graphene.Int(description="Filtrer par jour du mois")
    week_day = graphene.Int(
        name="weekDay", description="Filtrer par jour de la semaine (1=Dimanche, 7=Samedi)"
    )
    # Relative date filters
    today = graphene.Boolean(description="Est aujourd'hui")
    yesterday = graphene.Boolean(description="Est hier")
    this_week = graphene.Boolean(name="thisWeek", description="Est cette semaine")
    past_week = graphene.Boolean(name="pastWeek", description="Est la semaine dernière")
    this_month = graphene.Boolean(name="thisMonth", description="Est ce mois-ci")
    past_month = graphene.Boolean(name="pastMonth", description="Est le mois dernier")
    this_year = graphene.Boolean(name="thisYear", description="Est cette année")
    past_year = graphene.Boolean(name="pastYear", description="Est l'année dernière")


class DateTimeFilterInput(graphene.InputObjectType):
    """
    Filter input for datetime fields.

    Supports datetime comparisons, ranges, and convenient temporal filters.
    """

    eq = graphene.DateTime(description="Égal à")
    neq = graphene.DateTime(description="Différent de")
    gt = graphene.DateTime(description="Après la date et l'heure")
    gte = graphene.DateTime(description="Le ou après la date et l'heure")
    lt = graphene.DateTime(description="Avant la date et l'heure")
    lte = graphene.DateTime(description="Le ou avant la date et l'heure")
    between = graphene.List(
        graphene.DateTime, description="Entre [début, fin] inclus"
    )
    is_null = graphene.Boolean(name="isNull", description="Est nul")
    # Date-only filters (ignores time)
    date = graphene.Date(description="Filtrer par date uniquement")
    year = graphene.Int(description="Filtrer par année")
    month = graphene.Int(description="Filtrer par mois (1-12)")
    day = graphene.Int(description="Filtrer par jour du mois")
    week_day = graphene.Int(
        name="weekDay", description="Filtrer par jour de la semaine (1=Dimanche, 7=Samedi)"
    )
    hour = graphene.Int(description="Filtrer par heure (0-23)")
    # Relative date filters
    today = graphene.Boolean(description="Est aujourd'hui")
    yesterday = graphene.Boolean(description="Est hier")
    this_week = graphene.Boolean(name="thisWeek", description="Est cette semaine")
    past_week = graphene.Boolean(name="pastWeek", description="Est la semaine dernière")
    this_month = graphene.Boolean(name="thisMonth", description="Est ce mois-ci")
    past_month = graphene.Boolean(name="pastMonth", description="Est le mois dernier")
    this_year = graphene.Boolean(name="thisYear", description="Est cette année")
    past_year = graphene.Boolean(name="pastYear", description="Est l'année dernière")


__all__ = [
    "DateFilterInput",
    "DateTimeFilterInput",
]

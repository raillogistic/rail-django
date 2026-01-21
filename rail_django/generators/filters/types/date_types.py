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


__all__ = [
    "DateFilterInput",
    "DateTimeFilterInput",
]

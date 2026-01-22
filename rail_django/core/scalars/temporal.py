"""
Temporal custom scalars (DateTime, Date, Time).
"""

from datetime import date, datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from graphene import Scalar
from graphql.error import GraphQLError
from graphql.language import ast

from .ast_utils import _STRING_VALUE_TYPES


class DateTime(Scalar):
    """
    Custom DateTime scalar that handles timezone-aware datetime objects.

    Serializes datetime objects to ISO 8601 format strings.
    Parses ISO 8601 format strings to datetime objects.
    """

    @staticmethod
    def serialize(dt: datetime) -> str:
        """Serialize datetime to ISO 8601 string."""
        if not isinstance(dt, datetime):
            raise GraphQLError(f"Value must be a datetime object, got {type(dt).__name__}")

        # Ensure timezone awareness
        if dt.tzinfo is None:
            dt = timezone.make_aware(dt)

        return dt.isoformat()

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> datetime:
        """Parse AST literal to datetime."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return DateTime.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as DateTime")

    @staticmethod
    def parse_value(value: str) -> datetime:
        """Parse string value to datetime."""
        if not isinstance(value, str):
            raise GraphQLError(f"DateTime must be a string, got {type(value).__name__}")

        try:
            dt = parse_datetime(value)
            if dt is None:
                # Try parsing with different formats
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))

            # Ensure timezone awareness
            if dt.tzinfo is None:
                dt = timezone.make_aware(dt)

            return dt
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid DateTime format: {e}")


class Date(Scalar):
    """
    Custom Date scalar that handles date objects.

    Serializes date objects to ISO format strings (YYYY-MM-DD).
    Parses ISO format strings to date objects.
    """

    @staticmethod
    def serialize(d: date) -> str:
        """Serialize date to ISO string."""
        if not isinstance(d, date):
            raise GraphQLError(f"Value must be a date object, got {type(d).__name__}")

        return d.isoformat()

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> date:
        """Parse AST literal to date."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return Date.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as Date")

    @staticmethod
    def parse_value(value: str) -> date:
        """Parse string value to date."""
        if not isinstance(value, str):
            raise GraphQLError(f"Date must be a string, got {type(value).__name__}")

        try:
            d = parse_date(value)
            if d is None:
                d = datetime.fromisoformat(value).date()

            return d
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid Date format: {e}")


class Time(Scalar):
    """
    Custom Time scalar that handles time objects.

    Serializes time objects to ISO format strings (HH:MM:SS).
    Parses ISO format strings to time objects.
    """

    @staticmethod
    def serialize(t: time) -> str:
        """Serialize time to ISO string."""
        if not isinstance(t, time):
            raise GraphQLError(f"Value must be a time object, got {type(t).__name__}")

        return t.isoformat()

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> time:
        """Parse AST literal to time."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return Time.parse_value(node.value)

        raise GraphQLError(f"Cannot parse {type(node).__name__} as Time")

    @staticmethod
    def parse_value(value: str) -> time:
        """Parse string value to time."""
        if not isinstance(value, str):
            raise GraphQLError(f"Time must be a string, got {type(value).__name__}")

        try:
            t = parse_time(value)
            if t is None:
                t = datetime.fromisoformat(f"2000-01-01T{value}").time()

            return t
        except (ValueError, TypeError) as e:
            raise GraphQLError(f"Invalid Time format: {e}")

"""
Date and time utilities for Rail Django.

This module provides consistent date/time parsing and formatting functions
used throughout the framework.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO 8601 datetime string.

    Args:
        value: ISO datetime string to parse.

    Returns:
        Parsed datetime or None if parsing fails.

    Examples:
        >>> parse_iso_datetime("2024-01-15T10:30:00Z")
        datetime.datetime(2024, 1, 15, 10, 30, tzinfo=datetime.timezone.utc)
        >>> parse_iso_datetime(None)
        None
    """
    if not value:
        return None
    try:
        # Handle 'Z' suffix for UTC
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def format_iso_datetime(value: datetime) -> str:
    """
    Format a datetime as ISO 8601 string.

    Args:
        value: Datetime to format.

    Returns:
        ISO 8601 formatted string.

    Examples:
        >>> format_iso_datetime(datetime(2024, 1, 15, 10, 30))
        "2024-01-15T10:30:00"
    """
    return value.isoformat()


def parse_date(value: Any) -> Optional[date]:
    """
    Parse a date from various input formats.

    Args:
        value: Value to parse as date.

    Returns:
        Parsed date or None if parsing fails.

    Examples:
        >>> parse_date("2024-01-15")
        datetime.date(2024, 1, 15)
        >>> parse_date(datetime(2024, 1, 15, 10, 30))
        datetime.date(2024, 1, 15)
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except (ValueError, TypeError):
            return None
    return None


def coerce_date(value: Any) -> Optional[date]:
    """
    Coerce a value to a date, with flexible input handling.

    Args:
        value: Value to coerce.

    Returns:
        Coerced date or None.

    Examples:
        >>> coerce_date("2024-01-15")
        datetime.date(2024, 1, 15)
    """
    return parse_date(value)


def now_utc() -> datetime:
    """
    Get current UTC datetime.

    Returns:
        Current datetime in UTC.
    """
    return datetime.now(timezone.utc)


def format_date(value: date, fmt: str = "%Y-%m-%d") -> str:
    """
    Format a date using the specified format.

    Args:
        value: Date to format.
        fmt: Format string.

    Returns:
        Formatted date string.
    """
    return value.strftime(fmt)

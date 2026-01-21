"""
Type coercion utilities for Rail Django.

This module provides consistent type coercion functions used throughout
the framework to safely convert values to expected types.
"""

from typing import Any, Callable, Optional, TypeVar, List

T = TypeVar("T")


def coerce_int(value: Any, default: int = 0) -> int:
    """
    Coerce a value to an integer.

    Args:
        value: The value to coerce.
        default: Default value if coercion fails.

    Returns:
        The coerced integer or default.

    Examples:
        >>> coerce_int("42")
        42
        >>> coerce_int(None, default=10)
        10
        >>> coerce_int("invalid", default=0)
        0
    """
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def coerce_bool(value: Any, default: bool = False) -> bool:
    """
    Coerce a value to a boolean.

    Args:
        value: The value to coerce.
        default: Default value if coercion fails.

    Returns:
        The coerced boolean or default.

    Examples:
        >>> coerce_bool("true")
        True
        >>> coerce_bool(1)
        True
        >>> coerce_bool(None, default=False)
        False
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    try:
        return bool(value)
    except (ValueError, TypeError):
        return default


def coerce_str(value: Any, default: str = "") -> str:
    """
    Coerce a value to a string.

    Args:
        value: The value to coerce.
        default: Default value if coercion fails.

    Returns:
        The coerced string or default.

    Examples:
        >>> coerce_str(42)
        "42"
        >>> coerce_str(None, default="N/A")
        "N/A"
    """
    if value is None:
        return default
    try:
        return str(value)
    except (ValueError, TypeError):
        return default


def coerce_float(value: Any, default: float = 0.0) -> float:
    """
    Coerce a value to a float.

    Args:
        value: The value to coerce.
        default: Default value if coercion fails.

    Returns:
        The coerced float or default.

    Examples:
        >>> coerce_float("3.14")
        3.14
        >>> coerce_float(None, default=0.0)
        0.0
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def coerce_list(value: Any, default: Optional[List] = None) -> List:
    """
    Coerce a value to a list.

    Args:
        value: The value to coerce.
        default: Default value if coercion fails.

    Returns:
        The coerced list or default.

    Examples:
        >>> coerce_list("a,b,c")
        ["a,b,c"]
        >>> coerce_list(None)
        []
    """
    if default is None:
        default = []
    if value is None:
        return default
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    return [value]


def coerce_optional(
    value: Any, coerce_fn: Callable[[Any], T], default: Optional[T] = None
) -> Optional[T]:
    """
    Coerce a value using a provided function, returning None or default on failure.

    Args:
        value: The value to coerce.
        coerce_fn: Function to use for coercion.
        default: Default value if coercion fails.

    Returns:
        The coerced value or default.

    Examples:
        >>> coerce_optional("42", int)
        42
        >>> coerce_optional(None, int)
        None
    """
    if value is None:
        return default
    try:
        return coerce_fn(value)
    except (ValueError, TypeError):
        return default

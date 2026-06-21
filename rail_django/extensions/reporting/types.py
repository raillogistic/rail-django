"""
Data classes and constants for the BI reporting module.

This module contains the core type definitions used throughout the reporting
extension for filters, dimensions, metrics, computed fields, and safe
built-in function registries for formula evaluation.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from django.db.models import Avg, Count, Max, Min, Sum
from django.db.models.functions import Coalesce, Greatest, Least, NullIf


class ReportingError(Exception):
    """Raised when a reporting configuration cannot be executed."""


@dataclass
class FilterSpec:
    """Declarative filter used by the execution engine."""

    field: str
    lookup: str = "exact"
    value: Any = None
    connector: str = "and"
    negate: bool = False


@dataclass
class DimensionSpec:
    """Dimension exposed to the frontend for grouping/pivoting."""

    name: str
    field: str
    label: str = ""
    transform: Optional[str] = None
    help_text: str = ""


@dataclass
class MetricSpec:
    """Numeric metric declared for the dataset."""

    name: str
    field: str
    aggregation: str = "sum"
    label: str = ""
    help_text: str = ""
    format: Optional[str] = None
    filter: Optional[Any] = None
    options: Optional[dict[str, Any]] = None


@dataclass
class ComputedFieldSpec:
    """Client-side computed value derived from dimension/metric columns."""

    name: str
    formula: str
    label: str = ""
    help_text: str = ""
    stage: str = "post"


DEFAULT_ALLOWED_LOOKUPS = {
    "exact",
    "iexact",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "in",
    "range",
    "isnull",
    "gt",
    "gte",
    "lt",
    "lte",
}

DEFAULT_MAX_LIMIT = 5_000

AGGREGATION_MAP = {
    "count": Count,
    "distinct_count": lambda expr, *, filter_q=None: Count(
        expr, distinct=True, filter=filter_q
    ),
    "sum": lambda expr, *, filter_q=None: Sum(expr, filter=filter_q),
    "avg": lambda expr, *, filter_q=None: Avg(expr, filter=filter_q),
    "min": lambda expr, *, filter_q=None: Min(expr, filter=filter_q),
    "max": lambda expr, *, filter_q=None: Max(expr, filter=filter_q),
}

POSTGRES_AGGREGATIONS = {
    "array_agg",
    "bit_and",
    "bit_or",
    "bit_xor",
    "bool_and",
    "bool_or",
    "jsonb_agg",
    "string_agg",
}

SAFE_EXPR_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.Load,
    ast.Name,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Not,
    # Support for function calls: IF(...), ROUND(...), COALESCE(...)
    ast.Call,
    ast.keyword,
    # Support for ternary expressions: x if cond else y
    ast.IfExp,
)


SAFE_QUERY_EXPR_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.Load,
    ast.Name,
    # Support for ORM function calls: COALESCE(...), GREATEST(...)
    ast.Call,
    ast.keyword,
    ast.IfExp,
)


# ---------------------------------------------------------------------------
# Built-in functions for post-processing formula evaluation
# ---------------------------------------------------------------------------

def _safe_if(condition: Any, true_val: Any, false_val: Any = None) -> Any:
    """Conditional function: IF(condition, true_value, false_value)."""
    return true_val if condition else false_val


def _safe_coalesce(*args: Any) -> Any:
    """Returns the first non-None argument: COALESCE(a, b, c)."""
    return next((a for a in args if a is not None), None)


def _safe_nullif(a: Any, b: Any) -> Any:
    """Returns None if a == b, else a: NULLIF(a, b)."""
    return None if a == b else a


def _safe_concat(*args: Any) -> str:
    """Concatenate values as strings: CONCAT(a, b, c)."""
    return "".join(str(a) for a in args if a is not None)


def _safe_pct_change(current: Any, previous: Any) -> Any:
    """Percentage change: PCT_CHANGE(current, previous)."""
    try:
        if previous is None or previous == 0:
            return None
        return (current - previous) / previous
    except (TypeError, ZeroDivisionError):
        return None


SAFE_BUILTINS: dict[str, Callable] = {
    # Mathematical functions
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "ceil": math.ceil,
    "floor": math.floor,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    # Type conversion
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    # Conditional and null-handling
    "IF": _safe_if,
    "COALESCE": _safe_coalesce,
    "NULLIF": _safe_nullif,
    # String functions
    "CONCAT": _safe_concat,
    "UPPER": lambda s: str(s).upper() if s is not None else None,
    "LOWER": lambda s: str(s).lower() if s is not None else None,
    "LEN": lambda s: len(str(s)) if s is not None else 0,
    # Analytics
    "PCT_CHANGE": _safe_pct_change,
}


# ---------------------------------------------------------------------------
# Built-in functions for ORM-level (query stage) computed fields
# ---------------------------------------------------------------------------

SAFE_QUERY_BUILTINS: dict[str, Callable] = {
    "COALESCE": lambda *args: Coalesce(*args),
    "GREATEST": lambda *args: Greatest(*args),
    "LEAST": lambda *args: Least(*args),
    "NULLIF": lambda a, b: NullIf(a, b),
}


__all__ = [
    "ReportingError",
    "FilterSpec",
    "DimensionSpec",
    "MetricSpec",
    "ComputedFieldSpec",
    "DEFAULT_ALLOWED_LOOKUPS",
    "DEFAULT_MAX_LIMIT",
    "AGGREGATION_MAP",
    "POSTGRES_AGGREGATIONS",
    "SAFE_EXPR_NODES",
    "SAFE_QUERY_EXPR_NODES",
    "SAFE_BUILTINS",
    "SAFE_QUERY_BUILTINS",
]

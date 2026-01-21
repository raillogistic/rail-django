"""
Data classes and constants for the BI reporting module.

This module contains the core type definitions used throughout the reporting
extension for filters, dimensions, metrics, and computed fields.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Optional

from django.db.models import Avg, Count, Max, Min, Sum


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
)


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
]

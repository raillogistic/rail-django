"""
Utility functions for the BI reporting module.

This module contains helper functions for query expression building,
formula evaluation, filter normalization, and JSON serialization.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence
from uuid import UUID

from django.db.models import ExpressionWrapper, F, FloatField, Q, Value
from django.utils.encoding import force_str
from django.utils.functional import Promise

from .types import (
    FilterSpec,
    ReportingError,
    SAFE_EXPR_NODES,
    SAFE_QUERY_EXPR_NODES,
)


def _safe_query_expression(formula: str, *, allowed_names: set[str]) -> Any:
    """
    Build a Django ORM expression from a simple arithmetic formula.

    Supported:
    - arithmetic operators: +, -, *, /, %, **
    - variables: any name in `allowed_names` (resolved as `F(name)`)
    - constants: numbers / booleans / nulls
    """

    try:
        tree = ast.parse(formula, mode="eval")
    except Exception as exc:
        raise ReportingError(f"Expression invalide '{formula}': {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, SAFE_QUERY_EXPR_NODES):
            raise ReportingError(
                f"Expression non supportee dans '{formula}': {node.__class__.__name__}"
            )

    def build(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return build(node.body)
        if isinstance(node, ast.Num):  # pragma: no cover (py<3.8)
            return Value(node.n)
        if isinstance(node, ast.Constant):
            return Value(node.value)
        if isinstance(node, ast.Name):
            if node.id not in allowed_names:
                raise ReportingError(
                    f"Variable non autorisee '{node.id}' dans '{formula}'."
                )
            return F(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -build(node.operand)
        if isinstance(node, ast.BinOp):
            left = build(node.left)
            right = build(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left**right
            if isinstance(node.op, ast.Div):
                return ExpressionWrapper(left / right, output_field=FloatField())
        raise ReportingError(
            f"Expression non supportee dans '{formula}': {node.__class__.__name__}"
        )

    return build(tree)


def _safe_formula_eval(formula: str, context: dict[str, Any]) -> Any:
    """Evaluate simple arithmetic/boolean expressions without builtins."""

    try:
        tree = ast.parse(formula, mode="eval")
    except Exception as exc:
        raise ReportingError(f"Expression invalide '{formula}': {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, SAFE_EXPR_NODES):
            raise ReportingError(
                f"Expression non supportee dans '{formula}': {node.__class__.__name__}"
            )
        if isinstance(node, ast.Name) and node.id not in context:
            context[node.id] = 0

    compiled = compile(tree, "<reporting-formula>", "eval")
    return eval(compiled, {"__builtins__": {}}, context)


def _to_filter_list(
    raw_filters: Optional[Iterable[dict[str, Any]]],
) -> list[FilterSpec]:
    if not raw_filters:
        return []

    normalized: list[FilterSpec] = []
    for item in raw_filters:
        if not isinstance(item, dict):
            continue
        field_name = item.get("field")
        lookup = item.get("lookup") or "exact"
        value = item.get("value")
        connector = item.get("connector") or "and"
        negate = bool(item.get("negate") or item.get("not"))
        if not field_name:
            continue
        normalized.append(
            FilterSpec(
                field=str(field_name),
                lookup=str(lookup),
                value=value,
                connector=str(connector).lower(),
                negate=negate,
            )
        )
    return normalized


def _to_ordering(ordering: Optional[Iterable[str]]) -> list[str]:
    if ordering is None:
        return []
    if isinstance(ordering, str):
        ordering = [ordering]
    return [str(value) for value in ordering if value]


def _coerce_int(value: Any, *, default: int) -> int:
    """
    Coerce a GraphQL input value to an integer.

    The reporting extension is consumed through the auto-generated GraphQL
    schema, where action form inputs can reach the backend as strings even when
    declared as numbers. This helper makes BI preview/render endpoints tolerant
    to that behavior.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return default

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "":
            return default
        try:
            return int(cleaned)
        except ValueError:
            try:
                return int(float(cleaned))
            except ValueError as exc:
                raise ReportingError(
                    f"Limite invalide '{value}'. Valeur attendue: entier."
                ) from exc

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ReportingError(
            f"Limite invalide '{value}'. Valeur attendue: entier."
        ) from exc


def _stable_json_dumps(value: Any) -> str:
    """
    Serialize a Python object to JSON in a stable way.

    Used to build deterministic cache keys for BI queries.
    """

    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )


def _hash_query_payload(payload: Any) -> str:
    """Return a short stable hash for a query spec/payload."""

    digest = hashlib.sha256(_stable_json_dumps(payload).encode("utf-8")).hexdigest()
    return digest[:24]


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: Any, *, fallback: str) -> str:
    """
    Normalize user-provided names (JSON) into a Python/Django-friendly identifier.

    `annotate(**{name: ...})` and `values(**{name: ...})` require keyword-safe keys.
    """

    raw = str(value or "").strip()
    candidate = raw.replace("__", "_")
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if not candidate:
        candidate = fallback
    if candidate[0].isdigit():
        candidate = f"{fallback}_{candidate}"
    if not _IDENTIFIER_PATTERN.match(candidate):
        candidate = fallback
    return candidate


def _combine_q(conditions: Sequence[Q], *, op: str) -> Optional[Q]:
    if not conditions:
        return None
    op = (op or "and").lower()
    combined = conditions[0]
    for condition in conditions[1:]:
        combined = (combined | condition) if op == "or" else (combined & condition)
    return combined


def _json_sanitize(value: Any) -> Any:
    """
    Convert values to JSON-serializable primitives.

    The reporting engine returns dict payloads as GraphQL Generic scalars.
    Graphene-Django serializes the full response with `json.dumps(...)` (no
    DjangoJSONEncoder), so we must ensure all nested values are compatible with
    the standard library encoder (including lazy translations).
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Promise):
        return force_str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        try:
            return float(value)
        except Exception:
            return str(value)

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, dict):
        return {
            str(_json_sanitize(key)): _json_sanitize(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_sanitize(item) for item in value]

    return force_str(value)


__all__ = [
    "_safe_query_expression",
    "_safe_formula_eval",
    "_to_filter_list",
    "_to_ordering",
    "_coerce_int",
    "_stable_json_dumps",
    "_hash_query_payload",
    "_safe_identifier",
    "_combine_q",
    "_json_sanitize",
]

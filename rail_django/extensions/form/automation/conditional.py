"""
Conditional rule utilities for Form API.
"""

from __future__ import annotations

import re
from typing import Any, Dict


def _resolve_value(values: Dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    cursor: Any = values
    for token in str(path).split("."):
        if not token:
            continue
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(token)
    return cursor


def _as_collection(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _evaluate_single(rule: Dict[str, Any], values: Dict[str, Any]) -> bool:
    field = rule.get("field")
    operator = str(rule.get("operator", "EQ")).upper()
    expected = rule.get("value")
    actual = _resolve_value(values, str(field)) if field else None

    if operator == "EQ":
        return actual == expected
    if operator == "NEQ":
        return actual != expected
    if operator == "GT":
        try:
            return actual is not None and expected is not None and actual > expected
        except TypeError:
            return False
    if operator == "GTE":
        try:
            return actual is not None and expected is not None and actual >= expected
        except TypeError:
            return False
    if operator == "LT":
        try:
            return actual is not None and expected is not None and actual < expected
        except TypeError:
            return False
    if operator == "LTE":
        try:
            return actual is not None and expected is not None and actual <= expected
        except TypeError:
            return False
    if operator == "IN":
        return actual in _as_collection(expected)
    if operator == "NOT_IN":
        return actual not in _as_collection(expected)
    if operator == "CONTAINS":
        if isinstance(actual, str):
            return str(expected or "") in actual
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return False
    if operator == "STARTS_WITH":
        return isinstance(actual, str) and actual.startswith(str(expected or ""))
    if operator == "ENDS_WITH":
        return isinstance(actual, str) and actual.endswith(str(expected or ""))
    if operator == "IS_EMPTY":
        return actual in (None, "", [], {}, ())
    if operator == "IS_NOT_EMPTY":
        return actual not in (None, "", [], {}, ())
    if operator == "IS_NULL":
        return actual is None
    if operator == "IS_NOT_NULL":
        return actual is not None
    if operator == "MATCHES":
        if not isinstance(actual, str):
            return False
        try:
            return bool(re.search(str(expected or ""), actual))
        except re.error:
            return False

    return False


def evaluate_condition(rule: Dict[str, Any], values: Dict[str, Any]) -> bool:
    if not isinstance(rule, dict):
        return True

    conditions = rule.get("conditions")
    if isinstance(conditions, list) and conditions:
        logic = str(rule.get("logic", "AND")).upper()
        evaluations = [
            evaluate_condition(item, values)
            if isinstance(item, dict) and isinstance(item.get("conditions"), list)
            else _evaluate_single(item, values)
            for item in conditions
            if isinstance(item, dict)
        ]
        if not evaluations:
            return True
        if logic == "OR":
            return any(evaluations)
        return all(evaluations)

    return _evaluate_single(rule, values)

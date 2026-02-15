"""
Type coercion utilities for Form API.
"""

from __future__ import annotations

import json
import re
from typing import Any


INTEGER_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)$")
FLOAT_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)\.[0-9]+$")


def _coerce_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    normalized = value.strip()
    if normalized == "":
        return value

    lowered = normalized.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None

    if INTEGER_PATTERN.match(normalized):
        try:
            return int(normalized)
        except ValueError:
            return value

    if FLOAT_PATTERN.match(normalized):
        try:
            return float(normalized)
        except ValueError:
            return value

    if (normalized.startswith("{") and normalized.endswith("}")) or (
        normalized.startswith("[") and normalized.endswith("]")
    ):
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            return value

    return value


def coerce_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: coerce_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [coerce_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(coerce_value(item) for item in value)
    return _coerce_scalar(value)

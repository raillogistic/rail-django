"""
Relation input normalization for Form API.
"""

from __future__ import annotations

from typing import Any, Dict


def normalize_relation_input(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)):
        return {"connect": list(value)}
    return {"connect": [value]}

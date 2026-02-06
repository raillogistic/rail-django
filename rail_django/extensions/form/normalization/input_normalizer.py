"""
Input normalization for Form API mutations.
"""

from __future__ import annotations

from typing import Any, Dict

from .relation_normalizer import normalize_relation_input
from .type_coercion import coerce_value


def normalize_values(values: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    relations = {rel.get("name"): rel for rel in config.get("relations", [])}

    for key, value in (values or {}).items():
        if key in relations:
            normalized[key] = normalize_relation_input(value)
        else:
            normalized[key] = coerce_value(value)
    return normalized

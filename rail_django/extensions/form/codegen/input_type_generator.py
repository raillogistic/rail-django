"""
Placeholder for input type generation.
"""

from __future__ import annotations

from typing import Any, Iterable


def generate_input_types(configs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {"inputs": list(configs)}

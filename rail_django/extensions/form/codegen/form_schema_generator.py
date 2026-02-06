"""
Placeholder for form schema generation.
"""

from __future__ import annotations

from typing import Any, Iterable


def generate_form_schema(configs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return a JSON-serializable form schema bundle."""
    return {"models": list(configs)}

"""
Conditional rule utilities for Form API.
"""

from __future__ import annotations

from typing import Any, Dict, List


def evaluate_condition(rule: Dict[str, Any], values: Dict[str, Any]) -> bool:
    # Placeholder evaluator (always true)
    return True

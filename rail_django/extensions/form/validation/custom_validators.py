"""
Custom validator decorators for Form API.
"""

from __future__ import annotations

from typing import Callable


def form_validator(func: Callable):
    return func

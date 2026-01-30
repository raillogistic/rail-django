"""
Decorators facade.

This module provides backward compatibility for decorators that were moved
to `rail_django.core.decorators`.
"""

from .core.decorators import (
    action_form,
    business_logic,
    confirm_action,
    custom_mutation_name,
    mutation,
    private_method,
    register_schema,
)

__all__ = [
    "action_form",
    "business_logic",
    "confirm_action",
    "custom_mutation_name",
    "mutation",
    "private_method",
    "register_schema",
]

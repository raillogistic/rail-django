"""
Nested input validation limits for mutations.
"""

from dataclasses import dataclass
from typing import Any, List, Optional

import graphene

from .nested_operations import NestedOperationHandler
from .mutations_errors import MutationError, build_mutation_error


@dataclass
class NestedValidationLimits:
    max_depth: Optional[int]
    max_list_items: Optional[int]
    max_total_nodes: Optional[int]
    max_errors: int = 50


def _get_nested_validation_limits(
    info: graphene.ResolveInfo, handler: NestedOperationHandler
) -> NestedValidationLimits:
    settings = None
    if hasattr(info.context, "mutation_generator"):
        mg = info.context.mutation_generator
        # Ensure we have a real settings object, not a mock
        if hasattr(mg, "settings") and mg.settings is not None:
            settings = mg.settings

    def _get_int_or_default(obj, attr, default):
        """Safely get an integer attribute or return default."""
        if obj is None:
            return default
        value = getattr(obj, attr, None)
        if isinstance(value, int):
            return value
        return default

    max_depth = _get_int_or_default(settings, "max_nested_depth", None)
    if max_depth is None:
        max_depth = getattr(handler, "max_depth", 10)

    max_list_items = _get_int_or_default(settings, "max_nested_list_items", None)
    max_total_nodes = _get_int_or_default(settings, "max_nested_nodes", None)
    max_errors = _get_int_or_default(settings, "max_nested_errors", 50)

    return NestedValidationLimits(
        max_depth=max_depth,
        max_list_items=max_list_items,
        max_total_nodes=max_total_nodes,
        max_errors=max_errors,
    )


def _join_nested_path(path: Optional[str], segment: str) -> str:
    if segment.startswith("["):
        return f"{path}{segment}" if path else segment
    return f"{path}.{segment}" if path else segment


def _validate_nested_limits(
    input_data: Any, limits: NestedValidationLimits
) -> list[MutationError]:
    errors: list[MutationError] = []
    stats = {"nodes": 0}

    def add_error(message: str, path: Optional[str]):
        errors.append(build_mutation_error(message=message, field=path))

    def should_stop() -> bool:
        return limits.max_errors is not None and len(errors) >= limits.max_errors

    def check_total_nodes(path: Optional[str]) -> bool:
        if limits.max_total_nodes is None:
            return False
        if stats["nodes"] > limits.max_total_nodes:
            add_error(
                f"Nested input exceeds maximum size of {limits.max_total_nodes} items.",
                path,
            )
            return True
        return False

    def walk(value: Any, path: Optional[str], depth: int):
        if should_stop():
            return
        if limits.max_depth is not None and depth > limits.max_depth:
            add_error(
                f"Nested input exceeds maximum depth of {limits.max_depth}.",
                path,
            )
            return
        if isinstance(value, dict):
            stats["nodes"] += 1
            if check_total_nodes(path):
                return
            for key, nested_value in value.items():
                walk(nested_value, _join_nested_path(path, str(key)), depth + 1)
            return
        if isinstance(value, list):
            if limits.max_list_items is not None and len(value) > limits.max_list_items:
                add_error(
                    f"List exceeds maximum length of {limits.max_list_items}.",
                    path,
                )
                if should_stop():
                    return
            stats["nodes"] += len(value)
            if check_total_nodes(path):
                return
            for index, item in enumerate(value):
                walk(item, _join_nested_path(path, f"[{index}]"), depth + 1)

    walk(input_data, None, 1)
    return errors

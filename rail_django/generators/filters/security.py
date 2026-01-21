"""
Security utilities for GraphQL filter inputs.

This module provides security validation functions and related utilities
for nested filter inputs, including regex pattern validation, filter depth
checking, and complexity limits.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .applicator import NestedFilterApplicator
    from .generator import NestedFilterInputGenerator

logger = logging.getLogger(__name__)

# Security constants (defaults, can be overridden via FilteringSettings)
DEFAULT_MAX_REGEX_LENGTH = 500
DEFAULT_MAX_FILTER_DEPTH = 10
DEFAULT_MAX_FILTER_CLAUSES = 50


class FilterSecurityError(ValueError):
    """Raised when a filter violates security constraints."""

    pass


def validate_regex_pattern(
    pattern: str,
    max_length: int = DEFAULT_MAX_REGEX_LENGTH,
    check_redos: bool = True,
) -> str:
    """
    Validate regex pattern for safety.

    Checks for:
    - Pattern length limits
    - Valid regex syntax
    - Known ReDoS (Regular Expression Denial of Service) patterns

    Args:
        pattern: The regex pattern to validate
        max_length: Maximum allowed pattern length
        check_redos: Whether to check for ReDoS patterns

    Returns:
        The validated pattern (unchanged if valid)

    Raises:
        FilterSecurityError: If pattern is invalid or potentially dangerous
    """
    import re

    if not pattern:
        return pattern

    # Length limit
    if len(pattern) > max_length:
        raise FilterSecurityError(
            f"Regex pattern too long: {len(pattern)} chars (max {max_length})"
        )

    # Try to compile to check validity
    try:
        re.compile(pattern)
    except re.error as e:
        raise FilterSecurityError(f"Invalid regex pattern: {e}")

    # Check for known ReDoS patterns (catastrophic backtracking)
    # These patterns can cause exponential time complexity
    if check_redos:
        redos_patterns = [
            r"\(\.\*\)\+",  # (.*)+
            r"\(\.\+\)\+",  # (.+)+
            r"\(\[^\]]*\]\+\)\+",  # ([abc]+)+
            r"\(.*\|.*\)\+",  # (a|b)+ with complex alternatives
            r"\(\.\*\)\*",  # (.*)*
            r"\(\.\+\)\*",  # (.+)*
        ]

        for dangerous in redos_patterns:
            if re.search(dangerous, pattern):
                raise FilterSecurityError(
                    "Regex pattern contains potentially dangerous constructs that could cause "
                    "catastrophic backtracking. Avoid nested quantifiers like (.*)+, (.+)+, etc."
                )

    return pattern


def validate_filter_depth(
    where_input: Dict[str, Any],
    current_depth: int = 0,
    max_allowed_depth: int = DEFAULT_MAX_FILTER_DEPTH,
) -> int:
    """
    Validate that filter nesting depth doesn't exceed the limit.

    Args:
        where_input: The where filter dictionary
        current_depth: Current nesting depth
        max_allowed_depth: Maximum allowed nesting depth

    Returns:
        Maximum depth found

    Raises:
        FilterSecurityError: If depth exceeds max_allowed_depth
    """
    if current_depth > max_allowed_depth:
        raise FilterSecurityError(
            f"Filter nesting too deep: depth {current_depth} exceeds maximum {max_allowed_depth}"
        )

    found_max_depth = current_depth

    for key, value in where_input.items():
        if value is None:
            continue

        if key in ("AND", "OR") and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    depth = validate_filter_depth(
                        item, current_depth + 1, max_allowed_depth
                    )
                    found_max_depth = max(found_max_depth, depth)

        elif key == "NOT" and isinstance(value, dict):
            depth = validate_filter_depth(value, current_depth + 1, max_allowed_depth)
            found_max_depth = max(found_max_depth, depth)

        elif isinstance(value, dict):
            # Nested field filter or relation filter
            depth = validate_filter_depth(value, current_depth + 1, max_allowed_depth)
            found_max_depth = max(found_max_depth, depth)

    return found_max_depth


def count_filter_clauses(where_input: Dict[str, Any]) -> int:
    """
    Count the total number of filter clauses in a where input.

    Args:
        where_input: The where filter dictionary

    Returns:
        Total number of filter clauses
    """
    count = 0

    for key, value in where_input.items():
        if value is None:
            continue

        count += 1

        if key in ("AND", "OR") and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    count += count_filter_clauses(item)

        elif key == "NOT" and isinstance(value, dict):
            count += count_filter_clauses(value)

        elif isinstance(value, dict):
            count += count_filter_clauses(value)

    return count


def validate_filter_complexity(
    where_input: Dict[str, Any],
    max_depth: int = DEFAULT_MAX_FILTER_DEPTH,
    max_clauses: int = DEFAULT_MAX_FILTER_CLAUSES,
) -> None:
    """
    Validate that filter complexity doesn't exceed limits.

    Checks both depth and total clause count.

    Args:
        where_input: The where filter dictionary
        max_depth: Maximum allowed nesting depth
        max_clauses: Maximum allowed filter clauses

    Raises:
        FilterSecurityError: If filter exceeds complexity limits
    """
    if not where_input:
        return

    # Check depth
    validate_filter_depth(where_input, max_allowed_depth=max_depth)

    # Check clause count
    clause_count = count_filter_clauses(where_input)
    if clause_count > max_clauses:
        raise FilterSecurityError(
            f"Filter too complex: {clause_count} clauses (max {max_clauses})"
        )


# =============================================================================
# Singleton Registries for Filter Generators and Applicators
# =============================================================================

_filter_applicator_registry: Dict[str, "NestedFilterApplicator"] = {}
_filter_generator_registry: Dict[str, "NestedFilterInputGenerator"] = {}


def get_nested_filter_applicator(
    schema_name: str = "default",
) -> "NestedFilterApplicator":
    """
    Get or create a filter applicator for the schema (singleton pattern).

    This ensures filter applicators are reused across requests, avoiding
    repeated initialization overhead.

    Args:
        schema_name: Schema name for multi-schema support

    Returns:
        NestedFilterApplicator instance for the schema
    """
    # Import here to avoid circular imports
    from ..filter_inputs import NestedFilterApplicator

    if schema_name not in _filter_applicator_registry:
        _filter_applicator_registry[schema_name] = NestedFilterApplicator(schema_name)
    return _filter_applicator_registry[schema_name]


def get_nested_filter_generator(
    schema_name: str = "default",
) -> "NestedFilterInputGenerator":
    """
    Get or create a filter generator for the schema (singleton pattern).

    This ensures filter generators are reused across requests, avoiding
    repeated initialization and cache misses.

    Args:
        schema_name: Schema name for multi-schema support

    Returns:
        NestedFilterInputGenerator instance for the schema
    """
    # Import here to avoid circular imports
    from .generator import NestedFilterInputGenerator

    if schema_name not in _filter_generator_registry:
        _filter_generator_registry[schema_name] = NestedFilterInputGenerator(
            schema_name=schema_name
        )
    return _filter_generator_registry[schema_name]


def clear_filter_caches(schema_name: Optional[str] = None) -> None:
    """
    Clear filter caches. Call on schema reload or in tests.

    Args:
        schema_name: Specific schema to clear, or None for all schemas
    """
    if schema_name:
        # Clear specific schema
        _filter_applicator_registry.pop(schema_name, None)
        generator = _filter_generator_registry.pop(schema_name, None)
        # Clear instance caches if they exist
        if generator:
            generator.clear_cache()
    else:
        # Clear all schemas
        for generator in _filter_generator_registry.values():
            generator.clear_cache()
        _filter_applicator_registry.clear()
        _filter_generator_registry.clear()


__all__ = [
    "FilterSecurityError",
    "validate_regex_pattern",
    "validate_filter_depth",
    "count_filter_clauses",
    "validate_filter_complexity",
    "get_nested_filter_applicator",
    "get_nested_filter_generator",
    "clear_filter_caches",
    "DEFAULT_MAX_REGEX_LENGTH",
    "DEFAULT_MAX_FILTER_DEPTH",
    "DEFAULT_MAX_FILTER_CLAUSES",
    "_filter_generator_registry",
    "_filter_applicator_registry",
]

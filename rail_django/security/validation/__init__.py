"""
Input validation and sanitization package for GraphQL operations.

This package provides:
- Configurable sanitization for strings and nested payloads
- Heuristic detection of SQL/XSS patterns
- Field-level validators and model-level hooks
- A GraphQL-friendly validation decorator

Main Components:
    - ValidationSeverity: Enum for issue severity levels
    - ValidationIssue: Single validation issue with context
    - ValidationResult: Validation result for a single value
    - ValidationReport: Aggregated results for a payload
    - InputValidationSettings: Configuration for validation behavior
    - InputSanitizer: String sanitization and threat detection
    - GraphQLInputSanitizer: Mutation input validation
    - FieldValidator: Common field-level validators
    - InputValidator: Unified GraphQL input validation
    - validate_input: Decorator for resolver input validation

Example:
    from rail_django.security.validation import (
        InputValidator,
        validate_input,
        ValidationSeverity,
    )

    # Use the global validator
    from rail_django.security.validation import input_validator
    report = input_validator.validate_payload({"email": "test@example.com"})

    # Use the decorator on resolvers
    @validate_input()
    def resolve_create_user(root, info, input):
        return User.objects.create(**input)
"""

# Types and dataclasses
from .types import (
    DEFAULT_ALLOWED_HTML_ATTRIBUTES,
    DEFAULT_ALLOWED_HTML_TAGS,
    InputValidationSettings,
    SEVERITY_ORDER,
    SQL_INJECTION_PATTERNS,
    ValidationIssue,
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
    XSS_PATTERNS,
)

# Utility functions
from .utils import (
    coerce_input_data,
    highest_severity,
    join_list_path,
    join_path,
    raise_for_issues,
    raise_validation_report,
    severity_meets_threshold,
    setup_default_validators,
    # Backward compatibility aliases
    _coerce_input_data,
    _highest_severity,
    _join_list_path,
    _join_path,
    _raise_for_issues,
    _raise_validation_report,
)

# Sanitizers
from .sanitizer import GraphQLInputSanitizer, InputSanitizer

# Validators
from .validator import FieldValidator, InputValidator

# Decorators
from .decorators import validate_input

# Also export _parse_failure_severity for backward compatibility
from .types import _parse_failure_severity

# Global instances - created lazily to avoid circular imports
_input_validator = None
_graphql_sanitizer = None


def _get_input_validator() -> InputValidator:
    """Get or create the global InputValidator instance."""
    global _input_validator
    if _input_validator is None:
        _input_validator = InputValidator()
    return _input_validator


def _get_graphql_sanitizer() -> GraphQLInputSanitizer:
    """Get or create the global GraphQLInputSanitizer instance."""
    global _graphql_sanitizer
    if _graphql_sanitizer is None:
        _graphql_sanitizer = GraphQLInputSanitizer(validator=_get_input_validator())
    return _graphql_sanitizer


# Create global instances for backward compatibility
input_validator = _get_input_validator()
graphql_sanitizer = _get_graphql_sanitizer()


__all__ = [
    # Enums and constants
    "ValidationSeverity",
    "SEVERITY_ORDER",
    "DEFAULT_ALLOWED_HTML_TAGS",
    "DEFAULT_ALLOWED_HTML_ATTRIBUTES",
    "SQL_INJECTION_PATTERNS",
    "XSS_PATTERNS",
    # Dataclasses
    "ValidationIssue",
    "ValidationResult",
    "ValidationReport",
    "InputValidationSettings",
    # Classes
    "InputSanitizer",
    "GraphQLInputSanitizer",
    "FieldValidator",
    "InputValidator",
    # Decorators
    "validate_input",
    # Utility functions
    "severity_meets_threshold",
    "highest_severity",
    "coerce_input_data",
    "join_path",
    "join_list_path",
    "raise_for_issues",
    "raise_validation_report",
    "setup_default_validators",
    # Backward compatibility aliases
    "_parse_failure_severity",
    "_highest_severity",
    "_coerce_input_data",
    "_join_path",
    "_join_list_path",
    "_raise_for_issues",
    "_raise_validation_report",
    # Global instances
    "input_validator",
    "graphql_sanitizer",
]

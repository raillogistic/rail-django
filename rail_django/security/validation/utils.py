"""
Utility functions for input validation.

This module provides helper functions for:
- Severity comparison and threshold checking
- Path construction for nested validation
- Error raising utilities
- Default validator setup
"""

from typing import Any, Optional, TYPE_CHECKING

from ...core.exceptions import SecurityError
from ...core.exceptions import ValidationError as GraphQLValidationError
from .types import (
    SEVERITY_ORDER,
    ValidationIssue,
    ValidationResult,
    ValidationReport,
    ValidationSeverity,
)

if TYPE_CHECKING:
    from .validator import InputValidator


def severity_meets_threshold(
    severity: ValidationSeverity, threshold: ValidationSeverity
) -> bool:
    """Check if a severity level meets or exceeds a threshold.

    Args:
        severity: The severity level to check.
        threshold: The minimum severity threshold.

    Returns:
        True if severity >= threshold based on SEVERITY_ORDER.
    """
    return SEVERITY_ORDER[severity] >= SEVERITY_ORDER[threshold]


def highest_severity(issues: list[ValidationIssue]) -> ValidationSeverity:
    """Get the highest severity level from a list of issues.

    Args:
        issues: List of validation issues.

    Returns:
        The highest severity found, or LOW if the list is empty.
    """
    if not issues:
        return ValidationSeverity.LOW
    return max(issues, key=lambda issue: SEVERITY_ORDER[issue.severity]).severity


def coerce_input_data(input_data: Any) -> Any:
    """Convert input objects to dictionaries for validation.

    Args:
        input_data: The input data to coerce.

    Returns:
        A dictionary if the input has __dict__, otherwise the original value.
    """
    if hasattr(input_data, "__dict__") and not isinstance(input_data, dict):
        return dict(input_data.__dict__)
    return input_data


def join_path(prefix: Optional[str], field_name: Any) -> str:
    """Join a path prefix with a field name.

    Args:
        prefix: The current path prefix, or None.
        field_name: The field name to append.

    Returns:
        The combined path string (e.g., "parent.child").
    """
    segment = str(field_name)
    if prefix:
        return f"{prefix}.{segment}"
    return segment


def join_list_path(prefix: Optional[str], index: int) -> str:
    """Join a path prefix with a list index.

    Args:
        prefix: The current path prefix, or None.
        index: The list index to append.

    Returns:
        The combined path string (e.g., "items[0]").
    """
    if prefix:
        return f"{prefix}[{index}]"
    return f"[{index}]"


def raise_for_issues(result: ValidationResult) -> None:
    """Raise an exception if validation result contains critical issues.

    Args:
        result: The validation result to check.

    Raises:
        SecurityError: If SQL injection or XSS patterns were detected.
        GraphQLValidationError: If the result is invalid for other reasons.
    """
    if not result.issues:
        return

    if not result.is_valid:
        if any(
            issue.code in {"SQL_INJECTION_PATTERN", "XSS_PATTERN"}
            for issue in result.issues
        ):
            raise SecurityError("Potentially malicious input detected")
        raise GraphQLValidationError(result.violations[0], field=None)


def raise_validation_report(report: ValidationReport) -> None:
    """Raise an exception based on validation report failures.

    Args:
        report: The validation report to check.

    Raises:
        SecurityError: If SQL injection or XSS patterns were detected.
        GraphQLValidationError: If validation failed for other reasons.
    """
    if not report.has_failures():
        return

    if any(
        issue.code in {"SQL_INJECTION_PATTERN", "XSS_PATTERN"}
        and severity_meets_threshold(issue.severity, report.failure_severity)
        for issue in report.issues
    ):
        raise SecurityError(
            "Potentially malicious input detected",
            details={"validation_errors": report.as_error_dict()},
        )

    raise GraphQLValidationError(
        "Input validation failed", validation_errors=report.as_error_dict()
    )


def setup_default_validators(force: bool = False) -> None:
    """Register default field validators on the global input_validator.

    Args:
        force: If True, overwrite existing validators.
    """
    from . import input_validator

    input_validator._register_default_validators(force=force)


# Backward compatibility aliases for private functions
_highest_severity = highest_severity
_coerce_input_data = coerce_input_data
_join_path = join_path
_join_list_path = join_list_path
_raise_for_issues = raise_for_issues
_raise_validation_report = raise_validation_report

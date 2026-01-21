"""
Input sanitization classes for GraphQL operations.

This module provides:
- InputSanitizer for string sanitization and threat detection
- GraphQLInputSanitizer for mutation input validation
"""

import html
import re
from typing import Any, Optional, TYPE_CHECKING

import bleach
from django.utils.html import strip_tags

from .types import (
    InputValidationSettings,
    SQL_INJECTION_PATTERNS,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    XSS_PATTERNS,
)
from .utils import (
    highest_severity,
    raise_validation_report,
    severity_meets_threshold,
    coerce_input_data,
)

if TYPE_CHECKING:
    from .validator import InputValidator


class InputSanitizer:
    """Sanitize strings and detect high-risk input patterns.

    This class provides comprehensive string sanitization including:
    - SQL injection pattern detection
    - XSS pattern detection
    - HTML sanitization or stripping
    - String length validation and truncation

    Example:
        settings = InputValidationSettings()
        sanitizer = InputSanitizer(settings)
        result = sanitizer.sanitize_string("<script>alert('xss')</script>")
        if not result.is_valid:
            print(f"Validation failed: {result.violations}")
    """

    def __init__(self, settings: InputValidationSettings):
        """Initialize the sanitizer with validation settings.

        Args:
            settings: Configuration for validation behavior.
        """
        self.settings = settings
        self._sql_patterns = [
            re.compile(p, re.IGNORECASE) for p in SQL_INJECTION_PATTERNS
        ]
        self._xss_patterns = [re.compile(p, re.IGNORECASE) for p in XSS_PATTERNS]

    def sanitize_string(
        self,
        value: Any,
        field: Optional[str] = None,
        allow_html: Optional[bool] = None,
        max_length: Optional[int] = None,
    ) -> ValidationResult:
        """Sanitize a string value and detect threats.

        Args:
            value: The value to sanitize (must be a string).
            field: Optional field name for error context.
            allow_html: Override settings.allow_html for this call.
            max_length: Override settings.max_string_length for this call.

        Returns:
            ValidationResult containing sanitized value and any issues found.
        """
        issues: list[ValidationIssue] = []
        violations: list[str] = []
        original_value = value

        if not isinstance(value, str):
            issues.append(
                ValidationIssue(
                    field=field,
                    message="Value must be a string",
                    code="STRING_REQUIRED",
                    severity=ValidationSeverity.HIGH,
                )
            )
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                violations=[issue.message for issue in issues],
                severity=ValidationSeverity.HIGH,
                original_value=original_value,
                issues=issues,
            )

        issues.extend(self._detect_threats(value, field))

        sanitized_value = value.strip()

        max_length = (
            max_length if max_length is not None else self.settings.max_string_length
        )
        if max_length and len(sanitized_value) > max_length:
            if self.settings.truncate_long_strings:
                sanitized_value = sanitized_value[:max_length]
                issues.append(
                    ValidationIssue(
                        field=field,
                        message=f"Value truncated to {max_length} characters",
                        code="STRING_TRUNCATED",
                        severity=ValidationSeverity.MEDIUM,
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        field=field,
                        message=f"Value exceeds maximum length of {max_length}",
                        code="STRING_TOO_LONG",
                        severity=ValidationSeverity.HIGH,
                    )
                )

        allow_html = self.settings.allow_html if allow_html is None else allow_html
        if allow_html:
            sanitized_value = bleach.clean(
                sanitized_value,
                tags=self.settings.allowed_html_tags,
                attributes=self.settings.allowed_html_attributes,
                strip=True,
            )
        else:
            sanitized_value = html.escape(strip_tags(sanitized_value))

        violations.extend(issue.message for issue in issues)
        severity = highest_severity(issues)
        is_valid = not any(
            severity_meets_threshold(issue.severity, self.settings.failure_severity)
            for issue in issues
        )

        return ValidationResult(
            is_valid=is_valid,
            sanitized_value=sanitized_value,
            violations=violations,
            severity=severity,
            original_value=original_value,
            issues=issues,
        )

    def _detect_threats(
        self, value: str, field: Optional[str]
    ) -> list[ValidationIssue]:
        """Detect SQL injection and XSS patterns in a string.

        Args:
            value: The string to scan for threats.
            field: Optional field name for error context.

        Returns:
            List of ValidationIssue objects for any threats detected.
        """
        if not self.settings.enable_validation:
            return []

        scan_limit = self.settings.pattern_scan_limit
        scan_value = (
            value[:scan_limit] if scan_limit and len(value) > scan_limit else value
        )
        issues: list[ValidationIssue] = []

        if self.settings.enable_sql_injection_protection:
            for pattern in self._sql_patterns:
                if pattern.search(scan_value):
                    issues.append(
                        ValidationIssue(
                            field=field,
                            message="Potential SQL injection pattern detected",
                            code="SQL_INJECTION_PATTERN",
                            severity=ValidationSeverity.CRITICAL,
                        )
                    )
                    break

        if self.settings.enable_xss_protection:
            for pattern in self._xss_patterns:
                if pattern.search(scan_value):
                    issues.append(
                        ValidationIssue(
                            field=field,
                            message="Potential XSS pattern detected",
                            code="XSS_PATTERN",
                            severity=ValidationSeverity.CRITICAL,
                        )
                    )
                    break

        return issues


class GraphQLInputSanitizer:
    """Sanitize and validate GraphQL mutation inputs.

    This class wraps InputValidator to provide a convenient interface
    for sanitizing mutation inputs in GraphQL resolvers.

    Example:
        sanitizer = GraphQLInputSanitizer()
        cleaned_data = sanitizer.sanitize_mutation_input(input_data)
    """

    def __init__(
        self,
        schema_name: Optional[str] = None,
        validator: Optional["InputValidator"] = None,
    ):
        """Initialize the GraphQL input sanitizer.

        Args:
            schema_name: Optional schema name to load settings for.
            validator: Optional pre-configured InputValidator to use.
        """
        if validator is not None:
            self.validator = validator
        elif schema_name is None:
            # Import here to avoid circular imports
            from . import input_validator

            self.validator = input_validator
        else:
            from .validator import InputValidator

            self.validator = InputValidator(schema_name)

    def sanitize_mutation_input(self, input_data: Any) -> Any:
        """Sanitize mutation input data.

        Handles both dictionary inputs and objects with __dict__.

        Args:
            input_data: The input data to sanitize.

        Returns:
            Sanitized input data (same type as input).

        Raises:
            SecurityError: If malicious patterns are detected.
            GraphQLValidationError: If validation fails.
        """
        if hasattr(input_data, "__dict__") and not isinstance(input_data, dict):
            payload = dict(input_data.__dict__)
            report = self.validator.validate_payload(payload)
            if report.has_failures():
                raise_validation_report(report)
            if isinstance(report.sanitized_data, dict):
                for key, value in report.sanitized_data.items():
                    setattr(input_data, key, value)
            return input_data

        payload = coerce_input_data(input_data)
        report = self.validator.validate_payload(payload)
        if report.has_failures():
            raise_validation_report(report)
        return report.sanitized_data

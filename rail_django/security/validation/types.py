"""
Type definitions for input validation.

This module provides:
- ValidationSeverity enum for categorizing issue severity
- ValidationIssue, ValidationResult, and ValidationReport dataclasses
- InputValidationSettings for configuring validation behavior
- Constants for allowed HTML and threat detection patterns
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from ...config_proxy import get_setting


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER = {
    ValidationSeverity.LOW: 1,
    ValidationSeverity.MEDIUM: 2,
    ValidationSeverity.HIGH: 3,
    ValidationSeverity.CRITICAL: 4,
}


DEFAULT_ALLOWED_HTML_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "ol",
    "ul",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
]

DEFAULT_ALLOWED_HTML_ATTRIBUTES = {
    "*": ["class"],
    "a": ["href", "title"],
    "img": ["src", "alt", "width", "height"],
}

SQL_INJECTION_PATTERNS = [
    r"\b(select|insert|update|delete|drop|alter|create|exec|union)\b",
    r"(--|/\*|\*/)",
    r"\bor\s+1=1\b",
    r"\bunion\s+select\b",
]

XSS_PATTERNS = [
    r"<script\b",
    r"javascript:",
    r"on\w+\s*=",
    r"<iframe\b",
    r"<object\b",
    r"<embed\b",
]


@dataclass
class ValidationIssue:
    """Represents a single validation issue.

    Attributes:
        field: The field name where the issue occurred, or None for general issues.
        message: Human-readable description of the issue.
        code: Machine-readable error code for programmatic handling.
        severity: The severity level of this issue.
    """

    field: Optional[str]
    message: str
    code: str
    severity: ValidationSeverity


@dataclass
class ValidationResult:
    """Represents the validation result for a single value.

    Attributes:
        is_valid: Whether the value passed validation.
        sanitized_value: The cleaned/sanitized version of the input.
        violations: List of violation messages (deprecated, use issues).
        severity: The highest severity level among all issues.
        original_value: The original input value before sanitization.
        issues: List of ValidationIssue objects with detailed information.
    """

    is_valid: bool
    sanitized_value: Any
    violations: list[str]
    severity: ValidationSeverity
    original_value: Any
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Aggregated validation results for a payload.

    Provides methods to extract error messages and check for failures
    based on severity thresholds.

    Attributes:
        is_valid: Whether the entire payload passed validation.
        sanitized_data: The cleaned/sanitized version of the entire payload.
        issues: List of all validation issues found.
        failure_severity: Minimum severity level that constitutes a failure.
    """

    is_valid: bool
    sanitized_data: Any
    issues: list[ValidationIssue]
    failure_severity: ValidationSeverity

    def error_messages(self) -> list[str]:
        """Get error messages for issues meeting the failure threshold.

        Returns:
            List of error message strings.
        """
        from .utils import severity_meets_threshold

        return [
            issue.message
            for issue in self.issues
            if severity_meets_threshold(issue.severity, self.failure_severity)
        ]

    def as_error_dict(self) -> dict[str, list[str]]:
        """Convert issues to a dictionary keyed by field name.

        Returns:
            Dictionary mapping field names to lists of error messages.
            Issues without a field are grouped under '__all__'.
        """
        from .utils import severity_meets_threshold

        errors: dict[str, list[str]] = {}
        for issue in self.issues:
            if not severity_meets_threshold(issue.severity, self.failure_severity):
                continue
            key = issue.field or "__all__"
            errors.setdefault(key, []).append(issue.message)
        return errors

    def has_failures(self) -> bool:
        """Check if any issues meet the failure severity threshold.

        Returns:
            True if any issue has severity >= failure_severity.
        """
        from .utils import severity_meets_threshold

        return any(
            severity_meets_threshold(issue.severity, self.failure_severity)
            for issue in self.issues
        )


def _parse_failure_severity(value: Any) -> ValidationSeverity:
    """Parse a failure severity value from various input formats.

    Args:
        value: A ValidationSeverity enum, string, or other value.

    Returns:
        The parsed ValidationSeverity, defaulting to HIGH if unrecognized.
    """
    if isinstance(value, ValidationSeverity):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        for severity in ValidationSeverity:
            if severity.value == normalized:
                return severity
    return ValidationSeverity.HIGH


@dataclass
class InputValidationSettings:
    """Configuration for input validation behavior.

    Attributes:
        enable_validation: Master switch for all validation.
        enable_sql_injection_protection: Detect SQL injection patterns.
        enable_xss_protection: Detect XSS patterns.
        allow_html: Whether to allow HTML in string inputs.
        allowed_html_tags: List of allowed HTML tags when allow_html is True.
        allowed_html_attributes: Dict of allowed attributes per tag.
        max_string_length: Maximum allowed string length, or None for unlimited.
        truncate_long_strings: If True, truncate instead of rejecting long strings.
        failure_severity: Minimum severity that causes validation to fail.
        pattern_scan_limit: Max characters to scan for threat patterns.
    """

    enable_validation: bool = True
    enable_sql_injection_protection: bool = True
    enable_xss_protection: bool = True
    allow_html: bool = False
    allowed_html_tags: list[str] = field(
        default_factory=lambda: list(DEFAULT_ALLOWED_HTML_TAGS)
    )
    allowed_html_attributes: dict[str, list[str]] = field(
        default_factory=lambda: dict(DEFAULT_ALLOWED_HTML_ATTRIBUTES)
    )
    max_string_length: Optional[int] = None
    truncate_long_strings: bool = False
    failure_severity: ValidationSeverity = ValidationSeverity.HIGH
    pattern_scan_limit: int = 10000

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "InputValidationSettings":
        """Create settings from schema configuration.

        Args:
            schema_name: Optional schema name to load settings for.

        Returns:
            InputValidationSettings instance populated from configuration.
        """
        enable_validation = bool(
            get_setting(
                "security_settings.enable_input_validation", True, schema_name
            )
        )
        enable_sql = bool(
            get_setting(
                "security_settings.enable_sql_injection_protection", True, schema_name
            )
        )
        enable_xss = bool(
            get_setting(
                "security_settings.enable_xss_protection", True, schema_name
            )
        )
        allow_html = bool(
            get_setting("security_settings.input_allow_html", False, schema_name)
        )
        max_length = get_setting(
            "security_settings.input_max_string_length", None, schema_name
        )
        truncate = bool(
            get_setting(
                "security_settings.input_truncate_long_strings", False, schema_name
            )
        )
        failure_severity = get_setting(
            "security_settings.input_failure_severity", "high", schema_name
        )
        scan_limit = get_setting(
            "security_settings.input_pattern_scan_limit", 10000, schema_name
        )
        tags = get_setting(
            "security_settings.input_allowed_html_tags", None, schema_name
        )
        attrs = get_setting(
            "security_settings.input_allowed_html_attributes", None, schema_name
        )

        parsed_failure = _parse_failure_severity(failure_severity)

        if isinstance(max_length, str) and max_length.strip() == "":
            max_length = None
        if max_length is not None:
            try:
                max_length = int(max_length)
            except (TypeError, ValueError):
                max_length = None

        try:
            scan_limit = int(scan_limit)
        except (TypeError, ValueError):
            scan_limit = 10000

        return cls(
            enable_validation=enable_validation,
            enable_sql_injection_protection=enable_sql,
            enable_xss_protection=enable_xss,
            allow_html=allow_html,
            allowed_html_tags=list(tags) if tags else list(DEFAULT_ALLOWED_HTML_TAGS),
            allowed_html_attributes=dict(attrs) if attrs else dict(DEFAULT_ALLOWED_HTML_ATTRIBUTES),
            max_string_length=max_length,
            truncate_long_strings=truncate,
            failure_severity=parsed_failure,
            pattern_scan_limit=max(0, scan_limit),
        )

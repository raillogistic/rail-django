"""
Input validation and sanitization utilities for GraphQL operations.

This module provides:
- Configurable sanitization for strings and nested payloads
- Heuristic detection of SQL/XSS patterns
- Field-level validators and model-level hooks
- A GraphQL-friendly validation decorator
"""

import html
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import bleach
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator, validate_email
from django.utils.html import strip_tags
from ..config_proxy import get_setting
from ..core.exceptions import SecurityError
from ..core.exceptions import ValidationError as GraphQLValidationError

logger = logging.getLogger(__name__)


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


def severity_meets_threshold(
    severity: ValidationSeverity, threshold: ValidationSeverity
) -> bool:
    return SEVERITY_ORDER[severity] >= SEVERITY_ORDER[threshold]


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
    """Represents a single validation issue."""

    field: Optional[str]
    message: str
    code: str
    severity: ValidationSeverity


@dataclass
class ValidationResult:
    """Represents the validation result for a single value."""

    is_valid: bool
    sanitized_value: Any
    violations: list[str]
    severity: ValidationSeverity
    original_value: Any
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Aggregated validation results for a payload."""

    is_valid: bool
    sanitized_data: Any
    issues: list[ValidationIssue]
    failure_severity: ValidationSeverity

    def error_messages(self) -> list[str]:
        return [
            issue.message
            for issue in self.issues
            if severity_meets_threshold(issue.severity, self.failure_severity)
        ]

    def as_error_dict(self) -> dict[str, list[str]]:
        errors: dict[str, list[str]] = {}
        for issue in self.issues:
            if not severity_meets_threshold(issue.severity, self.failure_severity):
                continue
            key = issue.field or "__all__"
            errors.setdefault(key, []).append(issue.message)
        return errors

    def has_failures(self) -> bool:
        return any(
            severity_meets_threshold(issue.severity, self.failure_severity)
            for issue in self.issues
        )


@dataclass
class InputValidationSettings:
    """Configuration for input validation behavior."""

    enable_validation: bool = True
    enable_sql_injection_protection: bool = True
    enable_xss_protection: bool = True
    allow_html: bool = False
    allowed_html_tags: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_HTML_TAGS))
    allowed_html_attributes: dict[str, list[str]] = field(
        default_factory=lambda: dict(DEFAULT_ALLOWED_HTML_ATTRIBUTES)
    )
    max_string_length: Optional[int] = None
    truncate_long_strings: bool = False
    failure_severity: ValidationSeverity = ValidationSeverity.HIGH
    pattern_scan_limit: int = 10000

    @classmethod
    def from_schema(cls, schema_name: Optional[str] = None) -> "InputValidationSettings":
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


def _parse_failure_severity(value: Any) -> ValidationSeverity:
    if isinstance(value, ValidationSeverity):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        for severity in ValidationSeverity:
            if severity.value == normalized:
                return severity
    return ValidationSeverity.HIGH


class InputSanitizer:
    """Sanitize strings and detect high-risk input patterns."""

    def __init__(self, settings: InputValidationSettings):
        self.settings = settings
        self._sql_patterns = [re.compile(p, re.IGNORECASE) for p in SQL_INJECTION_PATTERNS]
        self._xss_patterns = [re.compile(p, re.IGNORECASE) for p in XSS_PATTERNS]

    def sanitize_string(
        self,
        value: Any,
        field: Optional[str] = None,
        allow_html: Optional[bool] = None,
        max_length: Optional[int] = None,
    ) -> ValidationResult:
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

        max_length = max_length if max_length is not None else self.settings.max_string_length
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
        severity = _highest_severity(issues)
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

    def _detect_threats(self, value: str, field: Optional[str]) -> list[ValidationIssue]:
        if not self.settings.enable_validation:
            return []

        scan_limit = self.settings.pattern_scan_limit
        scan_value = value[:scan_limit] if scan_limit and len(value) > scan_limit else value
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


def _highest_severity(issues: list[ValidationIssue]) -> ValidationSeverity:
    if not issues:
        return ValidationSeverity.LOW
    return max(issues, key=lambda issue: SEVERITY_ORDER[issue.severity]).severity


class FieldValidator:
    """Common field-level validators built on the sanitizer."""

    @staticmethod
    def validate_email_field(
        value: str, sanitizer: Optional[InputSanitizer] = None
    ) -> str:
        if not value:
            raise GraphQLValidationError("Email address is required", field="email")

        sanitizer = sanitizer or InputSanitizer(InputValidationSettings())
        result = sanitizer.sanitize_string(value, field="email")
        _raise_for_issues(result)

        cleaned_email = result.sanitized_value.lower().strip()
        try:
            validate_email(cleaned_email)
        except DjangoValidationError as exc:
            raise GraphQLValidationError(
                f"Invalid email format: {exc}", field="email"
            )

        return cleaned_email

    @staticmethod
    def validate_url_field(
        value: str, sanitizer: Optional[InputSanitizer] = None
    ) -> str:
        if not value:
            return value

        sanitizer = sanitizer or InputSanitizer(InputValidationSettings())
        result = sanitizer.sanitize_string(value, field="url")
        _raise_for_issues(result)

        cleaned_url = result.sanitized_value.strip()
        try:
            validator = URLValidator()
            validator(cleaned_url)
        except DjangoValidationError as exc:
            raise GraphQLValidationError(f"Invalid URL format: {exc}", field="url")

        parsed = urlparse(cleaned_url)
        if parsed.scheme not in ["http", "https"]:
            raise GraphQLValidationError(
                "Only HTTP and HTTPS protocols are allowed", field="url"
            )

        return cleaned_url

    @staticmethod
    def validate_integer_field(
        value: Any, min_value: Optional[int] = None, max_value: Optional[int] = None
    ) -> int:
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise GraphQLValidationError("Integer value required", field="integer")

        if min_value is not None and int_value < min_value:
            raise GraphQLValidationError(
                f"Value must be greater than or equal to {min_value}", field="integer"
            )

        if max_value is not None and int_value > max_value:
            raise GraphQLValidationError(
                f"Value must be less than or equal to {max_value}", field="integer"
            )

        return int_value

    @staticmethod
    def validate_decimal_field(
        value: Any,
        max_digits: Optional[int] = None,
        decimal_places: Optional[int] = None,
    ) -> "Decimal":
        from decimal import Decimal, InvalidOperation

        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise GraphQLValidationError("Decimal value required", field="decimal")

        if max_digits is not None:
            sign, digits, exponent = decimal_value.as_tuple()
            total_digits = len(digits)
            if total_digits > max_digits:
                raise GraphQLValidationError(
                    f"Maximum {max_digits} digits allowed", field="decimal"
                )

        if decimal_places is not None:
            sign, digits, exponent = decimal_value.as_tuple()
            if exponent < -decimal_places:
                raise GraphQLValidationError(
                    f"Maximum {decimal_places} decimal places allowed", field="decimal"
                )

        return decimal_value

    @staticmethod
    def validate_string_field(
        value: str,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        allow_html: bool = False,
        field_name: Optional[str] = None,
        sanitizer: Optional[InputSanitizer] = None,
    ) -> str:
        field_label = field_name or "string"
        if value is None:
            value = ""

        sanitizer = sanitizer or InputSanitizer(InputValidationSettings())
        result = sanitizer.sanitize_string(
            str(value), field=field_label, allow_html=allow_html, max_length=max_length
        )
        _raise_for_issues(result)

        cleaned_value = result.sanitized_value

        if min_length is not None and len(cleaned_value) < min_length:
            raise GraphQLValidationError(
                f"Minimum length is {min_length} characters", field=field_label
            )

        if max_length is not None and len(cleaned_value) > max_length:
            raise GraphQLValidationError(
                f"Maximum length is {max_length} characters", field=field_label
            )

        if pattern and not re.match(pattern, cleaned_value):
            raise GraphQLValidationError("Invalid format", field=field_label)

        return cleaned_value


class InputValidator:
    """Unified validator for GraphQL inputs."""

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name
        self.settings = InputValidationSettings.from_schema(schema_name)
        self.sanitizer = InputSanitizer(self.settings)
        self.field_validators: dict[str, Callable] = {}
        self.model_validators: dict[str, list[Callable]] = {}
        self._register_default_validators()

    def register_field_validator(self, field_name: str, validator: Callable) -> None:
        self.field_validators[field_name] = validator
        logger.info("Field validator registered: %s", field_name)

    def register_model_validator(self, model_name: str, validator: Callable) -> None:
        self.model_validators.setdefault(model_name, []).append(validator)
        logger.info("Model validator registered: %s", model_name)

    def validate_payload(self, input_data: Any) -> ValidationReport:
        if not self.settings.enable_validation:
            return ValidationReport(
                is_valid=True,
                sanitized_data=input_data,
                issues=[],
                failure_severity=self.settings.failure_severity,
            )

        issues: list[ValidationIssue] = []
        sanitized = self._sanitize_value(input_data, issues, None)
        is_valid = not any(
            severity_meets_threshold(issue.severity, self.settings.failure_severity)
            for issue in issues
        )
        return ValidationReport(
            is_valid=is_valid,
            sanitized_data=sanitized,
            issues=issues,
            failure_severity=self.settings.failure_severity,
        )

    def validate_input(
        self, model_name: Optional[str], input_data: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.settings.enable_validation:
            return input_data

        if not isinstance(input_data, dict):
            raise GraphQLValidationError("Input payload must be an object")

        report = self.validate_payload(input_data)
        if report.has_failures():
            _raise_validation_report(report)

        validated_data: dict[str, Any] = {}
        errors: dict[str, list[str]] = {}

        for field_name, value in report.sanitized_data.items():
            if field_name in self.field_validators:
                try:
                    validated_data[field_name] = self.field_validators[field_name](value)
                except (GraphQLValidationError, SecurityError) as exc:
                    errors.setdefault(field_name, []).append(str(exc))
            else:
                try:
                    validated_data[field_name] = self._validate_generic_field(
                        field_name, value
                    )
                except GraphQLValidationError as exc:
                    errors.setdefault(field_name, []).append(str(exc))

        for validator in self.model_validators.get(model_name or "", []):
            try:
                validator(validated_data)
            except GraphQLValidationError as exc:
                errors.setdefault(model_name or "__all__", []).append(str(exc))

        if errors:
            raise GraphQLValidationError(
                "Input validation failed", validation_errors=errors
            )

        return validated_data

    def validate_string(
        self, value: str, max_length: Optional[int] = None, allow_html: bool = False
    ) -> ValidationResult:
        return self.sanitizer.sanitize_string(
            value, allow_html=allow_html, max_length=max_length
        )

    def validate_email(self, email: str) -> ValidationResult:
        try:
            cleaned = FieldValidator.validate_email_field(email, sanitizer=self.sanitizer)
            return ValidationResult(
                is_valid=True,
                sanitized_value=cleaned,
                violations=[],
                severity=ValidationSeverity.LOW,
                original_value=email,
                issues=[],
            )
        except (GraphQLValidationError, SecurityError) as exc:
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                violations=[str(exc)],
                severity=ValidationSeverity.HIGH,
                original_value=email,
                issues=[
                    ValidationIssue(
                        field="email",
                        message=str(exc),
                        code="INVALID_EMAIL",
                        severity=ValidationSeverity.HIGH,
                    )
                ],
            )

    def validate_url(self, url: str) -> ValidationResult:
        try:
            cleaned = FieldValidator.validate_url_field(url, sanitizer=self.sanitizer)
            return ValidationResult(
                is_valid=True,
                sanitized_value=cleaned,
                violations=[],
                severity=ValidationSeverity.LOW,
                original_value=url,
                issues=[],
            )
        except (GraphQLValidationError, SecurityError) as exc:
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                violations=[str(exc)],
                severity=ValidationSeverity.HIGH,
                original_value=url,
                issues=[
                    ValidationIssue(
                        field="url",
                        message=str(exc),
                        code="INVALID_URL",
                        severity=ValidationSeverity.HIGH,
                    )
                ],
            )

    def validate_graphql_input(
        self, input_data: dict[str, Any], schema_definition: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for field_name, value in input_data.items():
            if isinstance(value, str):
                results[field_name] = self.validate_string(value)
            elif isinstance(value, dict):
                results[field_name] = self.validate_graphql_input(value, schema_definition)
            elif isinstance(value, list):
                list_results = []
                for item in value:
                    if isinstance(item, str):
                        list_results.append(self.validate_string(item))
                    elif isinstance(item, dict):
                        list_results.append(
                            self.validate_graphql_input(item, schema_definition)
                        )
                    else:
                        list_results.append(item)
                results[field_name] = list_results
        return results

    def _validate_generic_field(self, field_name: str, value: Any) -> Any:
        if value is None:
            return value

        if isinstance(value, str):
            lowered = field_name.lower()
            if "email" in lowered:
                return FieldValidator.validate_email_field(
                    value, sanitizer=self.sanitizer
                )
            if "url" in lowered or "link" in lowered:
                return FieldValidator.validate_url_field(
                    value, sanitizer=self.sanitizer
                )
            return FieldValidator.validate_string_field(
                value,
                max_length=self.settings.max_string_length,
                field_name=field_name,
                sanitizer=self.sanitizer,
            )

        if isinstance(value, int):
            return FieldValidator.validate_integer_field(value)

        if isinstance(value, float):
            return FieldValidator.validate_decimal_field(value)

        return value

    def _sanitize_value(
        self, value: Any, issues: list[ValidationIssue], path: Optional[str]
    ) -> Any:
        if hasattr(value, "__dict__") and not isinstance(value, dict):
            return self._sanitize_value(dict(value.__dict__), issues, path)

        if isinstance(value, dict):
            sanitized_map: dict[str, Any] = {}
            for key, nested_value in value.items():
                field_path = _join_path(path, key)
                sanitized_map[key] = self._sanitize_value(
                    nested_value, issues, field_path
                )
            return sanitized_map

        if isinstance(value, list):
            sanitized_list = []
            for index, item in enumerate(value):
                field_path = _join_list_path(path, index)
                sanitized_list.append(self._sanitize_value(item, issues, field_path))
            return sanitized_list

        if isinstance(value, str):
            result = self.sanitizer.sanitize_string(value, field=path)
            issues.extend(result.issues)
            return result.sanitized_value

        return value

    def _register_default_validators(self) -> None:
        self.register_field_validator(
            "email",
            lambda value: FieldValidator.validate_email_field(
                value, sanitizer=self.sanitizer
            ),
        )
        self.register_field_validator(
            "url",
            lambda value: FieldValidator.validate_url_field(
                value, sanitizer=self.sanitizer
            ),
        )
        self.register_field_validator(
            "website",
            lambda value: FieldValidator.validate_url_field(
                value, sanitizer=self.sanitizer
            ),
        )

        def validate_password(value: str) -> str:
            if len(value) < 8:
                raise GraphQLValidationError(
                    "Password must be at least 8 characters", field="password"
                )
            if not re.search(r"[A-Z]", value):
                raise GraphQLValidationError(
                    "Password must include an uppercase letter", field="password"
                )
            if not re.search(r"[a-z]", value):
                raise GraphQLValidationError(
                    "Password must include a lowercase letter", field="password"
                )
            if not re.search(r"\d", value):
                raise GraphQLValidationError(
                    "Password must include a number", field="password"
                )
            return value

        self.register_field_validator("password", validate_password)


class GraphQLInputSanitizer:
    """Sanitize and validate GraphQL mutation inputs."""

    def __init__(self, schema_name: Optional[str] = None, validator: InputValidator = None):
        self.validator = validator or InputValidator(schema_name)

    def sanitize_mutation_input(self, input_data: Any) -> Any:
        if hasattr(input_data, "__dict__") and not isinstance(input_data, dict):
            payload = dict(input_data.__dict__)
            report = self.validator.validate_payload(payload)
            if report.has_failures():
                _raise_validation_report(report)
            if isinstance(report.sanitized_data, dict):
                for key, value in report.sanitized_data.items():
                    setattr(input_data, key, value)
            return input_data

        payload = _coerce_input_data(input_data)
        report = self.validator.validate_payload(payload)
        if report.has_failures():
            _raise_validation_report(report)
        return report.sanitized_data


def validate_input(validator_func: Callable = None):
    """
    Decorator to validate GraphQL resolver inputs.

    Args:
        validator_func: Optional custom validation function.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            sanitizer = GraphQLInputSanitizer()
            input_keys = [
                key
                for key in kwargs
                if key == "input" or key == "data" or key.endswith("_data")
            ]
            for key in input_keys:
                kwargs[key] = sanitizer.sanitize_mutation_input(kwargs[key])

            if validator_func:
                validator_func(*args, **kwargs)

            return func(*args, **kwargs)

        return wrapper

    return decorator


input_validator = InputValidator()
graphql_sanitizer = GraphQLInputSanitizer(validator=input_validator)


def setup_default_validators() -> None:
    """Register default field validators."""

    input_validator._register_default_validators()


def _coerce_input_data(input_data: Any) -> Any:
    if hasattr(input_data, "__dict__") and not isinstance(input_data, dict):
        return dict(input_data.__dict__)
    return input_data


def _join_path(prefix: Optional[str], field: Any) -> str:
    segment = str(field)
    if prefix:
        return f"{prefix}.{segment}"
    return segment


def _join_list_path(prefix: Optional[str], index: int) -> str:
    if prefix:
        return f"{prefix}[{index}]"
    return f"[{index}]"


def _raise_for_issues(result: ValidationResult) -> None:
    if not result.issues:
        return

    if not result.is_valid:
        if any(issue.code in {"SQL_INJECTION_PATTERN", "XSS_PATTERN"} for issue in result.issues):
            raise SecurityError("Potentially malicious input detected")
        raise GraphQLValidationError(result.violations[0], field=None)


def _raise_validation_report(report: ValidationReport) -> None:
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

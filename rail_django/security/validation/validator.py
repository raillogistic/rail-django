"""
Field and input validation classes for GraphQL operations.
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator, validate_email

from ...core.exceptions import SecurityError
from ...core.exceptions import ValidationError as GraphQLValidationError
from .sanitizer import InputSanitizer
from .types import (
    InputValidationSettings,
    ValidationIssue,
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
)
from .utils import (
    join_list_path,
    join_path,
    raise_for_issues,
    raise_validation_report,
    severity_meets_threshold,
)

logger = logging.getLogger(__name__)


class FieldValidator:
    """Common field-level validators built on the sanitizer."""

    @staticmethod
    def validate_email_field(
        value: str, sanitizer: Optional[InputSanitizer] = None
    ) -> str:
        """Validate and sanitize an email address."""
        if not value:
            raise GraphQLValidationError("Email address is required", field="email")

        sanitizer = sanitizer or InputSanitizer(InputValidationSettings())
        result = sanitizer.sanitize_string(value, field="email")
        raise_for_issues(result)

        cleaned_email = result.sanitized_value.lower().strip()
        try:
            validate_email(cleaned_email)
        except DjangoValidationError as exc:
            raise GraphQLValidationError(f"Invalid email format: {exc}", field="email")
        return cleaned_email

    @staticmethod
    def validate_url_field(
        value: str, sanitizer: Optional[InputSanitizer] = None
    ) -> str:
        """Validate and sanitize a URL."""
        if not value:
            return value

        sanitizer = sanitizer or InputSanitizer(InputValidationSettings())
        result = sanitizer.sanitize_string(value, field="url")
        raise_for_issues(result)

        cleaned_url = result.sanitized_value.strip()
        try:
            URLValidator()(cleaned_url)
        except DjangoValidationError as exc:
            raise GraphQLValidationError(f"Invalid URL format: {exc}", field="url")

        if urlparse(cleaned_url).scheme not in ["http", "https"]:
            raise GraphQLValidationError(
                "Only HTTP and HTTPS protocols are allowed", field="url"
            )
        return cleaned_url

    @staticmethod
    def validate_integer_field(
        value: Any, min_value: Optional[int] = None, max_value: Optional[int] = None
    ) -> int:
        """Validate an integer value with optional range constraints."""
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
    ) -> Decimal:
        """Validate a decimal value with optional precision constraints."""
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise GraphQLValidationError("Decimal value required", field="decimal")

        if max_digits is not None:
            _, digits, _ = decimal_value.as_tuple()
            if len(digits) > max_digits:
                raise GraphQLValidationError(
                    f"Maximum {max_digits} digits allowed", field="decimal"
                )

        if decimal_places is not None:
            _, _, exponent = decimal_value.as_tuple()
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
        """Validate and sanitize a string value."""
        field_label = field_name or "string"
        if value is None:
            value = ""

        sanitizer = sanitizer or InputSanitizer(InputValidationSettings())
        result = sanitizer.sanitize_string(
            str(value), field=field_label, allow_html=allow_html, max_length=max_length
        )
        raise_for_issues(result)

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
        """Initialize with optional schema name for settings lookup."""
        self.schema_name = schema_name
        self.settings = InputValidationSettings.from_schema(schema_name)
        self.sanitizer = InputSanitizer(self.settings)
        self.field_validators: dict[str, Callable] = {}
        self.model_validators: dict[str, list[Callable]] = {}
        self._register_default_validators()

    def register_field_validator(
        self, field_name: str, validator: Callable, *, replace: bool = True
    ) -> None:
        """Register a custom validator for a field name."""
        existing = self.field_validators.get(field_name)
        schema_label = self.schema_name or "default"

        if existing is not None:
            if existing is validator or not replace:
                logger.debug("Field validator already registered: %s", field_name)
                return
            logger.info("Field validator updated: %s (schema=%s)", field_name, schema_label)
        else:
            logger.info("Field validator registered: %s (schema=%s)", field_name, schema_label)
        self.field_validators[field_name] = validator

    def register_model_validator(self, model_name: str, validator: Callable) -> None:
        """Register a model-level validator."""
        validators = self.model_validators.setdefault(model_name, [])
        if validator in validators:
            logger.debug("Model validator already registered: %s", model_name)
            return
        validators.append(validator)
        logger.info("Model validator registered: %s (schema=%s)", model_name, self.schema_name or "default")

    def validate_payload(self, input_data: Any) -> ValidationReport:
        """Validate and sanitize an input payload."""
        if not self.settings.enable_validation:
            return ValidationReport(
                is_valid=True, sanitized_data=input_data,
                issues=[], failure_severity=self.settings.failure_severity,
            )

        issues: list[ValidationIssue] = []
        sanitized = self._sanitize_value(input_data, issues, None)
        is_valid = not any(
            severity_meets_threshold(issue.severity, self.settings.failure_severity)
            for issue in issues
        )
        return ValidationReport(
            is_valid=is_valid, sanitized_data=sanitized,
            issues=issues, failure_severity=self.settings.failure_severity,
        )

    def validate_input(
        self, model_name: Optional[str], input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate input data with field and model validators."""
        if not self.settings.enable_validation:
            return input_data

        if not isinstance(input_data, dict):
            raise GraphQLValidationError("Input payload must be an object")

        report = self.validate_payload(input_data)
        if report.has_failures():
            raise_validation_report(report)

        validated_data: dict[str, Any] = {}
        errors: dict[str, list[str]] = {}

        for field_name, value in report.sanitized_data.items():
            try:
                if field_name in self.field_validators:
                    validated_data[field_name] = self.field_validators[field_name](value)
                else:
                    validated_data[field_name] = self._validate_generic_field(field_name, value)
            except (GraphQLValidationError, SecurityError) as exc:
                errors.setdefault(field_name, []).append(str(exc))

        for validator in self.model_validators.get(model_name or "", []):
            try:
                validator(validated_data)
            except GraphQLValidationError as exc:
                errors.setdefault(model_name or "__all__", []).append(str(exc))

        if errors:
            raise GraphQLValidationError("Input validation failed", validation_errors=errors)
        return validated_data

    def validate_string(
        self, value: str, max_length: Optional[int] = None, allow_html: bool = False
    ) -> ValidationResult:
        """Validate a single string value."""
        return self.sanitizer.sanitize_string(value, allow_html=allow_html, max_length=max_length)

    def validate_email(self, email: str) -> ValidationResult:
        """Validate an email address."""
        try:
            cleaned = FieldValidator.validate_email_field(email, sanitizer=self.sanitizer)
            return ValidationResult(
                is_valid=True, sanitized_value=cleaned, violations=[],
                severity=ValidationSeverity.LOW, original_value=email, issues=[],
            )
        except (GraphQLValidationError, SecurityError) as exc:
            return ValidationResult(
                is_valid=False, sanitized_value="", violations=[str(exc)],
                severity=ValidationSeverity.HIGH, original_value=email,
                issues=[ValidationIssue(
                    field="email", message=str(exc),
                    code="INVALID_EMAIL", severity=ValidationSeverity.HIGH,
                )],
            )

    def validate_url(self, url: str) -> ValidationResult:
        """Validate a URL."""
        try:
            cleaned = FieldValidator.validate_url_field(url, sanitizer=self.sanitizer)
            return ValidationResult(
                is_valid=True, sanitized_value=cleaned, violations=[],
                severity=ValidationSeverity.LOW, original_value=url, issues=[],
            )
        except (GraphQLValidationError, SecurityError) as exc:
            return ValidationResult(
                is_valid=False, sanitized_value="", violations=[str(exc)],
                severity=ValidationSeverity.HIGH, original_value=url,
                issues=[ValidationIssue(
                    field="url", message=str(exc),
                    code="INVALID_URL", severity=ValidationSeverity.HIGH,
                )],
            )

    def validate_graphql_input(
        self, input_data: dict[str, Any], schema_definition: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Recursively validate GraphQL input data."""
        results: dict[str, Any] = {}
        for field_name, value in input_data.items():
            if isinstance(value, str):
                results[field_name] = self.validate_string(value)
            elif isinstance(value, dict):
                results[field_name] = self.validate_graphql_input(value, schema_definition)
            elif isinstance(value, list):
                results[field_name] = [
                    self.validate_string(item) if isinstance(item, str)
                    else self.validate_graphql_input(item, schema_definition) if isinstance(item, dict)
                    else item
                    for item in value
                ]
        return results

    def _validate_generic_field(self, field_name: str, value: Any) -> Any:
        """Apply generic validation based on field name heuristics."""
        if value is None:
            return value

        if isinstance(value, str):
            lowered = field_name.lower()
            if "email" in lowered:
                return FieldValidator.validate_email_field(value, sanitizer=self.sanitizer)
            if "url" in lowered or "link" in lowered:
                return FieldValidator.validate_url_field(value, sanitizer=self.sanitizer)
            return FieldValidator.validate_string_field(
                value, max_length=self.settings.max_string_length,
                field_name=field_name, sanitizer=self.sanitizer,
            )

        if isinstance(value, int):
            return FieldValidator.validate_integer_field(value)
        if isinstance(value, float):
            return FieldValidator.validate_decimal_field(value)
        return value

    def _sanitize_value(
        self, value: Any, issues: list[ValidationIssue], path: Optional[str]
    ) -> Any:
        """Recursively sanitize a value."""
        if isinstance(value, Enum):
            return value.value

        if hasattr(value, "__dict__") and not isinstance(value, dict):
            return self._sanitize_value(dict(value.__dict__), issues, path)

        if isinstance(value, dict):
            return {
                key: self._sanitize_value(nested_value, issues, join_path(path, key))
                for key, nested_value in value.items()
            }

        if isinstance(value, list):
            return [
                self._sanitize_value(item, issues, join_list_path(path, idx))
                for idx, item in enumerate(value)
            ]

        if isinstance(value, str):
            result = self.sanitizer.sanitize_string(value, field=path)
            issues.extend(result.issues)
            return result.sanitized_value

        return value

    def _register_default_validators(self, *, force: bool = False) -> None:
        """Register default field validators."""
        self.register_field_validator(
            "email",
            lambda v: FieldValidator.validate_email_field(v, sanitizer=self.sanitizer),
            replace=force,
        )
        self.register_field_validator(
            "url",
            lambda v: FieldValidator.validate_url_field(v, sanitizer=self.sanitizer),
            replace=force,
        )
        self.register_field_validator(
            "website",
            lambda v: FieldValidator.validate_url_field(v, sanitizer=self.sanitizer),
            replace=force,
        )
        self.register_field_validator("password", _validate_password, replace=force)


def _validate_password(value: str) -> str:
    """Validate password meets security requirements."""
    if len(value) < 8:
        raise GraphQLValidationError("Password must be at least 8 characters", field="password")
    if not re.search(r"[A-Z]", value):
        raise GraphQLValidationError("Password must include an uppercase letter", field="password")
    if not re.search(r"[a-z]", value):
        raise GraphQLValidationError("Password must include a lowercase letter", field="password")
    if not re.search(r"\d", value):
        raise GraphQLValidationError("Password must include a number", field="password")
    return value

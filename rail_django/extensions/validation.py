"""
Validation extensions for GraphQL schemas.

This module re-exports the unified input validation components and provides
query helpers for interactive validation checks.
"""

import graphene

from ..core.exceptions import SecurityError
from ..core.exceptions import ValidationError as GraphQLValidationError
from ..security.input_validation import (
    FieldValidator,
    GraphQLInputSanitizer,
    InputSanitizer,
    InputValidator,
    ValidationResult,
    ValidationSeverity,
    input_validator,
    validate_input,
)


__all__ = [
    "InputSanitizer",
    "FieldValidator",
    "InputValidator",
    "ValidationResult",
    "ValidationSeverity",
    "GraphQLInputSanitizer",
    "validate_input",
    "input_validator",
    "ValidationInfo",
    "ValidationQuery",
]


graphql_sanitizer = GraphQLInputSanitizer(validator=input_validator)


class ValidationInfo(graphene.ObjectType):
    """Validation metadata for a single field."""

    field_name = graphene.String(description="Field name")
    is_valid = graphene.Boolean(description="Is the field valid")
    error_message = graphene.String(description="Validation error message")
    sanitized_value = graphene.String(description="Sanitized value")


class ValidationQuery(graphene.ObjectType):
    """Queries for testing input validation."""

    validate_field = graphene.Field(
        ValidationInfo,
        field_name=graphene.String(required=True),
        value=graphene.String(required=True),
        description="Validate a specific field",
    )

    def resolve_validate_field(self, info, field_name: str, value: str):
        try:
            if field_name in input_validator.field_validators:
                sanitized = input_validator.field_validators[field_name](value)
            else:
                sanitized = input_validator._validate_generic_field(field_name, value)

            return ValidationInfo(
                field_name=field_name,
                is_valid=True,
                error_message=None,
                sanitized_value=str(sanitized),
            )
        except (GraphQLValidationError, SecurityError) as exc:
            return ValidationInfo(
                field_name=field_name,
                is_valid=False,
                error_message=str(exc),
                sanitized_value=None,
            )

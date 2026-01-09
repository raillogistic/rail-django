"""
Error handling classes for schema validation.

This module provides custom exception classes and error handling utilities
for schema validation operations.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SchemaRegistryError(Exception):
    """Base exception for schema registry operations."""

    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or 'SCHEMA_REGISTRY_ERROR'
        self.details = details or {}


class SchemaValidationError(SchemaRegistryError):
    """Schema validation failed."""

    def __init__(self, message: str, field: str = None, validation_errors: List[str] = None):
        super().__init__(message, 'SCHEMA_VALIDATION_ERROR')
        self.field = field
        self.validation_errors = validation_errors or []


class SchemaConflictError(SchemaRegistryError):
    """Schema conflict detected."""

    def __init__(self, message: str, conflicting_schema: str = None, conflict_type: str = None):
        super().__init__(message, 'SCHEMA_CONFLICT_ERROR')
        self.conflicting_schema = conflicting_schema
        self.conflict_type = conflict_type


class SchemaNotFoundError(SchemaRegistryError):
    """Schema not found."""

    def __init__(self, schema_name: str):
        message = f"Schema '{schema_name}' not found"
        super().__init__(message, 'SCHEMA_NOT_FOUND')
        self.schema_name = schema_name


class InvalidSchemaConfigError(SchemaRegistryError):
    """Invalid schema configuration."""

    def __init__(self, message: str, config_field: str = None):
        super().__init__(message, 'INVALID_SCHEMA_CONFIG')
        self.config_field = config_field


@dataclass
class ValidationError:
    """Represents a single validation error."""
    field: Optional[str]
    message: str
    code: str
    severity: str = 'error'  # 'error', 'warning', 'info'


class ValidationErrorHandler:
    """Handles and formats validation errors."""

    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    def add_error(self, field: str, message: str, code: str = 'VALIDATION_ERROR'):
        """Add a validation error."""
        error = ValidationError(field=field, message=message, code=code, severity='error')
        self.errors.append(error)
        logger.error(f"Validation error in field '{field}': {message}")

    def add_warning(self, field: str, message: str, code: str = 'VALIDATION_WARNING'):
        """Add a validation warning."""
        warning = ValidationError(field=field, message=message, code=code, severity='warning')
        self.warnings.append(warning)
        logger.warning(f"Validation warning in field '{field}': {message}")

    def add_info(self, field: str, message: str, code: str = 'VALIDATION_INFO'):
        """Add a validation info message."""
        info = ValidationError(field=field, message=message, code=code, severity='info')
        logger.info(f"Validation info for field '{field}': {message}")

    def has_errors(self) -> bool:
        """Check if there are any validation errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any validation warnings."""
        return len(self.warnings) > 0

    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of all validation issues."""
        return {
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'errors': [
                {
                    'field': error.field,
                    'message': error.message,
                    'code': error.code,
                    'severity': error.severity
                }
                for error in self.errors
            ],
            'warnings': [
                {
                    'field': warning.field,
                    'message': warning.message,
                    'code': warning.code,
                    'severity': warning.severity
                }
                for warning in self.warnings
            ]
        }

    def clear(self):
        """Clear all errors and warnings."""
        self.errors.clear()
        self.warnings.clear()

    def raise_if_errors(self):
        """Raise SchemaValidationError if there are any errors."""
        if self.has_errors():
            error_messages = [error.message for error in self.errors]
            raise SchemaValidationError(
                message=f"Schema validation failed with {len(self.errors)} error(s)",
                validation_errors=error_messages
            )


def handle_validation_exception(func):
    """Decorator to handle validation exceptions and convert them to structured errors."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SchemaRegistryError:
            # Re-raise schema registry errors as-is
            raise
        except Exception as e:
            # Convert other exceptions to schema registry errors
            logger.exception(f"Unexpected error in {func.__name__}")
            raise SchemaRegistryError(
                message=f"Unexpected error: {str(e)}",
                error_code='UNEXPECTED_ERROR',
                details={'original_exception': type(e).__name__}
            )
    return wrapper

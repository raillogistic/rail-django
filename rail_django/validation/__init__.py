"""
Schema validation and error handling module.

This module provides comprehensive validation capabilities for GraphQL schemas,
including schema configuration validation, GraphQL schema validation, and
enhanced error handling.
"""

from .error_handlers import (
    SchemaConflictError,
    SchemaRegistryError,
    SchemaValidationError,
    ValidationErrorHandler,
)
from .schema_validator import SchemaValidator, ValidationResult

__all__ = [
    'SchemaValidator',
    'ValidationResult',
    'SchemaRegistryError',
    'SchemaValidationError',
    'SchemaConflictError',
    'ValidationErrorHandler'
]

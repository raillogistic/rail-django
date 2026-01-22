"""
Custom exceptions for mutation operations.

This module provides specialized exception types for mutation operations,
allowing for more precise error handling and better error messages.
"""

from typing import Optional


class MutationError(Exception):
    """Base exception for mutation operations."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        code: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code

    def __str__(self) -> str:
        return self.message


class NestedDepthError(MutationError):
    """Raised when nested operation exceeds maximum depth."""

    def __init__(self, max_depth: int, current_depth: int):
        super().__init__(
            f"Nested operation exceeds maximum depth of {max_depth}. "
            f"Current depth: {current_depth}",
            code="DEPTH_EXCEEDED",
        )
        self.max_depth = max_depth
        self.current_depth = current_depth


class BulkSizeError(MutationError):
    """Raised when bulk operation exceeds maximum size."""

    def __init__(self, max_size: int, actual_size: int):
        super().__init__(
            f"Bulk operation exceeds maximum size of {max_size} items. "
            f"Received: {actual_size}",
            code="BULK_SIZE_EXCEEDED",
        )
        self.max_size = max_size
        self.actual_size = actual_size


class CircularReferenceError(MutationError):
    """Raised when circular reference is detected in nested data."""

    def __init__(self, model_name: str, path: str = ""):
        super().__init__(
            f"Circular reference detected in nested data for {model_name}."
            + (f" Path: {path}" if path else ""),
            code="CIRCULAR_REFERENCE",
        )
        self.model_name = model_name
        self.path = path


class TenantAccessError(MutationError):
    """Raised when tenant access is denied."""

    def __init__(self, model_name: str, operation: str):
        super().__init__(
            f"Tenant access denied for {operation} on {model_name}",
            code="TENANT_ACCESS_DENIED",
        )
        self.model_name = model_name
        self.operation = operation


class InvalidIdFormatError(MutationError):
    """Raised when an ID has an invalid format."""

    def __init__(self, field_name: str, value: str):
        super().__init__(
            f"Invalid ID format for field '{field_name}': {value!r}",
            field=field_name,
            code="INVALID_ID_FORMAT",
        )
        self.value = value


class RelatedObjectNotFoundError(MutationError):
    """Raised when a related object is not found."""

    def __init__(self, model_name: str, field_name: str, pk_value: str):
        super().__init__(
            f"{model_name} with id '{pk_value}' not found",
            field=field_name,
            code="RELATED_OBJECT_NOT_FOUND",
        )
        self.model_name = model_name
        self.pk_value = pk_value


class NestedOperationDisabledError(MutationError):
    """Raised when nested operations are disabled for a field."""

    def __init__(self, model_name: str, field_name: str):
        super().__init__(
            f"Nested operations are disabled for {model_name}.{field_name}. "
            f"Use ID references instead.",
            field=field_name,
            code="NESTED_OPERATION_DISABLED",
        )
        self.model_name = model_name

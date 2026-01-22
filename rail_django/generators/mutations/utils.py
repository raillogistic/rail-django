"""
Shared utilities for mutation generators.

This module provides common utility functions used across all mutation types,
reducing code duplication and ensuring consistent behavior.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional, Type

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# Default limits for mutation operations
DEFAULT_MAX_BULK_SIZE = 100
DEFAULT_MAX_NESTED_DEPTH = 10


# Internationalized error messages
ERROR_ID_REQUIRED_FOR_UPDATE = _("ID is required for update operations.")
ERROR_DUPLICATE_VALUE = _("Duplicate value: field '{field}' already exists.")
ERROR_FIELD_REQUIRED = _("Field '{field}' cannot be null.")
ERROR_BULK_SIZE_EXCEEDED = _(
    "Bulk operation exceeds maximum size of {max_size} items. Received: {actual_size}"
)
ERROR_DEPTH_EXCEEDED = _(
    "Nested operation exceeds maximum depth of {max_depth}. Current depth: {current_depth}"
)
ERROR_OBJECT_NOT_FOUND = _("{model_name} with id '{pk}' not found.")
ERROR_INVALID_ID_FORMAT = _("Invalid ID format for field '{field}': '{value}'")
ERROR_GENERIC_OPERATION = _("An error occurred while processing {operation}.")


def sanitize_input_data(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize input data for safe processing.

    - Converts non-string IDs to strings for consistent handling
    - Strips whitespace from string values
    - Recursively sanitizes nested dictionaries and lists

    Args:
        input_data: Raw input data from GraphQL mutation

    Returns:
        Sanitized input data
    """
    if not input_data:
        return {}

    sanitized = {}
    for key, value in input_data.items():
        if key == "id" and value is not None:
            sanitized[key] = str(value)
        elif isinstance(value, str):
            sanitized[key] = value.strip()
        elif isinstance(value, dict):
            sanitized[key] = sanitize_input_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_input_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def normalize_enum_inputs(
    input_data: Dict[str, Any],
    model: Type[models.Model],
) -> Dict[str, Any]:
    """
    Normalize GraphQL enum values to Django model values.

    Handles Graphene Enum objects by extracting their underlying value.

    Args:
        input_data: Input data that may contain enum values
        model: Django model for field introspection

    Returns:
        Input data with enum values normalized to their underlying types
    """
    if not input_data:
        return {}

    normalized = dict(input_data)

    # Build a map of choice fields for this model
    choice_fields = {
        f.name: f
        for f in model._meta.get_fields()
        if hasattr(f, "choices") and getattr(f, "choices", None)
    }

    def normalize_value(value: Any) -> Any:
        """Recursively normalize enum values."""
        if hasattr(value, "value") and not isinstance(value, (str, bytes)):
            try:
                return getattr(value, "value")
            except Exception:
                return value
        if isinstance(value, list):
            return [normalize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: normalize_value(v) for k, v in value.items()}
        return value

    for field_name in choice_fields.keys():
        if field_name in normalized:
            normalized[field_name] = normalize_value(normalized[field_name])

    return normalized


def get_mandatory_fields(model: Type[models.Model]) -> List[str]:
    """
    Get mandatory fields from model metadata or field definitions.

    Checks GraphQLMeta for explicit mandatory_fields configuration first,
    then falls back to introspecting model field definitions.

    Args:
        model: Django model class

    Returns:
        List of field names that are mandatory for this model
    """
    from ..core.meta import get_model_graphql_meta

    # Check GraphQLMeta first
    graphql_meta = get_model_graphql_meta(model)
    if hasattr(graphql_meta, "mandatory_fields"):
        return list(graphql_meta.mandatory_fields)

    # Fall back to model field definitions
    mandatory = []
    for field in model._meta.get_fields():
        if not hasattr(field, "blank") or not hasattr(field, "null"):
            continue
        if field.name in ("id", "pk"):
            continue
        if hasattr(field, "primary_key") and field.primary_key:
            continue

        has_default = (
            hasattr(field, "default") and field.default is not models.NOT_PROVIDED
        ) or (hasattr(field, "has_default") and field.has_default())

        if not field.blank and not field.null and not has_default:
            mandatory.append(field.name)

    return mandatory


def normalize_pk(pk_value: Any) -> str:
    """
    Normalize PK to string for consistent comparison.

    Args:
        pk_value: Primary key value (int, str, UUID, etc.)

    Returns:
        String representation of the primary key
    """
    if pk_value is None:
        return ""
    return str(pk_value)


def sanitize_error_message(
    exc: Exception,
    operation: str,
    model_name: str,
) -> str:
    """
    Return user-safe error message while logging full details.

    Prevents internal error details from being exposed to users while
    ensuring full error information is logged for debugging.

    Args:
        exc: The exception that occurred
        operation: The operation type (create, update, delete)
        model_name: Name of the model being operated on

    Returns:
        User-safe error message string
    """
    from graphql import GraphQLError

    logger.exception(
        f"Mutation error during {operation} on {model_name}",
        extra={"model": model_name, "operation": operation},
    )

    # Known safe exceptions - return their message
    if isinstance(exc, ValidationError):
        return str(exc)
    if isinstance(exc, PermissionDenied):
        return str(exc)
    if isinstance(exc, GraphQLError):
        return str(exc)

    # Generic message for unknown errors
    return str(ERROR_GENERIC_OPERATION).format(operation=operation)


def validate_and_normalize_pk(
    value: Any,
    field_name: str,
) -> Any:
    """
    Validate and normalize a primary key value.

    Handles various PK formats including integers, UUIDs, and Relay global IDs.

    Args:
        value: The primary key value to normalize
        field_name: Name of the field for error messages

    Returns:
        Normalized primary key value

    Raises:
        ValueError: If the ID format is invalid
    """
    from .exceptions import InvalidIdFormatError

    if value is None:
        return None

    # Already an integer
    if isinstance(value, int):
        return value

    # UUID instance
    if isinstance(value, uuid.UUID):
        return value

    # String handling
    if isinstance(value, str):
        # Check if it's a valid UUID
        try:
            uuid.UUID(value)
            return value  # Keep as string for UUID fields
        except ValueError:
            pass

        # Check if it's a numeric ID
        if value.isdigit():
            return int(value)

        # Check if it's a Relay global ID
        try:
            from graphql_relay import from_global_id

            type_name, decoded_id = from_global_id(value)
            if decoded_id:
                return int(decoded_id) if decoded_id.isdigit() else decoded_id
        except Exception:
            pass

        # If we reach here, keep the string as-is (might be a slug or custom PK)
        return value

    # For model instances, extract the PK
    if hasattr(value, "pk"):
        return value.pk

    raise InvalidIdFormatError(field_name, str(value))


def resolve_fk_id(
    value: Any,
    related_model: Type[models.Model],
    queryset: Optional[models.QuerySet] = None,
    field_name: str = "id",
) -> Optional[models.Model]:
    """
    Resolve a foreign key ID to its related object.

    Handles string IDs, integer IDs, and Relay global IDs.

    Args:
        value: The ID value to resolve
        related_model: The related model class
        queryset: Optional queryset to use (for tenant scoping)
        field_name: Field name for error messages

    Returns:
        The related model instance

    Raises:
        ValueError: If the related object is not found
    """
    from .exceptions import RelatedObjectNotFoundError

    if value is None:
        return None

    # Already a model instance
    if hasattr(value, "pk"):
        return value

    # Normalize the PK value
    pk_value = validate_and_normalize_pk(value, field_name)

    # Get queryset
    if queryset is None:
        queryset = related_model.objects.all()

    try:
        return queryset.get(pk=pk_value)
    except related_model.DoesNotExist:
        raise RelatedObjectNotFoundError(
            related_model.__name__, field_name, str(value)
        )


def wrap_with_audit(
    model: Type[models.Model],
    operation: str,
    func: callable,
) -> callable:
    """
    Wrap a function with audit logging if available.

    Returns the original function if audit logging is not configured.

    Args:
        model: The model being operated on
        operation: The operation type (create, update, delete)
        func: The function to wrap

    Returns:
        The wrapped function or the original if audit is not available
    """
    try:
        from ..security.audit_logging import audit_data_modification

        def audited_func(info, instance, *args, **kwargs):
            result = func(info, instance, *args, **kwargs)
            audit_data_modification(
                info=info,
                model=model,
                operation=operation,
                instance=result or instance,
            )
            return result

        return audited_func

    except ImportError:
        logger.debug("Audit logging not available")
        return func
    except Exception as e:
        logger.warning(f"Failed to setup audit wrapper: {e}")
        return func


def check_bulk_size_limit(
    inputs: List[Any],
    max_size: Optional[int] = None,
) -> None:
    """
    Check if bulk operation inputs exceed the maximum size limit.

    Args:
        inputs: List of input items
        max_size: Maximum allowed size (defaults to DEFAULT_MAX_BULK_SIZE)

    Raises:
        BulkSizeError: If the inputs exceed the maximum size
    """
    from .exceptions import BulkSizeError

    if max_size is None:
        max_size = DEFAULT_MAX_BULK_SIZE

    if len(inputs) > max_size:
        raise BulkSizeError(max_size, len(inputs))


def check_nested_depth(
    current_depth: int,
    max_depth: Optional[int] = None,
) -> None:
    """
    Check if current nesting depth exceeds the maximum depth limit.

    Args:
        current_depth: Current nesting depth
        max_depth: Maximum allowed depth (defaults to DEFAULT_MAX_NESTED_DEPTH)

    Raises:
        NestedDepthError: If the depth exceeds the maximum
    """
    from .exceptions import NestedDepthError

    if max_depth is None:
        max_depth = DEFAULT_MAX_NESTED_DEPTH

    if current_depth > max_depth:
        raise NestedDepthError(max_depth, current_depth)

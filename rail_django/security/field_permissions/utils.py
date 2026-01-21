"""
Utility functions for field-level permissions.

This module provides helper functions for masking sensitive fields
and other field permission-related utilities.
"""

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
    Set,
    Type,
)

from django.db import models

from .types import (
    FieldContext,
    FieldVisibility,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def mask_sensitive_fields(
    data: Dict[str, Any],
    user: "AbstractUser",
    model_class: Type[models.Model],
    instance: Optional[models.Model] = None,
) -> Dict[str, Any]:
    """
    Mask sensitive fields in a data dictionary.

    This function iterates through all fields in the data dictionary and
    applies appropriate masking based on the user's permissions and the
    field's visibility settings.

    Args:
        data: Dictionary of field names to values.
        user: The user accessing the data.
        model_class: The Django model class.
        instance: Optional model instance for context-aware masking.

    Returns:
        Dictionary with sensitive fields appropriately masked or removed.

    Example:
        >>> data = {"name": "John", "salary": 50000, "ssn": "123-45-6789"}
        >>> masked = mask_sensitive_fields(data, user, Employee, employee)
        >>> masked
        {"name": "John", "salary": "***CONFIDENTIAL***", "ssn": "12****89"}
    """
    # Import here to avoid circular imports
    from .manager import field_permission_manager

    if user is None:
        return {}

    result = data.copy()

    for field_name, value in data.items():
        context = FieldContext(
            user=user,
            instance=instance,
            field_name=field_name,
            operation_type="read",
            model_class=model_class,
        )

        visibility, mask_value = field_permission_manager.get_field_visibility(context)

        if visibility == FieldVisibility.HIDDEN:
            result.pop(field_name, None)
        elif visibility == FieldVisibility.MASKED:
            result[field_name] = mask_value
        elif visibility == FieldVisibility.REDACTED and value:
            result[field_name] = redact_value(value)

    return result


def redact_value(value: Any) -> str:
    """
    Redact a value by keeping first and last characters visible.

    This function partially censors a value by showing only the first
    two and last two characters, with asterisks in between.

    Args:
        value: The value to redact.

    Returns:
        Redacted string with partial visibility.

    Example:
        >>> redact_value("1234567890")
        "12******90"
        >>> redact_value("abc")
        "****"
    """
    if isinstance(value, str) and len(value) > 4:
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    return "****"


def filter_visible_fields(
    fields: Dict[str, Any],
    user: "AbstractUser",
    model_class: Type[models.Model],
    instance: Optional[models.Model] = None,
) -> Set[str]:
    """
    Get the set of field names that are visible to a user.

    This function returns only the names of fields that the user
    is allowed to see (i.e., not hidden).

    Args:
        fields: Dictionary of field names to values.
        user: The user accessing the data.
        model_class: The Django model class.
        instance: Optional model instance for context-aware checks.

    Returns:
        Set of field names that are visible to the user.

    Example:
        >>> fields = {"name": "John", "salary": 50000, "password": "secret"}
        >>> visible = filter_visible_fields(fields, user, Employee)
        >>> visible
        {"name", "salary"}  # password is hidden
    """
    from .manager import field_permission_manager

    if user is None:
        return set()

    visible_fields: Set[str] = set()

    for field_name in fields.keys():
        context = FieldContext(
            user=user,
            instance=instance,
            field_name=field_name,
            operation_type="read",
            model_class=model_class,
        )

        visibility, _ = field_permission_manager.get_field_visibility(context)

        if visibility != FieldVisibility.HIDDEN:
            visible_fields.add(field_name)

    return visible_fields


def get_readable_fields(
    user: "AbstractUser",
    model_class: Type[models.Model],
    instance: Optional[models.Model] = None,
) -> Set[str]:
    """
    Get all field names that a user can read from a model.

    This function examines all fields on a model and returns the names
    of those that the user has at least READ access to.

    Args:
        user: The user accessing the data.
        model_class: The Django model class.
        instance: Optional model instance for context-aware checks.

    Returns:
        Set of field names the user can read.

    Example:
        >>> readable = get_readable_fields(user, Employee)
        >>> readable
        {"id", "name", "department", "hire_date"}
    """
    from .manager import field_permission_manager
    from .types import FieldAccessLevel

    if user is None:
        return set()

    readable_fields: Set[str] = set()

    for field in model_class._meta.get_fields():
        if field.name.startswith("_"):
            continue

        context = FieldContext(
            user=user,
            instance=instance,
            field_name=field.name,
            operation_type="read",
            model_class=model_class,
        )

        access_level = field_permission_manager.get_field_access_level(context)

        if access_level in [
            FieldAccessLevel.READ,
            FieldAccessLevel.WRITE,
            FieldAccessLevel.ADMIN,
        ]:
            readable_fields.add(field.name)

    return readable_fields


def get_writable_fields(
    user: "AbstractUser",
    model_class: Type[models.Model],
    instance: Optional[models.Model] = None,
) -> Set[str]:
    """
    Get all field names that a user can write to on a model.

    This function examines all fields on a model and returns the names
    of those that the user has WRITE or ADMIN access to.

    Args:
        user: The user accessing the data.
        model_class: The Django model class.
        instance: Optional model instance for context-aware checks.

    Returns:
        Set of field names the user can write to.

    Example:
        >>> writable = get_writable_fields(user, Employee)
        >>> writable
        {"name", "department"}  # User can modify these fields
    """
    from .manager import field_permission_manager
    from .types import FieldAccessLevel

    if user is None:
        return set()

    writable_fields: Set[str] = set()

    for field in model_class._meta.get_fields():
        if field.name.startswith("_"):
            continue

        context = FieldContext(
            user=user,
            instance=instance,
            field_name=field.name,
            operation_type="write",
            model_class=model_class,
        )

        access_level = field_permission_manager.get_field_access_level(context)

        if access_level in [FieldAccessLevel.WRITE, FieldAccessLevel.ADMIN]:
            writable_fields.add(field.name)

    return writable_fields


def validate_field_access(
    user: "AbstractUser",
    model_class: Type[models.Model],
    field_names: Set[str],
    operation: str = "read",
    instance: Optional[models.Model] = None,
) -> Dict[str, bool]:
    """
    Validate access to multiple fields at once.

    This function checks whether a user has access to each of the
    specified fields and returns a dictionary indicating access status.

    Args:
        user: The user accessing the data.
        model_class: The Django model class.
        field_names: Set of field names to check.
        operation: Type of operation (read, write, create, update, delete).
        instance: Optional model instance for context-aware checks.

    Returns:
        Dictionary mapping field names to access status (True/False).

    Example:
        >>> fields = {"name", "salary", "ssn"}
        >>> access = validate_field_access(user, Employee, fields)
        >>> access
        {"name": True, "salary": True, "ssn": False}
    """
    from .manager import field_permission_manager
    from .types import FieldAccessLevel

    if user is None:
        return {field: False for field in field_names}

    result: Dict[str, bool] = {}

    required_level = (
        FieldAccessLevel.WRITE
        if operation in ["write", "create", "update", "delete"]
        else FieldAccessLevel.READ
    )

    for field_name in field_names:
        context = FieldContext(
            user=user,
            instance=instance,
            field_name=field_name,
            operation_type=operation,
            model_class=model_class,
        )

        access_level = field_permission_manager.get_field_access_level(context)

        from .types import ACCESS_LEVEL_HIERARCHY

        result[field_name] = (
            ACCESS_LEVEL_HIERARCHY[access_level]
            >= ACCESS_LEVEL_HIERARCHY[required_level]
        )

    return result


def apply_field_masks(
    queryset_values: list[Dict[str, Any]],
    user: "AbstractUser",
    model_class: Type[models.Model],
) -> list[Dict[str, Any]]:
    """
    Apply field masking to a list of queryset value dictionaries.

    This is a convenience function for applying masking to the results
    of a QuerySet.values() call.

    Args:
        queryset_values: List of dictionaries from QuerySet.values().
        user: The user accessing the data.
        model_class: The Django model class.

    Returns:
        List of dictionaries with appropriate fields masked.

    Example:
        >>> employees = list(Employee.objects.values("name", "salary", "ssn"))
        >>> masked = apply_field_masks(employees, user, Employee)
    """
    return [
        mask_sensitive_fields(record, user, model_class) for record in queryset_values
    ]


def is_field_sensitive(field_name: str) -> bool:
    """
    Check if a field name matches common sensitive field patterns.

    This is a quick check based on field naming conventions without
    requiring the full permission manager context.

    Args:
        field_name: Name of the field to check.

    Returns:
        True if the field name suggests sensitive data.

    Example:
        >>> is_field_sensitive("password")
        True
        >>> is_field_sensitive("username")
        False
    """
    sensitive_patterns = {
        "password",
        "token",
        "secret",
        "key",
        "hash",
        "ssn",
        "social_security",
        "credit_card",
        "bank_account",
        "api_key",
        "private_key",
        "auth_token",
        "refresh_token",
        "access_token",
    }

    field_lower = field_name.lower()
    return any(pattern in field_lower for pattern in sensitive_patterns)


def create_field_context(
    user: "AbstractUser",
    field_name: str,
    model_class: Type[models.Model],
    instance: Optional[models.Model] = None,
    operation_type: str = "read",
    request_context: Optional[Dict[str, Any]] = None,
) -> FieldContext:
    """
    Factory function to create a FieldContext instance.

    This is a convenience function for creating FieldContext objects
    with sensible defaults.

    Args:
        user: The user accessing the field.
        field_name: Name of the field being accessed.
        model_class: The Django model class.
        instance: Optional model instance.
        operation_type: Type of operation (read, write, etc.).
        request_context: Additional request context.

    Returns:
        Configured FieldContext instance.

    Example:
        >>> context = create_field_context(
        ...     user=request.user,
        ...     field_name="salary",
        ...     model_class=Employee,
        ...     operation_type="read",
        ... )
    """
    return FieldContext(
        user=user,
        instance=instance,
        field_name=field_name,
        operation_type=operation_type,
        request_context=request_context,
        model_class=model_class,
    )

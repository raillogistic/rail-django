"""
Type definitions for the field permissions system.

This module provides:
- FieldAccessLevel enum for access level definitions
- FieldVisibility enum for visibility state definitions
- FieldPermissionRule dataclass for permission rule configuration
- FieldContext dataclass for access context information
"""

from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    Set,
    Type,
)

from django.db import models

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class FieldAccessLevel(Enum):
    """
    Access levels for fields.

    Defines the level of access a user has to a specific field:
    - NONE: No access allowed
    - READ: Read-only access
    - WRITE: Read and write access
    - ADMIN: Full administrative access
    """

    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class FieldVisibility(Enum):
    """
    Visibility states for fields.

    Defines how a field value should be displayed:
    - VISIBLE: Field is fully visible
    - HIDDEN: Field is completely hidden from output
    - MASKED: Field value is replaced with a mask value
    - REDACTED: Field value is partially censored (e.g., ab****cd)
    """

    VISIBLE = "visible"
    HIDDEN = "hidden"
    MASKED = "masked"
    REDACTED = "redacted"


@dataclass
class FieldPermissionRule:
    """
    Permission rule configuration for a field.

    Attributes:
        field_name: Name of the field this rule applies to. Supports wildcards (*).
        model_name: Name of the model this rule applies to. Use "*" for all models.
        access_level: The access level granted by this rule.
        visibility: The visibility state for the field.
        condition: Optional callable that receives FieldContext and returns bool.
        mask_value: Value to display when visibility is MASKED.
        roles: List of role names that this rule applies to.
        permissions: List of Django permission strings required.
        context_required: Whether request context is required for evaluation.

    Example:
        >>> rule = FieldPermissionRule(
        ...     field_name="salary",
        ...     model_name="Employee",
        ...     access_level=FieldAccessLevel.READ,
        ...     visibility=FieldVisibility.VISIBLE,
        ...     roles=["manager", "hr"],
        ... )
    """

    field_name: str
    model_name: str
    access_level: FieldAccessLevel
    visibility: FieldVisibility
    condition: Optional[Callable] = None
    mask_value: Any = None
    roles: Optional[list[str]] = None
    permissions: Optional[list[str]] = None
    context_required: bool = False


@dataclass
class FieldContext:
    """
    Context information for field access evaluation.

    This dataclass encapsulates all the information needed to evaluate
    field-level permissions, including the user, the instance being accessed,
    and additional metadata.

    Attributes:
        user: The user attempting to access the field.
        instance: The model instance being accessed (optional).
        parent_instance: Parent instance for nested relationships (optional).
        field_name: Name of the field being accessed.
        operation_type: Type of operation (read, write, create, update, delete).
        request_context: Additional context from the request.
        model_class: The model class (used when instance is not available).
        classifications: Set of classification tags for the field/model.

    Example:
        >>> context = FieldContext(
        ...     user=request.user,
        ...     instance=employee,
        ...     field_name="salary",
        ...     operation_type="read",
        ... )
    """

    user: "AbstractUser"
    instance: Optional[models.Model] = None
    parent_instance: Optional[models.Model] = None
    field_name: Optional[str] = None
    operation_type: str = "read"
    request_context: Optional[dict[str, Any]] = None
    model_class: Optional[Type[models.Model]] = None
    classifications: Optional[Set[str]] = None


# Access level hierarchy for comparison operations
ACCESS_LEVEL_HIERARCHY: dict[FieldAccessLevel, int] = {
    FieldAccessLevel.NONE: 0,
    FieldAccessLevel.READ: 1,
    FieldAccessLevel.WRITE: 2,
    FieldAccessLevel.ADMIN: 3,
}


def compare_access_levels(level1: FieldAccessLevel, level2: FieldAccessLevel) -> int:
    """
    Compare two access levels.

    Args:
        level1: First access level to compare.
        level2: Second access level to compare.

    Returns:
        Negative if level1 < level2, zero if equal, positive if level1 > level2.

    Example:
        >>> compare_access_levels(FieldAccessLevel.READ, FieldAccessLevel.ADMIN)
        -2
    """
    return ACCESS_LEVEL_HIERARCHY[level1] - ACCESS_LEVEL_HIERARCHY[level2]


def access_level_sufficient(
    user_level: FieldAccessLevel, required_level: FieldAccessLevel
) -> bool:
    """
    Check if a user's access level meets the required level.

    Args:
        user_level: The access level the user has.
        required_level: The minimum access level required.

    Returns:
        True if user_level >= required_level, False otherwise.

    Example:
        >>> access_level_sufficient(FieldAccessLevel.ADMIN, FieldAccessLevel.READ)
        True
        >>> access_level_sufficient(FieldAccessLevel.READ, FieldAccessLevel.WRITE)
        False
    """
    return compare_access_levels(user_level, required_level) >= 0

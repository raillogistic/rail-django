"""
Field-level permissions system for Django GraphQL.

This package provides comprehensive field-level permission management:
- Dynamic per-field permissions
- Relationship-based filtering
- Conditional field masking
- Real-time access validation

Example usage:
    >>> from rail_django.security.field_permissions import (
    ...     field_permission_manager,
    ...     FieldAccessLevel,
    ...     FieldVisibility,
    ...     FieldPermissionRule,
    ...     FieldContext,
    ...     field_permission_required,
    ...     mask_sensitive_fields,
    ... )
    >>>
    >>> # Register a custom permission rule
    >>> rule = FieldPermissionRule(
    ...     field_name="salary",
    ...     model_name="Employee",
    ...     access_level=FieldAccessLevel.READ,
    ...     visibility=FieldVisibility.VISIBLE,
    ...     roles=["hr", "manager"],
    ... )
    >>> field_permission_manager.register_field_rule(rule)
    >>>
    >>> # Use the decorator on a resolver
    >>> @field_permission_required("salary", FieldAccessLevel.READ)
    ... def resolve_salary(root, info):
    ...     return root.salary
    >>>
    >>> # Mask sensitive fields in a data dictionary
    >>> data = {"name": "John", "salary": 50000}
    >>> masked = mask_sensitive_fields(data, user, Employee)
"""

# Types and enums
from .types import (
    ACCESS_LEVEL_HIERARCHY,
    FieldAccessLevel,
    FieldContext,
    FieldPermissionRule,
    FieldVisibility,
    access_level_sufficient,
    compare_access_levels,
)

# Manager and global instance
from .manager import (
    FieldPermissionManager,
    field_permission_manager,
)

# Decorators
from .decorators import (
    check_admin_permission,
    check_write_permission,
    field_permission_required,
    require_field_visibility,
)

# Utility functions
from .utils import (
    apply_field_masks,
    create_field_context,
    filter_visible_fields,
    get_readable_fields,
    get_writable_fields,
    is_field_sensitive,
    mask_sensitive_fields,
    redact_value,
    validate_field_access,
)

# Default configuration
from .defaults import (
    DEFAULT_CLASSIFICATION_PATTERNS,
    DEFAULT_SENSITIVE_FIELDS,
    FINANCIAL_FIELDS,
    is_owner_or_admin,
    setup_default_rules,
)

__all__ = [
    # Enums
    "FieldAccessLevel",
    "FieldVisibility",
    # Dataclasses
    "FieldPermissionRule",
    "FieldContext",
    # Constants
    "ACCESS_LEVEL_HIERARCHY",
    "DEFAULT_SENSITIVE_FIELDS",
    "DEFAULT_CLASSIFICATION_PATTERNS",
    "FINANCIAL_FIELDS",
    # Type helper functions
    "compare_access_levels",
    "access_level_sufficient",
    # Manager class and instance
    "FieldPermissionManager",
    "field_permission_manager",
    # Decorators
    "field_permission_required",
    "require_field_visibility",
    "check_write_permission",
    "check_admin_permission",
    # Utility functions
    "mask_sensitive_fields",
    "redact_value",
    "filter_visible_fields",
    "get_readable_fields",
    "get_writable_fields",
    "validate_field_access",
    "apply_field_masks",
    "is_field_sensitive",
    "create_field_context",
    # Default configuration functions
    "is_owner_or_admin",
    "setup_default_rules",
]

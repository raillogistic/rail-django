"""
Default configuration and rules for field permissions.

This module contains default sensitive field patterns, classification
defaults, and the default rule setup for the FieldPermissionManager.
"""

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from .manager import FieldPermissionManager
    from .types import FieldContext

# Default sensitive field patterns
DEFAULT_SENSITIVE_FIELDS: Set[str] = {
    "password",
    "token",
    "secret",
    "key",
    "hash",
    "ssn",
    "social_security",
    "credit_card",
    "bank_account",
}

# Default classification patterns by category
DEFAULT_CLASSIFICATION_PATTERNS: dict[str, Set[str]] = {
    "pii": {
        "email",
        "phone",
        "ssn",
        "social_security",
        "address",
    },
    "financial": {
        "salary",
        "wage",
        "income",
        "revenue",
        "cost",
        "price",
        "credit_card",
        "bank_account",
    },
    "credential": {
        "password",
        "token",
        "secret",
        "key",
        "hash",
    },
}

# Financial field names that require restricted access
FINANCIAL_FIELDS: list[str] = [
    "salary",
    "wage",
    "income",
    "revenue",
    "cost",
    "price",
]


def setup_default_rules(manager: "FieldPermissionManager") -> None:
    """
    Configure default rules for sensitive fields on a manager instance.

    Args:
        manager: The FieldPermissionManager to configure.
    """
    from .types import FieldAccessLevel, FieldPermissionRule, FieldVisibility

    # Password fields - always hidden
    manager.register_field_rule(
        FieldPermissionRule(
            field_name="password",
            model_name="*",
            access_level=FieldAccessLevel.NONE,
            visibility=FieldVisibility.HIDDEN,
        )
    )

    # Token fields - visible for admin, masked for others
    manager.register_field_rule(
        FieldPermissionRule(
            field_name="*token*",
            model_name="*",
            access_level=FieldAccessLevel.READ,
            visibility=FieldVisibility.VISIBLE,
            roles=["admin", "superadmin"],
        )
    )
    manager.register_field_rule(
        FieldPermissionRule(
            field_name="*token*",
            model_name="*",
            access_level=FieldAccessLevel.READ,
            visibility=FieldVisibility.MASKED,
            mask_value="***HIDDEN***",
        )
    )

    # Email - visible for owner and admin
    manager.register_field_rule(
        FieldPermissionRule(
            field_name="email",
            model_name="User",
            access_level=FieldAccessLevel.READ,
            visibility=FieldVisibility.VISIBLE,
            condition=is_owner_or_admin,
        )
    )

    # Financial fields - restricted access
    for field in FINANCIAL_FIELDS:
        manager.register_field_rule(
            FieldPermissionRule(
                field_name=field,
                model_name="*",
                access_level=FieldAccessLevel.READ,
                visibility=FieldVisibility.VISIBLE,
                roles=["manager", "admin", "superadmin"],
            )
        )
        manager.register_field_rule(
            FieldPermissionRule(
                field_name=field,
                model_name="*",
                access_level=FieldAccessLevel.READ,
                visibility=FieldVisibility.MASKED,
                mask_value="***CONFIDENTIAL***",
            )
        )


def is_owner_or_admin(context: "FieldContext") -> bool:
    """
    Check if the user is owner of the object or an administrator.

    Args:
        context: Access context.

    Returns:
        True if user is owner or admin.
    """
    from django.contrib.auth import get_user_model

    if context.user.is_staff or context.user.is_superuser:
        return True

    if context.instance:
        if hasattr(context.instance, "owner"):
            return context.instance.owner == context.user
        elif hasattr(context.instance, "created_by"):
            return context.instance.created_by == context.user
        elif hasattr(context.instance, "user"):
            return context.instance.user == context.user
        elif isinstance(context.instance, get_user_model()):
            return context.instance == context.user

    return False

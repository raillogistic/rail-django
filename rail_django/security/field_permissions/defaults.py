"""
Default configuration and rules for field permissions.

This module contains default sensitive field patterns, classification
defaults, and the default rule setup for the FieldPermissionManager.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Set

if TYPE_CHECKING:
    from django.db import models

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


RESTRICTED_FIELD_DEFAULT_NOT_SET = object()


def _build_restricted_default_for_field(field: "models.Field") -> Any:
    """Return a safe fallback value for restricted fields."""
    from django.db import models

    if isinstance(field, models.DecimalField):
        return Decimal("0")
    if isinstance(field, models.FloatField):
        return 0.0
    if isinstance(
        field,
        (
            models.IntegerField,
            models.BigIntegerField,
            models.SmallIntegerField,
            models.PositiveIntegerField,
            models.PositiveSmallIntegerField,
        ),
    ):
        return 0
    if isinstance(field, models.BooleanField):
        return False
    return RESTRICTED_FIELD_DEFAULT_NOT_SET


def resolve_restricted_field_default(
    model_class: type["models.Model"], field_name: str
) -> Any:
    """
    Resolve a server-side fallback for a restricted field.

    Priority:
    1. Django model field default (if defined)
    2. Type-safe zero/false fallback for non-null restricted numerics/bools
    """
    from django.db import models

    if not model_class or not field_name:
        return RESTRICTED_FIELD_DEFAULT_NOT_SET
    if field_name not in FINANCIAL_FIELDS:
        return RESTRICTED_FIELD_DEFAULT_NOT_SET

    try:
        model_field = model_class._meta.get_field(field_name)
    except Exception:
        return RESTRICTED_FIELD_DEFAULT_NOT_SET

    if getattr(model_field, "is_relation", False):
        return RESTRICTED_FIELD_DEFAULT_NOT_SET

    try:
        if callable(getattr(model_field, "has_default", None)) and model_field.has_default():
            value = model_field.get_default()
            if value is not models.NOT_PROVIDED:
                return value
    except Exception:
        pass

    if getattr(model_field, "null", False):
        return None

    return _build_restricted_default_for_field(model_field)


def has_restricted_field_default(
    model_class: type["models.Model"], field_name: str
) -> bool:
    """Return True when a restricted field has a resolvable fallback value."""
    return (
        resolve_restricted_field_default(model_class, field_name)
        is not RESTRICTED_FIELD_DEFAULT_NOT_SET
    )


def apply_restricted_field_defaults(
    input_data: dict[str, Any], model_class: type["models.Model"]
) -> dict[str, Any]:
    """Inject restricted field fallbacks for missing fields in create payloads."""
    if not isinstance(input_data, dict):
        return input_data
    if model_class is None:
        return input_data

    result = dict(input_data)
    for field_name in FINANCIAL_FIELDS:
        if field_name in result:
            continue
        fallback = resolve_restricted_field_default(model_class, field_name)
        if fallback is RESTRICTED_FIELD_DEFAULT_NOT_SET:
            continue
        result[field_name] = fallback
    return result


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

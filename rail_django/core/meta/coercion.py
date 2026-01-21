"""
Coercion Functions for GraphQL Meta Configuration

This module provides standalone functions for coercing raw configuration
values (dicts, strings, lists) into proper configuration dataclass instances.
These functions normalize legacy configuration formats and ensure type safety.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Union

from django.db import models

from .config import (
    FieldGuardConfig,
    FilterFieldConfig,
    OperationGuardConfig,
    RoleConfig,
)

logger = logging.getLogger(__name__)


def coerce_filter_field_config(value: Any) -> FilterFieldConfig:
    """
    Normalize legacy filter definitions into FilterFieldConfig.

    Handles various input formats:
    - FilterFieldConfig: Returns a copy
    - None: Returns empty config
    - list/tuple/set: Treats as list of lookups
    - str: Treats as single lookup
    - dict: Extracts lookups, choices, and help_text

    Args:
        value: Raw filter field configuration

    Returns:
        Normalized FilterFieldConfig instance
    """
    if isinstance(value, FilterFieldConfig):
        return FilterFieldConfig(
            lookups=list(value.lookups),
            choices=list(value.choices) if value.choices is not None else None,
            help_text=value.help_text,
        )

    if value is None:
        return FilterFieldConfig()

    if isinstance(value, (list, tuple, set)):
        return FilterFieldConfig(lookups=list(value))

    if isinstance(value, str):
        return FilterFieldConfig(lookups=[value])

    if isinstance(value, dict):
        choices = value.get("choices")
        help_text = value.get("help_text")

        if "lookups" in value:
            lookups = value.get("lookups") or []
        else:
            lookups: list[str] = []
            for lookup, definition in value.items():
                if lookup in {"choices", "help_text"}:
                    continue
                if isinstance(definition, bool):
                    if definition:
                        lookups.append(lookup)
                else:
                    lookups.append(lookup)
                    if (
                        lookup == "in"
                        and choices is None
                        and isinstance(definition, (list, tuple, set))
                    ):
                        choices = list(definition)

        if isinstance(choices, (list, tuple, set)):
            choices = list(choices)

        return FilterFieldConfig(
            lookups=list(lookups),
            choices=choices,
            help_text=help_text,
        )

    return FilterFieldConfig()


def coerce_role_config(name: str, value: Any) -> RoleConfig:
    """
    Coerce a raw value into a RoleConfig.

    Args:
        name: The role name (used as default if not specified in value)
        value: Raw role configuration (RoleConfig, dict)

    Returns:
        Normalized RoleConfig instance

    Raises:
        ValueError: If value format is not supported
    """
    if isinstance(value, RoleConfig):
        if not value.name:
            value.name = name
        return value

    if isinstance(value, dict):
        return RoleConfig(
            name=value.get("name") or name,
            description=value.get("description", ""),
            role_type=coerce_role_type(value.get("role_type")),
            permissions=list(value.get("permissions", [])),
            parent_roles=list(value.get("parent_roles", [])),
            is_system_role=value.get("is_system_role", False),
            max_users=value.get("max_users"),
        )

    raise ValueError(f"Unsupported role configuration for '{name}': {value}")


def coerce_operation_guard(name: str, value: Any) -> OperationGuardConfig:
    """
    Coerce a raw value into an OperationGuardConfig.

    Args:
        name: The operation name
        value: Raw guard configuration (OperationGuardConfig, dict, list)

    Returns:
        Normalized OperationGuardConfig instance

    Raises:
        ValueError: If value format is not supported
    """
    if isinstance(value, OperationGuardConfig):
        if not value.name:
            value.name = name
        return value

    if isinstance(value, dict):
        return OperationGuardConfig(
            name=name,
            roles=list(value.get("roles", [])),
            permissions=list(value.get("permissions", [])),
            condition=value.get("condition"),
            require_authentication=value.get("require_authentication", True),
            allow_anonymous=value.get("allow_anonymous", False),
            match=value.get("match", "any"),
            deny_message=value.get("deny_message"),
        )

    if isinstance(value, (list, tuple)):
        # Treat list as roles shortcut
        return OperationGuardConfig(name=name, roles=list(value))

    raise ValueError(
        f"Unsupported operation guard configuration for '{name}': {value}"
    )


def coerce_field_guard(value: Any) -> FieldGuardConfig:
    """
    Coerce a raw value into a FieldGuardConfig.

    Args:
        value: Raw field guard configuration (FieldGuardConfig, dict)

    Returns:
        Normalized FieldGuardConfig instance

    Raises:
        ValueError: If value format is not supported
    """
    if isinstance(value, FieldGuardConfig):
        return value

    if isinstance(value, dict):
        return FieldGuardConfig(
            field=value.get("field"),
            access=value.get("access", "read"),
            visibility=value.get("visibility", "visible"),
            roles=list(value.get("roles", [])),
            permissions=list(value.get("permissions", [])),
            mask_value=value.get("mask") or value.get("mask_value"),
            condition=value.get("condition"),
        )

    raise ValueError(f"Unsupported field guard configuration: {value}")


def coerce_role_type(role_type: Any) -> str:
    """
    Normalize a role type value to a lowercase string.

    Args:
        role_type: Raw role type (string or other)

    Returns:
        Normalized role type string (defaults to "business")
    """
    if isinstance(role_type, str) and role_type.strip():
        return role_type.strip().lower()
    return "business"


def convert_role_type(value: str, role_type_cls: Any) -> Any:
    """
    Convert a string role type to the corresponding enum member.

    Args:
        value: Role type string
        role_type_cls: The RoleType enum class

    Returns:
        Matching enum member or default (BUSINESS)
    """
    normalized = (value or "business").strip().lower()
    for candidate in role_type_cls:
        if candidate.value == normalized or candidate.name.lower() == normalized:
            return candidate
    return getattr(role_type_cls, "BUSINESS", list(role_type_cls)[0])


def coerce_access_level(value: str, components: dict[str, Any]) -> Any:
    """
    Coerce a string access level to a FieldAccessLevel enum.

    Args:
        value: Access level string (none, read, write, admin)
        components: Security components dictionary

    Returns:
        FieldAccessLevel enum member
    """
    FieldAccessLevel = components["FieldAccessLevel"]
    if isinstance(value, FieldAccessLevel):
        return value
    mapping = {
        "none": FieldAccessLevel.NONE,
        "read": FieldAccessLevel.READ,
        "write": FieldAccessLevel.WRITE,
        "admin": FieldAccessLevel.ADMIN,
    }
    return mapping.get(str(value).lower(), FieldAccessLevel.READ)


def coerce_visibility(value: str, components: dict[str, Any]) -> Any:
    """
    Coerce a string visibility to a FieldVisibility enum.

    Args:
        value: Visibility string (visible, hidden, masked, redacted)
        components: Security components dictionary

    Returns:
        FieldVisibility enum member
    """
    FieldVisibility = components["FieldVisibility"]
    if isinstance(value, FieldVisibility):
        return value
    mapping = {
        "visible": FieldVisibility.VISIBLE,
        "hidden": FieldVisibility.HIDDEN,
        "masked": FieldVisibility.MASKED,
        "redacted": FieldVisibility.REDACTED,
    }
    return mapping.get(str(value).lower(), FieldVisibility.VISIBLE)


def resolve_condition_callable(
    condition: Optional[Union[str, Callable]],
    model_class: type[models.Model],
) -> Optional[Callable]:
    """
    Resolve a condition to a callable.

    Args:
        condition: Condition specification (callable, method name string, or None)
        model_class: The model class to look up method names on

    Returns:
        Callable if resolved, None otherwise
    """
    if condition is None:
        return None
    if callable(condition):
        return condition
    if isinstance(condition, str) and hasattr(model_class, condition):
        candidate = getattr(model_class, condition)
        if callable(candidate):
            return candidate
    return None

"""
Security Component Loader

This module provides lazy loading of security components to avoid
circular imports between the meta configuration and security modules.
"""

from __future__ import annotations

from typing import Any, Optional

_SECURITY_COMPONENTS: Optional[dict[str, Any]] = None


def load_security_components() -> dict[str, Any]:
    """
    Lazily load and cache security components.

    Returns:
        Dictionary containing security classes and manager instances:
        - FieldAccessLevel
        - FieldPermissionRule
        - FieldVisibility
        - RoleDefinition
        - RoleType
        - field_permission_manager
        - role_manager
    """
    global _SECURITY_COMPONENTS
    if _SECURITY_COMPONENTS is None:
        from rail_django.security import (
            FieldAccessLevel,
            FieldPermissionRule,
            FieldVisibility,
            RoleDefinition,
            RoleType,
            field_permission_manager,
            role_manager,
        )

        _SECURITY_COMPONENTS = {
            "FieldAccessLevel": FieldAccessLevel,
            "FieldPermissionRule": FieldPermissionRule,
            "FieldVisibility": FieldVisibility,
            "RoleDefinition": RoleDefinition,
            "RoleType": RoleType,
            "field_permission_manager": field_permission_manager,
            "role_manager": role_manager,
        }
    return _SECURITY_COMPONENTS

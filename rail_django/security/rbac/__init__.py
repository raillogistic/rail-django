"""
Role-Based Access Control (RBAC) package for Django GraphQL.

This package provides a comprehensive RBAC system with:
- Role management with hierarchy support
- Permission evaluation with caching
- Policy engine integration
- Object-level permissions (ownership, assignment)
- GraphQL resolver decorators

Quick Start:
    >>> from rail_django.security.rbac import role_manager, require_role
    >>>
    >>> # Check permissions
    >>> if role_manager.has_permission(user, "project.update", context):
    ...     project.save()
    >>>
    >>> # Use decorators on resolvers
    >>> @require_role("admin")
    ... def resolve_admin_data(root, info):
    ...     return AdminData.objects.all()

Exports:
    - RoleManager: Central class for RBAC operations
    - RoleType: Enum for role classification (SYSTEM, BUSINESS, FUNCTIONAL)
    - PermissionScope: Enum for permission scope levels
    - RoleDefinition: Dataclass for role configuration
    - PermissionContext: Dataclass for contextual permission checks
    - PolicyDecisionDetail: Dataclass for policy decision details
    - PermissionExplanation: Dataclass for permission explanation
    - require_role: Decorator for role-based access control
    - require_permission: Decorator for permission-based access control
    - role_manager: Global singleton instance of RoleManager
"""

from .decorators import require_permission, require_role
from .manager import RoleManager, role_manager
from .types import (
    PermissionContext,
    PermissionExplanation,
    PermissionScope,
    PolicyDecisionDetail,
    RoleDefinition,
    RoleType,
)

__all__ = [
    # Types
    "RoleType",
    "PermissionScope",
    "RoleDefinition",
    "PermissionContext",
    "PolicyDecisionDetail",
    "PermissionExplanation",
    # Manager
    "RoleManager",
    # Decorators
    "require_role",
    "require_permission",
    # Singleton
    "role_manager",
]

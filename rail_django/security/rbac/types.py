"""
Type definitions for the RBAC (Role-Based Access Control) system.

This module contains enums and dataclasses used throughout the RBAC package:
- RoleType: Classification of role types (system, business, functional)
- PermissionScope: Scope levels for permissions (global, organization, etc.)
- RoleDefinition: Configuration for a role including permissions and hierarchy
- PermissionContext: Context information for permission evaluation
- PolicyDecisionDetail: Details about a policy decision
- PermissionExplanation: Comprehensive explanation of permission evaluation
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from django.db import models

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class RoleType(Enum):
    """Classification of role types in the system."""

    SYSTEM = "system"  # System-level roles (admin, superuser)
    BUSINESS = "business"  # Business domain roles (manager, employee)
    FUNCTIONAL = "functional"  # Functional roles (editor, viewer)


class PermissionScope(Enum):
    """Scope levels for permission application."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    DEPARTMENT = "department"
    PROJECT = "project"
    OBJECT = "object"


@dataclass
class RoleDefinition:
    """Definition of a role in the RBAC system."""

    name: str
    description: str
    role_type: RoleType
    permissions: list[str]
    parent_roles: list[str] = None
    is_system_role: bool = False
    max_users: Optional[int] = None


@dataclass
class PermissionContext:
    """Context information for evaluating contextual permissions."""

    user: "AbstractUser"
    object_id: Optional[str] = None
    object_instance: Optional[models.Model] = None
    model_class: Optional[type[models.Model]] = None
    operation: Optional[str] = None
    organization_id: Optional[str] = None
    department_id: Optional[str] = None
    project_id: Optional[str] = None
    additional_context: dict[str, Any] = None


@dataclass
class PolicyDecisionDetail:
    """Details about a specific policy's contribution to a permission decision."""

    name: str
    effect: str
    priority: int
    reason: Optional[str] = None


@dataclass
class PermissionExplanation:
    """Comprehensive explanation of a permission evaluation result."""

    permission: str
    allowed: bool
    reason: Optional[str] = None
    policy_decision: Optional[PolicyDecisionDetail] = None
    policy_matches: list[PolicyDecisionDetail] = field(default_factory=list)
    user_roles: list[str] = field(default_factory=list)
    effective_permissions: set[str] = field(default_factory=set)
    context_required: bool = False
    context_allowed: Optional[bool] = None
    context_reason: Optional[str] = None


__all__ = [
    "RoleType",
    "PermissionScope",
    "RoleDefinition",
    "PermissionContext",
    "PolicyDecisionDetail",
    "PermissionExplanation",
]

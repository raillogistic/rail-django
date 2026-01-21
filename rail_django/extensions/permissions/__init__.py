"""
Permission system for Django GraphQL Auto-Generation.

This package provides comprehensive permission checking for GraphQL operations
including field-level, object-level, and operation-level permissions.
"""

from .base import (
    BasePermissionChecker,
    OperationType,
    PermissionLevel,
    PermissionResult,
)
from .checkers import (
    CustomPermissionChecker,
    DjangoPermissionChecker,
    GraphQLOperationGuardChecker,
    OwnershipPermissionChecker,
)
from .decorators import (
    require_authentication,
    require_permission,
    require_superuser,
)
from .manager import PermissionManager, permission_manager
from .mixins import PermissionFilterMixin
from .queries import (
    PermissionExplanationInfo,
    PermissionInfo,
    PermissionQuery,
    PolicyDecisionInfo,
)
from .utils import setup_default_permissions

__all__ = [
    # Base
    "OperationType",
    "PermissionLevel",
    "PermissionResult",
    "BasePermissionChecker",
    # Checkers
    "DjangoPermissionChecker",
    "OwnershipPermissionChecker",
    "CustomPermissionChecker",
    "GraphQLOperationGuardChecker",
    # Manager
    "PermissionManager",
    "permission_manager",
    # Decorators
    "require_permission",
    "require_authentication",
    "require_superuser",
    # Mixins
    "PermissionFilterMixin",
    # Queries
    "PermissionInfo",
    "PolicyDecisionInfo",
    "PermissionExplanationInfo",
    "PermissionQuery",
    # Utils
    "setup_default_permissions",
]

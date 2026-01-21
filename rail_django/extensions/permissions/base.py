"""
Base types and classes for permissions.
"""

from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class OperationType(Enum):
    """Types d'opÇ¸rations GraphQL."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    HISTORY = "history"


class PermissionLevel(Enum):
    """Niveaux de permissions."""
    FIELD = "field"
    OBJECT = "object"
    OPERATION = "operation"


class PermissionResult:
    """RÇ¸sultat d'une vÇ¸rification de permission."""
    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason
    def __bool__(self):
        return self.allowed


class BasePermissionChecker:
    """Classe de base pour les vÇ¸rificateurs de permissions."""
    def check_permission(self, user: "AbstractUser", obj: Any = None, **kwargs) -> PermissionResult:
        raise NotImplementedError("Les sous-classes doivent implÇ¸menter check_permission")

"""
Concrete permission checkers.
"""

import logging
from typing import Any, Callable, TYPE_CHECKING
from django.db import models
from .base import BasePermissionChecker, PermissionResult, OperationType

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class DjangoPermissionChecker(BasePermissionChecker):
    """VÇ¸rificateur basÇ¸ sur les permissions Django."""
    def __init__(self, permission_codename: str, model_class: type[models.Model] = None):
        self.permission_codename = permission_codename
        self.model_class = model_class

    def check_permission(self, user: "AbstractUser", obj: Any = None, **kwargs) -> PermissionResult:
        if not user or not user.is_authenticated: return PermissionResult(False, "Utilisateur non authentifiÇ¸")
        if user.is_superuser: return PermissionResult(True, "Superutilisateur")
        if self.model_class: full_permission = f"{self.model_class._meta.app_label}.{self.permission_codename}_{self.model_class._meta.model_name}"
        else: full_permission = self.permission_codename
        if user.has_perm(full_permission): return PermissionResult(True, f"Permission {full_permission} accordÇ¸e")
        return PermissionResult(False, f"Permission {full_permission} refusÇ¸e")


class OwnershipPermissionChecker(BasePermissionChecker):
    """VÇ¸rificateur basÇ¸ sur la propriÇ¸tÇ¸ de l'objet."""
    def __init__(self, owner_field: str = "owner"):
        self.owner_field = owner_field

    def check_permission(self, user: "AbstractUser", obj: Any = None, **kwargs) -> PermissionResult:
        if not user or not user.is_authenticated: return PermissionResult(False, "Utilisateur non authentifiÇ¸")
        if not obj: return PermissionResult(True, "Pas d'objet Çÿ vÇ¸rifier")
        if user.is_superuser: return PermissionResult(True, "Superutilisateur")
        if getattr(obj, self.owner_field, None) == user: return PermissionResult(True, "PropriÇ¸taire de l'objet")
        return PermissionResult(False, "Pas propriÇ¸taire de l'objet")


class CustomPermissionChecker(BasePermissionChecker):
    """VÇ¸rificateur personnalisÇ¸ basÇ¸ sur une fonction."""
    def __init__(self, check_function: Callable[["AbstractUser", Any], bool], description: str = ""):
        self.check_function = check_function
        self.description = description

    def check_permission(self, user: "AbstractUser", obj: Any = None, **kwargs) -> PermissionResult:
        try:
            allowed = self.check_function(user, obj)
            return PermissionResult(allowed, f"VÇ¸rification personnalisÇ¸e: {self.description}")
        except Exception as e:
            logger.error(f"Erreur dans la vÇ¸rification personnalisÇ¸e: {e}")
            return PermissionResult(False, "Erreur dans la vÇ¸rification des permissions")


class GraphQLOperationGuardChecker(BasePermissionChecker):
    """VÇ¸rifie les gardes d'accÇºs dÇ¸finies dans GraphQLMeta."""
    def __init__(self, graphql_meta, guard_name: str, operation: OperationType):
        self.graphql_meta = graphql_meta
        self.guard_name = guard_name
        self.operation = operation

    def check_permission(self, user: "AbstractUser", obj: Any = None, **kwargs) -> PermissionResult:
        if not self.graphql_meta: return PermissionResult(True, "Aucune configuration GraphQL")
        try:
            guard_state = self.graphql_meta.describe_operation_guard(self.guard_name, user=user, instance=obj)
        except Exception as exc:
            logger.warning("Erreur lors de l'Ç¸valuation de la garde GraphQL %s: %s", self.guard_name, exc)
            return PermissionResult(False, "Impossible de vÇ¸rifier la garde GraphQL")
        if not guard_state.get("guarded", False): return PermissionResult(True, "Aucune garde GraphQL configurÇ¸e")
        if guard_state.get("allowed", True): return PermissionResult(True, "Garde GraphQL satisfaite")
        return PermissionResult(False, guard_state.get("reason") or f"AccÇºs interdit par la garde '{self.guard_name}'")

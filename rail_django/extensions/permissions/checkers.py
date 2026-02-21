"""
Concrete permission checkers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from django.db import models

from .base import BasePermissionChecker, OperationType, PermissionResult

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class DjangoPermissionChecker(BasePermissionChecker):
    """Checker based on Django auth permissions."""

    def __init__(
        self, permission_codename: str, model_class: type[models.Model] = None
    ) -> None:
        self.permission_codename = permission_codename
        self.model_class = model_class

    def check_permission(
        self, user: "AbstractUser", obj: Any = None, **kwargs
    ) -> PermissionResult:
        if not user or not getattr(user, "is_authenticated", False):
            return PermissionResult(False, "Utilisateur non authentifie")
        if getattr(user, "is_superuser", False):
            return PermissionResult(True, "Superutilisateur")

        if self.model_class:
            full_permission = (
                f"{self.model_class._meta.app_label}.{self.permission_codename}_"
                f"{self.model_class._meta.model_name}"
            )
        else:
            full_permission = self.permission_codename

        if user.has_perm(full_permission):
            return PermissionResult(True, f"Permission {full_permission} accordee")
        return PermissionResult(False, f"Permission {full_permission} refusee")


class OwnershipPermissionChecker(BasePermissionChecker):
    """Checker based on object ownership."""

    def __init__(self, owner_field: str = "owner") -> None:
        self.owner_field = owner_field

    def check_permission(
        self, user: "AbstractUser", obj: Any = None, **kwargs
    ) -> PermissionResult:
        if not user or not getattr(user, "is_authenticated", False):
            return PermissionResult(False, "Utilisateur non authentifie")
        if obj is None:
            return PermissionResult(True, "Pas d'objet a verifier")
        if getattr(user, "is_superuser", False):
            return PermissionResult(True, "Superutilisateur")
        if getattr(obj, self.owner_field, None) == user:
            return PermissionResult(True, "Proprietaire de l'objet")
        return PermissionResult(False, "Pas proprietaire de l'objet")


class CustomPermissionChecker(BasePermissionChecker):
    """Custom checker based on a function."""

    def __init__(
        self, check_function: Callable[["AbstractUser", Any], bool], description: str = ""
    ) -> None:
        self.check_function = check_function
        self.description = description

    def check_permission(
        self, user: "AbstractUser", obj: Any = None, **kwargs
    ) -> PermissionResult:
        try:
            allowed = bool(self.check_function(user, obj))
            return PermissionResult(
                allowed, f"Verification personnalisee: {self.description}"
            )
        except Exception as exc:
            logger.error("Erreur dans la verification personnalisee: %s", exc)
            return PermissionResult(False, "Erreur dans la verification des permissions")


class GraphQLOperationGuardChecker(BasePermissionChecker):
    """Checker for GraphQLMeta operation guards."""

    def __init__(self, graphql_meta, guard_name: str, operation: OperationType) -> None:
        self.graphql_meta = graphql_meta
        self.guard_name = guard_name
        self.operation = operation

    def check_permission(
        self, user: "AbstractUser", obj: Any = None, **kwargs
    ) -> PermissionResult:
        if not self.graphql_meta:
            return PermissionResult(True, "Aucune configuration GraphQL")
        try:
            guard_state = self.graphql_meta.describe_operation_guard(
                self.guard_name, user=user, instance=obj
            )
        except Exception as exc:
            logger.warning(
                "Erreur lors de l'evaluation de la garde GraphQL %s: %s",
                self.guard_name,
                exc,
            )
            return PermissionResult(False, "Impossible de verifier la garde GraphQL")
        if not guard_state.get("guarded", False):
            return PermissionResult(True, "Aucune garde GraphQL configuree")
        if guard_state.get("allowed", True):
            return PermissionResult(True, "Garde GraphQL satisfaite")
        reason = guard_state.get("reason") or f"Acces interdit par la garde '{self.guard_name}'"
        return PermissionResult(False, reason)


class HybridPermissionChecker(BasePermissionChecker):
    """Checker backed by hybrid RBAC+ABAC evaluation."""

    def __init__(
        self, permission_codename: str, model_class: type[models.Model] = None
    ) -> None:
        self.permission_codename = permission_codename
        self.model_class = model_class

    def check_permission(
        self, user: "AbstractUser", obj: Any = None, **kwargs
    ) -> PermissionResult:
        if not user or not getattr(user, "is_authenticated", False):
            return PermissionResult(False, "Utilisateur non authentifie")

        from ...security.hybrid import hybrid_engine
        from ...security.rbac import PermissionContext

        if self.model_class:
            full_permission = (
                f"{self.model_class._meta.app_label}.{self.permission_codename}_"
                f"{self.model_class._meta.model_name}"
            )
        else:
            full_permission = self.permission_codename

        request = kwargs.get("request")
        context = PermissionContext(
            user=user,
            object_instance=obj if isinstance(obj, models.Model) else None,
            model_class=self.model_class,
            operation=kwargs.get("operation"),
            additional_context={"request": request},
        )
        decision = hybrid_engine.has_permission(
            user,
            full_permission,
            context=context,
            instance=context.object_instance,
            request=request,
        )
        if decision.allowed:
            return PermissionResult(
                True, f"Permission {full_permission} accordee ({decision.reason})"
            )
        return PermissionResult(
            False, f"Permission {full_permission} refusee ({decision.reason})"
        )


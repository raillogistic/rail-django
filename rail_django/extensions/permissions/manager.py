"""
Permission manager implementation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import BasePermissionChecker, OperationType, PermissionResult

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class PermissionManager:
    """Central registry for field/object/operation permission checkers."""

    def __init__(self) -> None:
        self._field_permissions: dict[str, dict[str, list[BasePermissionChecker]]] = {}
        self._object_permissions: dict[str, list[BasePermissionChecker]] = {}
        self._operation_permissions: dict[str, dict[str, list[BasePermissionChecker]]] = {}

    def register_field_permission(
        self, model_name: str, field_name: str, checker: BasePermissionChecker
    ) -> None:
        self._field_permissions.setdefault(model_name, {}).setdefault(
            field_name, []
        ).append(checker)
        logger.info("Field permission checker registered: %s.%s", model_name, field_name)

    def register_object_permission(
        self, model_name: str, checker: BasePermissionChecker
    ) -> None:
        self._object_permissions.setdefault(model_name, []).append(checker)
        logger.info("Object permission checker registered: %s", model_name)

    def register_operation_permission(
        self, model_name: str, operation: OperationType, checker: BasePermissionChecker
    ) -> None:
        op_key = operation.value
        self._operation_permissions.setdefault(model_name, {}).setdefault(
            op_key, []
        ).append(checker)
        logger.info(
            "Operation permission checker registered: %s.%s", model_name, op_key
        )

    def check_field_permission(
        self, user: "AbstractUser", model_name: str, field_name: str, obj: Any = None
    ) -> PermissionResult:
        checkers = self._field_permissions.get(model_name, {}).get(field_name, [])
        if not checkers:
            return PermissionResult(True, "Aucune restriction de champ")
        for checker in checkers:
            result = checker.check_permission(user, obj)
            if not result.allowed:
                return result
        return PermissionResult(True, "Toutes les verifications de champ ont reussi")

    def check_object_permission(
        self, user: "AbstractUser", model_name: str, obj: Any = None
    ) -> PermissionResult:
        checkers = self._object_permissions.get(model_name, [])
        if not checkers:
            return PermissionResult(True, "Aucune restriction d'objet")
        for checker in checkers:
            result = checker.check_permission(user, obj)
            if not result.allowed:
                return result
        return PermissionResult(True, "Toutes les verifications d'objet ont reussi")

    def check_operation_permission(
        self,
        user: "AbstractUser",
        model_name: str,
        operation: OperationType,
        obj: Any = None,
        request: Any = None,
    ) -> PermissionResult:
        checkers = self._operation_permissions.get(model_name, {}).get(
            operation.value, []
        )
        if not checkers:
            return PermissionResult(True, "Aucune restriction d'operation")
        for checker in checkers:
            result = checker.check_permission(
                user,
                obj,
                operation=operation.value,
                model_name=model_name,
                request=request,
            )
            if not result.allowed:
                return result
        return PermissionResult(
            True, "Toutes les verifications d'operation ont reussi"
        )


permission_manager = PermissionManager()


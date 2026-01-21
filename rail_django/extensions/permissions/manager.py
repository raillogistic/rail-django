"""
PermissionManager implementation.
"""

import logging
from typing import Any, TYPE_CHECKING
from .base import BasePermissionChecker, PermissionResult, OperationType

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class PermissionManager:
    """Gestionnaire central des permissions."""

    def __init__(self):
        self._field_permissions: dict[str, dict[str, list[BasePermissionChecker]]] = {}
        self._object_permissions: dict[str, list[BasePermissionChecker]] = {}
        self._operation_permissions: dict[str, dict[str, list[BasePermissionChecker]]] = {}

    def register_field_permission(self, model_name: str, field_name: str, checker: BasePermissionChecker):
        if model_name not in self._field_permissions: self._field_permissions[model_name] = {}
        if field_name not in self._field_permissions[model_name]: self._field_permissions[model_name][field_name] = []
        self._field_permissions[model_name][field_name].append(checker)
        logger.info(f"Permission de champ enregistrÇ¸e: {model_name}.{field_name}")

    def register_object_permission(self, model_name: str, checker: BasePermissionChecker):
        if model_name not in self._object_permissions: self._object_permissions[model_name] = []
        self._object_permissions[model_name].append(checker)
        logger.info(f"Permission d'objet enregistrÇ¸e: {model_name}")

    def register_operation_permission(self, model_name: str, operation: OperationType, checker: BasePermissionChecker):
        if model_name not in self._operation_permissions: self._operation_permissions[model_name] = {}
        op_key = operation.value
        if op_key not in self._operation_permissions[model_name]: self._operation_permissions[model_name][op_key] = []
        self._operation_permissions[model_name][op_key].append(checker)
        logger.info(f"Permission d'opÇ¸ration enregistrÇ¸e: {model_name}.{op_key}")

    def check_field_permission(self, user: "AbstractUser", model_name: str, field_name: str, obj: Any = None) -> PermissionResult:
        checkers = self._field_permissions.get(model_name, {}).get(field_name, [])
        if not checkers: return PermissionResult(True, "Aucune restriction de champ")
        for checker in checkers:
            result = checker.check_permission(user, obj)
            if not result.allowed: return result
        return PermissionResult(True, "Toutes les vÇ¸rifications de champ rÇ¸ussies")

    def check_object_permission(self, user: "AbstractUser", model_name: str, obj: Any = None) -> PermissionResult:
        checkers = self._object_permissions.get(model_name, [])
        if not checkers: return PermissionResult(True, "Aucune restriction d'objet")
        for checker in checkers:
            result = checker.check_permission(user, obj)
            if not result.allowed: return result
        return PermissionResult(True, "Toutes les vÇ¸rifications d'objet rÇ¸ussies")

    def check_operation_permission(self, user: "AbstractUser", model_name: str, operation: OperationType, obj: Any = None) -> PermissionResult:
        checkers = self._operation_permissions.get(model_name, {}).get(operation.value, [])
        if not checkers: return PermissionResult(True, "Aucune restriction d'opÇ¸ration")
        for checker in checkers:
            result = checker.check_permission(user, obj)
            if not result.allowed: return result
        return PermissionResult(True, "Toutes les vÇ¸rifications d'opÇ¸ration rÇ¸ussies")


# Global instance
permission_manager = PermissionManager()

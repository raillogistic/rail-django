"""
Internal utility functions for permissions.
"""

import logging
from threading import Lock
from django.apps import apps
from django.db import models
from django.core.exceptions import AppRegistryNotReady

from ...core.meta import get_model_graphql_meta
from ...security.field_permissions import field_permission_manager
from ...security.rbac import PermissionContext, role_manager
from .base import OperationType
from .manager import permission_manager
from .checkers import DjangoPermissionChecker, GraphQLOperationGuardChecker

logger = logging.getLogger(__name__)

_PERMISSION_LOCK = Lock()
_REGISTERED_PERMISSION_MODELS: set[str] = set()

_OPERATION_PERMISSION_MAP = {
    OperationType.CREATE: "add", OperationType.READ: "view", OperationType.UPDATE: "change",
    OperationType.DELETE: "delete", OperationType.LIST: "view", OperationType.HISTORY: "view",
}

_GRAPHQL_GUARD_MAP = {
    OperationType.CREATE: "create", OperationType.READ: "retrieve", OperationType.UPDATE: "update",
    OperationType.DELETE: "delete", OperationType.LIST: "list", OperationType.HISTORY: "history",
}


def setup_default_permissions():
    """Configure les permissions et gardes pour les modÇºles installÇ¸s."""
    with _PERMISSION_LOCK:
        if not apps.ready: raise AppRegistryNotReady("Le registre des applications n'est pas prÇºt")
        registered_count = 0
        for model in apps.get_models():
            if model._meta.abstract or model._meta.auto_created: continue
            model_label = model._meta.label_lower
            if model_label in _REGISTERED_PERMISSION_MODELS: continue
            graphql_meta = _get_graphql_meta(model)
            _register_model_permissions(model, graphql_meta)
            role_manager.register_default_model_roles(model)
            if graphql_meta: field_permission_manager.register_graphql_field_config(model, graphql_meta)
            _REGISTERED_PERMISSION_MODELS.add(model_label)
            registered_count += 1
        logger.info("Permissions initialisÇ¸es pour %s modÇºles (total: %s)", registered_count, len(_REGISTERED_PERMISSION_MODELS))


def _get_graphql_meta(model: type[models.Model]):
    try: return get_model_graphql_meta(model)
    except Exception as exc:
        logger.warning("Impossible de charger GraphQLMeta pour %s: %s", model._meta.label, exc)
        return None


def _register_model_permissions(model: type[models.Model], graphql_meta=None) -> None:
    model_label = model._meta.label_lower
    for operation, codename in _OPERATION_PERMISSION_MAP.items():
        permission_manager.register_operation_permission(model_label, operation, DjangoPermissionChecker(codename, model))
        if graphql_meta:
            guard_name = _GRAPHQL_GUARD_MAP.get(operation)
            permission_manager.register_operation_permission(model_label, operation, GraphQLOperationGuardChecker(graphql_meta, guard_name, operation))

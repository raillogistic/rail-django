"""
Authorization helpers for generated form mutation/query paths.
"""

from __future__ import annotations

from typing import Any

from graphql import GraphQLError

from ....core.meta import get_model_graphql_meta

MODEL_PERMISSION_MAP = {
    "create": "add",
    "update": "change",
    "delete": "delete",
    "view": "view",
    "bulk_create": "add",
    "bulk_update": "change",
    "bulk_delete": "delete",
}


def _get_permission_codename(model: Any, operation: str) -> str:
    op = MODEL_PERMISSION_MAP.get(operation, operation)
    return f"{model._meta.app_label}.{op}_{model._meta.model_name}"


def ensure_generated_mutation_authorized(
    info: Any,
    model: Any,
    *,
    operation: str,
    instance: Any | None = None,
) -> None:
    context = getattr(info, "context", None)
    user = getattr(context, "user", None)

    if not user or not getattr(user, "is_authenticated", False):
        raise GraphQLError("Authentication required.")

    permission = _get_permission_codename(model, operation)
    if hasattr(user, "has_perm") and callable(user.has_perm):
        if not user.has_perm(permission):
            raise GraphQLError(f"Permission required: {permission}")

    graphql_meta = get_model_graphql_meta(model)
    try:
        graphql_meta.ensure_operation_access(operation, info=info, instance=instance)
    except GraphQLError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise GraphQLError(str(exc))

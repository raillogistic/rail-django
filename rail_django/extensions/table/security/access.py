"""Access control helpers for table v3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.conf import settings
from django.db import models

from ....core.meta import get_model_graphql_meta
from ....core.settings import QueryGeneratorSettings
from ....security.field_permissions import field_permission_manager
from ....security.field_permissions.types import FieldVisibility
from ....security.rbac import PermissionContext, role_manager


@dataclass(frozen=True)
class TablePermissionSnapshot:
    can_view: bool
    can_create: bool
    can_update: bool
    can_delete: bool
    can_export: bool


def resolve_table_model(app_label: str, model_name: str) -> type[models.Model]:
    model_cls = apps.get_model(app_label, model_name)
    meta = getattr(model_cls, "_meta", None)
    if meta is None or meta.abstract or meta.auto_created:
        raise LookupError(f"Model '{app_label}.{model_name}' is not available.")
    return model_cls


def table_anonymous_read_enabled() -> bool:
    return bool(getattr(settings, "TABLE_V3_ALLOW_ANONYMOUS_READ", False))


def table_mutations_enabled() -> bool:
    return bool(getattr(settings, "TABLE_V3_ENABLE_MUTATIONS", False))


def _user_has_perm(user: Any, permission_name: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    has_perm = getattr(user, "has_perm", None)
    if not callable(has_perm):
        return False
    try:
        return bool(has_perm(permission_name))
    except Exception:
        return False


def has_table_permission(user: Any, model_cls: type[models.Model], action: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if action == "view":
        if table_anonymous_read_enabled() and not (
            user and getattr(user, "is_authenticated", False)
        ):
            return True
    elif not table_mutations_enabled():
        return False

    codename_map = {
        "view": "view",
        "create": "add",
        "update": "change",
        "delete": "delete",
        "export": "view",
    }
    codename = codename_map.get(action, "view")
    permission_name = f"{model_cls._meta.app_label}.{codename}_{model_cls._meta.model_name}"
    return _user_has_perm(user, permission_name)


def get_table_permissions(user: Any, model_cls: type[models.Model]) -> TablePermissionSnapshot:
    can_view = has_table_permission(user, model_cls, "view")
    return TablePermissionSnapshot(
        can_view=can_view,
        can_create=has_table_permission(user, model_cls, "create"),
        can_update=has_table_permission(user, model_cls, "update"),
        can_delete=has_table_permission(user, model_cls, "delete"),
        can_export=has_table_permission(user, model_cls, "export") and can_view,
    )


def _is_authenticated(user: Any) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "pk", getattr(user, "id", None)) is not None
    )


def _graphql_guard_allows_table_read(
    user: Any,
    model_cls: type[models.Model],
    *,
    operation: str,
    instance: models.Model | None = None,
) -> bool | None:
    try:
        graphql_meta = get_model_graphql_meta(model_cls)
    except Exception:
        return None

    describe = getattr(graphql_meta, "describe_operation_guard", None)
    if not callable(describe):
        return None

    try:
        state = describe(operation, user=user, instance=instance)
    except Exception:
        return None

    if not isinstance(state, dict) or not state.get("guarded"):
        return None
    return bool(state.get("allowed", False))


def _user_has_model_permission_via_rbac(
    user: Any,
    model_cls: type[models.Model],
    permission_name: str,
    *,
    operation: str,
    instance: models.Model | None = None,
) -> bool:
    if not _is_authenticated(user):
        return False

    try:
        permission_context = PermissionContext(
            user=user,
            model_class=model_cls,
            object_instance=instance,
            object_id=str(getattr(instance, "pk", "")) if instance is not None else None,
            operation=operation,
        )
        return bool(
            role_manager.has_permission(user, permission_name, permission_context)
        )
    except Exception:
        return _user_has_perm(user, permission_name)


def can_read_table_model(
    user: Any,
    model_cls: type[models.Model],
    *,
    schema_name: str = "default",
    operation: str = "list",
    instance: models.Model | None = None,
    permission_snapshot: TablePermissionSnapshot | Any | None = None,
) -> bool:
    if getattr(user, "is_superuser", False):
        return True

    guard_allowed = _graphql_guard_allows_table_read(
        user,
        model_cls,
        operation=operation,
        instance=instance,
    )
    if guard_allowed is not None:
        return guard_allowed

    if bool(getattr(permission_snapshot, "can_view", False)):
        return True

    model_meta = getattr(model_cls, "_meta", None)
    if model_meta is None:
        return bool(getattr(permission_snapshot, "can_view", False))

    query_settings = QueryGeneratorSettings.from_schema(schema_name)
    if not getattr(query_settings, "require_model_permissions", True):
        return True

    if table_anonymous_read_enabled() and not _is_authenticated(user):
        return True

    codename = str(getattr(query_settings, "model_permission_codename", "view") or "").strip()
    if not codename:
        return True

    permission_name = (
        f"{model_meta.app_label}.{codename}_{model_meta.model_name}"
    )
    return _user_has_model_permission_via_rbac(
        user,
        model_cls,
        permission_name,
        operation=operation,
        instance=instance,
    )


def get_table_field_permissions(
    user: Any,
    model_cls: type[models.Model],
    *,
    instance: models.Model | None = None,
    operation_type: str = "read",
) -> dict[str, Any]:
    try:
        graphql_meta = get_model_graphql_meta(model_cls)
    except Exception:
        graphql_meta = None

    permissions: dict[str, Any] = {}
    for field in model_cls._meta.fields:
        field_name = getattr(field, "name", "")
        if not field_name or field_name.startswith("_"):
            continue
        if graphql_meta is not None:
            try:
                if not graphql_meta.should_expose_field(
                    field_name,
                    for_input=operation_type != "read",
                ):
                    continue
            except Exception:
                continue
        permission = field_permission_manager.check_field_permission(
            user,
            model_cls,
            field_name,
            instance=instance,
            operation_type=operation_type,
        )
        permissions[field_name] = permission
    return permissions


def get_visible_table_fields(
    user: Any,
    model_cls: type[models.Model],
    *,
    instance: models.Model | None = None,
) -> tuple[list[str], set[str], dict[str, Any]]:
    field_permissions = get_table_field_permissions(
        user,
        model_cls,
        instance=instance,
        operation_type="read",
    )
    visible_fields: list[str] = []
    editable_fields: set[str] = set()
    masked_fields: dict[str, Any] = {}

    for field_name, permission in field_permissions.items():
        if getattr(permission, "can_read", False):
            visible_fields.append(field_name)
            if getattr(permission, "visibility", None) in {
                FieldVisibility.MASKED,
                FieldVisibility.REDACTED,
            }:
                masked_fields[field_name] = (
                    permission.mask_value
                    if getattr(permission, "mask_value", None) not in (None, "")
                    else "***"
                )
        if getattr(permission, "can_write", False):
            editable_fields.add(field_name)

    return visible_fields, editable_fields, masked_fields


def get_writable_table_fields(
    user: Any,
    model_cls: type[models.Model],
    *,
    instance: models.Model | None = None,
) -> set[str]:
    field_permissions = get_table_field_permissions(
        user,
        model_cls,
        instance=instance,
        operation_type="update",
    )
    return {
        field_name
        for field_name, permission in field_permissions.items()
        if getattr(permission, "can_write", False)
    }

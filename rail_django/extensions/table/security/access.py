"""Access control helpers for table v3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.conf import settings
from django.db import models

from ....core.meta import get_model_graphql_meta
from ....security.field_permissions import field_permission_manager
from ....security.field_permissions.types import FieldVisibility


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

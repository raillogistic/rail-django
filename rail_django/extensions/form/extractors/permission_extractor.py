"""
Permission extraction for Form API.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from ....security.field_permissions import FieldVisibility, field_permission_manager


class PermissionExtractorMixin:
    """Mixin for extracting model and field permissions."""

    def _extract_permissions(
        self,
        model: type[models.Model],
        user: Any,
        *,
        fields: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        app_label = model._meta.app_label
        model_name = model._meta.model_name

        perms = {
            "can_create": True,
            "can_update": True,
            "can_delete": True,
            "can_view": True,
            "field_permissions": [],
        }

        if user and hasattr(user, "has_perm"):
            perms["can_create"] = user.has_perm(f"{app_label}.add_{model_name}")
            perms["can_update"] = user.has_perm(f"{app_label}.change_{model_name}")
            perms["can_delete"] = user.has_perm(f"{app_label}.delete_{model_name}")
            perms["can_view"] = user.has_perm(f"{app_label}.view_{model_name}")

        field_permissions = []
        for field in fields:
            field_permissions.append(
                {
                    "field": field.get("name"),
                    "can_read": True,
                    "can_write": not field.get("read_only", False),
                    "visibility": "VISIBLE",
                }
            )

        for relation in relations:
            field_permissions.append(
                {
                    "field": relation.get("name"),
                    "can_read": True,
                    "can_write": not relation.get("read_only", False),
                    "visibility": "VISIBLE",
                }
            )

        # Override with field permission manager when available
        if user:
            for entry in field_permissions:
                field_name = entry.get("field")
                if not field_name:
                    continue
                try:
                    perm = field_permission_manager.check_field_permission(
                        user, model, field_name, instance=None
                    )
                    entry["can_read"] = perm.visibility != FieldVisibility.HIDDEN
                    entry["can_write"] = perm.can_write
                    entry["visibility"] = (
                        perm.visibility.name
                        if hasattr(perm.visibility, "name")
                        else "VISIBLE"
                    )
                except Exception:
                    continue

        perms["field_permissions"] = field_permissions
        return perms

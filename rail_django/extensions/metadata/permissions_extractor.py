"""
Permission and other extraction logic for ModelSchemaExtractor.
"""

from typing import Any, Mapping, Optional
from django.db import models
from django.utils.translation import gettext_lazy as _

class PermissionExtractorMixin:
    """Mixin for extracting permissions and other miscellaneous info."""

    def _extract_mutations(self, model: type[models.Model], user: Any) -> list[dict]:
        """Extract available mutations."""
        mutations = []
        model_name = model.__name__
        # Translators: Operation names
        ops = {
            "CREATE": _("Create"),
            "UPDATE": _("Update"),
            "DELETE": _("Delete")
        }

        for op, name in [("CREATE", f"create_{model_name}"), ("UPDATE", f"update_{model_name}"), ("DELETE", f"delete_{model_name}")]:
            op_label = ops.get(op, op.title())
            mutations.append({
                "name": name, "operation": op,
                "description": f"{op_label} {model._meta.verbose_name}",
                "method_name": None, "input_fields": [], "allowed": True,
                "required_permissions": [f"{model._meta.app_label}.{op.lower()}_{model_name.lower()}"],
                "reason": None,
            })
        return mutations

    def _extract_permissions(self, model: type[models.Model], user: Any) -> dict:
        """Extract model permissions for user."""
        perms = {
            "can_list": False, "can_retrieve": False, "can_create": False, "can_update": False, "can_delete": False,
            "can_bulk_create": False, "can_bulk_update": False, "can_bulk_delete": False, "can_export": False,
            "denial_reasons": {},
        }
        if user and getattr(user, "is_superuser", False):
            perms["can_create"] = True
            perms["can_update"] = True
            perms["can_delete"] = True
            perms["can_list"] = True
            perms["can_retrieve"] = True
            perms["can_bulk_create"] = True
            perms["can_bulk_update"] = True
            perms["can_bulk_delete"] = True
            perms["can_export"] = True
            return perms

        has_perm = getattr(user, "has_perm", None)
        is_authenticated = bool(user and getattr(user, "is_authenticated", False))
        if is_authenticated and callable(has_perm):
            app = model._meta.app_label
            name = model.__name__.lower()
            perms["can_create"] = bool(has_perm(f"{app}.add_{name}"))
            perms["can_update"] = bool(has_perm(f"{app}.change_{name}"))
            perms["can_delete"] = bool(has_perm(f"{app}.delete_{name}"))
            perms["can_list"] = bool(has_perm(f"{app}.view_{name}"))
            perms["can_retrieve"] = perms["can_list"]
            perms["can_bulk_create"] = perms["can_create"]
            perms["can_bulk_update"] = perms["can_update"]
            perms["can_bulk_delete"] = perms["can_delete"]
            perms["can_export"] = perms["can_list"]
        return perms

    def _extract_field_groups(self, model: type[models.Model], graphql_meta: Any) -> Optional[list[dict]]:
        """Extract field groups from GraphQLMeta."""
        groups = getattr(graphql_meta, "field_groups", None)
        if groups:
            return [{"key": g.get("key", ""), "label": g.get("label", ""), "description": g.get("description"), "fields": g.get("fields", [])} for g in groups]
        return None

    def _extract_templates(self, model: type[models.Model], user: Any) -> list[dict]:
        """Extract available templates."""
        templates = []
        try:
            from ..templating import template_registry
            if template_registry:
                model_templates = template_registry.get_templates_for_model(model)
                for key, tmpl in model_templates.items():
                    templates.append({
                        "key": key, "title": getattr(tmpl, "title", key),
                        "description": getattr(tmpl, "description", None),
                        "endpoint": f"/api/templates/{model._meta.app_label}/{model.__name__}/{key}/",
                    })
        except Exception:
            pass
        return templates

    def _extract_detail_permission_snapshot(
        self,
        model: type[models.Model],
        user: Any,
        *,
        schema_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Build a detail-focused permission snapshot used by ModelDetailV2.
        """
        payload = schema_payload or {}
        permissions = self._extract_permissions(model, user)

        field_visibility = {
            str(field.get("name")): bool(field.get("readable", False))
            for field in (payload.get("fields") or [])
            if isinstance(field, Mapping) and field.get("name")
        }
        relation_visibility = {
            str(relation.get("name")): bool(relation.get("readable", False))
            for relation in (payload.get("relationships") or [])
            if isinstance(relation, Mapping) and relation.get("name")
        }
        action_executability = {
            str(mutation.get("name")): bool(mutation.get("allowed", False))
            for mutation in (payload.get("mutations") or [])
            if isinstance(mutation, Mapping) and mutation.get("name")
        }

        return {
            "model_readable": bool(
                permissions.get("can_retrieve", False) and permissions.get("can_list", False)
            ),
            "field_visibility": field_visibility,
            "relation_visibility": relation_visibility,
            "action_executability": action_executability,
            "source_flags": {
                "metadata": {
                    "fields": sorted(field_visibility.keys()),
                    "relations": sorted(relation_visibility.keys()),
                    "actions": sorted(action_executability.keys()),
                },
                "backend": {
                    "can_list": bool(permissions.get("can_list", False)),
                    "can_retrieve": bool(permissions.get("can_retrieve", False)),
                    "can_update": bool(permissions.get("can_update", False)),
                    "can_delete": bool(permissions.get("can_delete", False)),
                },
            },
            "policy": "FAIL_CLOSED",
        }

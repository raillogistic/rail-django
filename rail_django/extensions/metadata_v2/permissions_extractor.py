"""
Permission and other extraction logic for ModelSchemaExtractor.
"""

from typing import Any, Optional
from django.db import models

class PermissionExtractorMixin:
    """Mixin for extracting permissions and other miscellaneous info."""

    def _extract_mutations(self, model: type[models.Model], user: Any) -> list[dict]:
        """Extract available mutations."""
        mutations = []
        model_name = model.__name__
        for op, name in [("CREATE", f"create_{model_name}"), ("UPDATE", f"update_{model_name}"), ("DELETE", f"delete_{model_name}")]:
            mutations.append({
                "name": name, "operation": op,
                "description": f"{op.title()} a {model._meta.verbose_name}",
                "method_name": None, "input_fields": [], "allowed": True,
                "required_permissions": [f"{model._meta.app_label}.{op.lower()}_{model_name.lower()}"],
                "reason": None,
            })
        return mutations

    def _extract_permissions(self, model: type[models.Model], user: Any) -> dict:
        """Extract model permissions for user."""
        perms = {
            "can_list": True, "can_retrieve": True, "can_create": True, "can_update": True, "can_delete": True,
            "can_bulk_create": True, "can_bulk_update": True, "can_bulk_delete": True, "can_export": True,
            "denial_reasons": {},
        }
        if user and hasattr(user, "has_perm"):
            app = model._meta.app_label
            name = model.__name__.lower()
            perms["can_create"] = user.has_perm(f"{app}.add_{name}")
            perms["can_update"] = user.has_perm(f"{app}.change_{name}")
            perms["can_delete"] = user.has_perm(f"{app}.delete_{name}")
            perms["can_list"] = user.has_perm(f"{app}.view_{name}")
            perms["can_retrieve"] = perms["can_list"]
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
        except Exception: pass
        return templates

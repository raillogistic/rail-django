"""
ModelSchemaExtractor implementation.
"""

import logging
from typing import Any, Optional

from django.apps import apps
from graphql import GraphQLError

from ...utils.graphql_meta import get_model_graphql_meta
from .utils import (
    _cache_version,
    get_cached_schema,
    set_cached_schema,
    get_model_version,
)

from .field_extractor import FieldExtractorMixin
from .filter_extractor import FilterExtractorMixin
from .permissions_extractor import PermissionExtractorMixin
from ...generators.introspector import ModelIntrospector
from ...core.settings import MutationGeneratorSettings
from ..templating.registry import template_registry

logger = logging.getLogger(__name__)


class ModelSchemaExtractor(
    FieldExtractorMixin, FilterExtractorMixin, PermissionExtractorMixin
):
    """
    Extracts comprehensive schema information from Django models.
    """

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name

    def extract(
        self,
        app_name: str,
        model_name: str,
        user: Any = None,
        object_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Extract complete schema for a model."""
        # Try cache first
        user_id = str(user.pk) if user and hasattr(user, "pk") else None
        cached = get_cached_schema(app_name, model_name, user_id, object_id)
        if cached:
            return cached

        try:
            model = apps.get_model(app_name, model_name)
        except LookupError:
            raise GraphQLError(f"Model '{app_name}.{model_name}' not found.")

        meta = model._meta
        graphql_meta = get_model_graphql_meta(model)

        # Retrieve instance if object_id is provided
        instance = None
        if object_id:
            try:
                instance = model.objects.get(pk=object_id)
            except (model.DoesNotExist, ValueError):
                pass

        from graphene.utils.str_converters import to_camel_case

        result = {
            "app": app_name,
            "model": model_name,
            "verbose_name": str(meta.verbose_name),
            "verbose_name_plural": str(meta.verbose_name_plural),
            "primary_key": to_camel_case(meta.pk.name) if meta.pk else "id",
            "ordering": [("-" + to_camel_case(o[1:])) if o.startswith("-") else to_camel_case(o) for o in meta.ordering] if meta.ordering else [],
            "unique_together": [[to_camel_case(f) for f in ut] for ut in meta.unique_together]
            if meta.unique_together
            else [],
            "fields": self._extract_fields(
                model, user, instance=instance, graphql_meta=graphql_meta
            ),
            "relationships": self._extract_relationships(
                model, user, graphql_meta=graphql_meta
            ),
            "filters": self._extract_filters(model),
            "filter_config": self._extract_filter_config(model),
            "relation_filters": self._extract_relation_filters(model),
            "mutations": self._extract_mutations(model, user, instance=instance),
            "permissions": self._extract_permissions(model, user),
            "field_groups": self._extract_field_groups(model, graphql_meta),
            "templates": self._extract_templates(model, user),
            "metadata_version": get_model_version(app_name, model_name),
            "custom_metadata": getattr(graphql_meta, "custom_metadata", None),
        }

        # Cache result
        set_cached_schema(app_name, model_name, result, user_id, object_id)

        return result

    def _extract_field_groups(self, model: Any, graphql_meta: Any) -> list[dict]:
        """Extract field grouping information."""
        if not graphql_meta or not hasattr(graphql_meta, "field_groups"):
            return []

        from graphene.utils.str_converters import to_camel_case

        groups = []
        field_groups = getattr(graphql_meta, "field_groups", None) or []
        for group in field_groups:
            groups.append(
                {
                    "key": group.get("key"),
                    "label": group.get("label"),
                    "description": group.get("description"),
                    "fields": [to_camel_case(f) for f in group.get("fields", [])],
                    "collapsed": group.get("collapsed", False),
                }
            )
        return groups

    def _extract_templates(self, model: Any, user: Any) -> list[dict]:
        """Extract available PDF templates for the model."""
        from graphene.utils.str_converters import to_camel_case
        templates = []
        # Filter templates for this model
        for url_path, definition in template_registry.all().items():
            if definition.model == model:
                # Basic permission check mock - in real app, check 'roles'/'permissions' against user
                templates.append(
                    {
                        "key": url_path,
                        "title": definition.title,
                        "description": None,
                        "endpoint": f"/api/templating/{url_path}",  # construct actual endpoint
                        "url_path": definition.url_path,
                        "guard": definition.guard,
                        "require_authentication": definition.require_authentication,
                        "roles": list(definition.roles),
                        "permissions": list(definition.permissions),
                        "allowed": True,
                        "denial_reason": None,
                        "allow_client_data": definition.allow_client_data,
                        "client_data_fields": [to_camel_case(f) for f in definition.client_data_fields],
                        "client_data_schema": None,  # complex to serialize fully
                    }
                )
        return templates

    def _extract_mutations(
        self, model: Any, user: Any, instance: Any = None
    ) -> list[dict]:
        """Extract available mutations for the model."""
        from ...core.security import get_authz_manager

        settings = MutationGeneratorSettings.from_schema(self.schema_name)
        results: list[dict] = []
        model_name = model.__name__
        graphql_meta = get_model_graphql_meta(model)

        authz_manager = get_authz_manager(self.schema_name)
        enable_authorization = getattr(
            getattr(authz_manager, "settings", None), "enable_authorization", True
        )
        require_model_permissions = (
            enable_authorization
            and getattr(settings, "require_model_permissions", True)
        )

        def _normalize_operation(op: str) -> str:
            normalized = str(op or "").strip().lower()
            if normalized.startswith("bulk_"):
                normalized = normalized[len("bulk_") :]
            return normalized

        def _get_model_permission(operation: str) -> Optional[str]:
            if not require_model_permissions:
                return None
            mapping = getattr(settings, "model_permission_codenames", None)
            if not isinstance(mapping, dict):
                return None
            normalized = _normalize_operation(operation)
            codename = mapping.get(operation) or mapping.get(normalized)
            codename = str(codename or "").strip() if codename is not None else ""
            if not codename:
                return None
            return f"{model._meta.app_label}.{codename}_{model._meta.model_name}"

        def _get_guard(operation: str):
            guards = getattr(graphql_meta, "_operation_guards", None)
            if not isinstance(guards, dict):
                guards = {}
            return guards.get(operation) or guards.get("*")

        def _dedupe(items: list[str]) -> list[str]:
            seen = set()
            out = []
            for item in items:
                if not item or item in seen:
                    continue
                seen.add(item)
                out.append(item)
            return out

        def _user_has_permissions(perms: list[str]) -> bool:
            if not perms:
                return True
            if not user or not getattr(user, "is_authenticated", False):
                return False
            has_perm = getattr(user, "has_perm", None)
            if not callable(has_perm):
                return False
            return all(has_perm(perm) for perm in perms)

        def _permission_reason(perms: list[str]) -> str:
            if not perms:
                return "Authentication required"
            return f"Permission required: {', '.join(perms)}"

        def _evaluate_access(
            *,
            operation: str,
            guard_operation: Optional[str] = None,
            instance: Any = None,
            extra_permissions: Optional[list[str]] = None,
        ) -> tuple[bool, list[str], bool, Optional[str]]:
            guard_op = guard_operation or operation
            guard = _get_guard(guard_op)
            guard_state = {"guarded": False, "allowed": True, "reason": None}
            describe = getattr(graphql_meta, "describe_operation_guard", None)
            if callable(describe):
                try:
                    state = describe(guard_op, user=user, instance=instance)
                    if isinstance(state, dict):
                        guard_state = state
                except Exception:
                    guard_state = {"guarded": False, "allowed": True, "reason": None}

            required_permissions: list[str] = []
            if guard:
                guard_perms = list(getattr(guard, "permissions", []) or [])
                if extra_permissions:
                    required_permissions = _dedupe(guard_perms + extra_permissions)
                else:
                    required_permissions = _dedupe(guard_perms)
                requires_authentication = bool(
                    getattr(guard, "require_authentication", True)
                ) and not bool(getattr(guard, "allow_anonymous", False))
                if extra_permissions:
                    requires_authentication = True
                allowed = bool(guard_state.get("allowed", True))
                reason = guard_state.get("reason") if not allowed else None
                if allowed and extra_permissions:
                    if not user or not getattr(user, "is_authenticated", False):
                        allowed = False
                        reason = "Authentication required"
                    else:
                        missing = [
                            perm
                            for perm in extra_permissions
                            if not _user_has_permissions([perm])
                        ]
                        if missing:
                            allowed = False
                            reason = _permission_reason(missing)
                return allowed, required_permissions, requires_authentication, reason

            if extra_permissions:
                required_permissions.extend(extra_permissions)
            model_permission = _get_model_permission(operation)
            if model_permission:
                required_permissions.append(model_permission)
            required_permissions = _dedupe(required_permissions)

            requires_authentication = bool(required_permissions)
            if not required_permissions:
                return True, required_permissions, requires_authentication, None

            if not user or not getattr(user, "is_authenticated", False):
                return False, required_permissions, requires_authentication, "Authentication required"

            missing = [
                perm
                for perm in required_permissions
                if not _user_has_permissions([perm])
            ]
            if missing:
                return (
                    False,
                    required_permissions,
                    requires_authentication,
                    _permission_reason(missing),
                )
            return True, required_permissions, requires_authentication, None

        # CRUD
        if settings.enable_create:
            allowed, required_permissions, requires_authentication, reason = _evaluate_access(
                operation="create"
            )
            results.append(
                {
                    "name": f"create{model_name}",
                    "operation": "create",
                    "description": f"Create {model._meta.verbose_name}",
                    "method_name": None,
                    "input_fields": [],
                    "allowed": allowed,
                    "required_permissions": required_permissions,
                    "reason": reason,
                    "mutation_type": "create",
                    "model_name": model_name,
                    "requires_authentication": requires_authentication,
                }
            )
        if settings.enable_update:
            allowed, required_permissions, requires_authentication, reason = _evaluate_access(
                operation="update", instance=instance
            )
            results.append(
                {
                    "name": f"update{model_name}",
                    "operation": "update",
                    "description": f"Update {model._meta.verbose_name}",
                    "method_name": None,
                    "input_fields": [],
                    "allowed": allowed,
                    "required_permissions": required_permissions,
                    "reason": reason,
                    "mutation_type": "update",
                    "model_name": model_name,
                    "requires_authentication": requires_authentication,
                }
            )
        if settings.enable_delete:
            allowed, required_permissions, requires_authentication, reason = _evaluate_access(
                operation="delete", instance=instance
            )
            results.append(
                {
                    "name": f"delete{model_name}",
                    "operation": "delete",
                    "description": f"Delete {model._meta.verbose_name}",
                    "method_name": None,
                    "input_fields": [],
                    "allowed": allowed,
                    "required_permissions": required_permissions,
                    "reason": reason,
                    "mutation_type": "delete",
                    "model_name": model_name,
                    "requires_authentication": requires_authentication,
                }
            )

        # Method mutations
        introspector = ModelIntrospector.for_model(model)
        from graphene.utils.str_converters import to_camel_case

        def _infer_guard_operation(name: Optional[str], action_kind: Optional[str] = None) -> str:
            if action_kind == "confirm":
                return "update"
            lowered = str(name or "").lower()
            if lowered.startswith(("create", "add", "register", "signup", "import")):
                return "create"
            if lowered.startswith(("delete", "remove", "archive", "purge", "clear")):
                return "delete"
            if lowered.startswith(("update", "set", "edit", "patch", "upsert", "enable", "disable")):
                return "update"
            if "delete" in lowered or "remove" in lowered:
                return "delete"
            if "create" in lowered or "add" in lowered:
                return "create"
            return "update"

        for name, info in introspector.get_model_methods().items():
            if not info.is_mutation:
                continue
            method = info.method
            requires_permissions = getattr(method, "_requires_permissions", None)
            if requires_permissions is None:
                legacy_perm = getattr(method, "_requires_permission", None)
                requires_permissions = [legacy_perm] if legacy_perm else None
            requires_permissions = [
                perm for perm in (requires_permissions or []) if perm
            ]
            action_kind = getattr(method, "_action_kind", None)
            guard_operation = _infer_guard_operation(name, action_kind)
            allowed, required_permissions, requires_authentication, reason = _evaluate_access(
                operation="custom",
                guard_operation=guard_operation,
                instance=instance,
                extra_permissions=requires_permissions,
            )

            results.append(
                {
                    "name": to_camel_case(name),
                    "operation": "custom",
                    "description": str(method.__doc__ or "").strip(),
                    "method_name": name,
                    "input_fields": [],  # Argument extraction omitted for brevity
                    "allowed": allowed,
                    "required_permissions": required_permissions,
                    "reason": reason,
                    "mutation_type": "custom",
                    "model_name": model_name,
                    "requires_authentication": requires_authentication,
                }
            )

        return results

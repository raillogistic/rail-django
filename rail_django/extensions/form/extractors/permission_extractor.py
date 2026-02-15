"""
Permission extraction for Form API.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from ....core.security import get_authz_manager
from ....core.settings import MutationGeneratorSettings, QueryGeneratorSettings
from ....security.field_permissions import FieldVisibility, field_permission_manager
from ....security.rbac import PermissionContext, role_manager
from ..utils.graphql_meta import get_graphql_meta


class PermissionExtractorMixin:
    """Mixin for extracting model and field permissions."""

    def _extract_permissions(
        self,
        model: type[models.Model],
        user: Any,
        *,
        fields: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        graphql_meta: Any | None = None,
        instance: models.Model | None = None,
        mode: str = "CREATE",
    ) -> dict[str, Any]:
        schema_name = getattr(self, "schema_name", "default")
        app_label = model._meta.app_label
        model_name = model._meta.model_name

        if graphql_meta is None:
            graphql_meta = get_graphql_meta(model)

        authz_manager = get_authz_manager(schema_name)
        enable_authorization = bool(
            getattr(getattr(authz_manager, "settings", None), "enable_authorization", True)
        )
        query_settings = QueryGeneratorSettings.from_schema(schema_name)
        mutation_settings = MutationGeneratorSettings.from_schema(schema_name)

        require_query_permissions = bool(
            enable_authorization and getattr(query_settings, "require_model_permissions", True)
        )
        require_mutation_permissions = bool(
            enable_authorization and getattr(mutation_settings, "require_model_permissions", True)
        )

        def _is_authenticated(target_user: Any) -> bool:
            return bool(
                target_user
                and getattr(target_user, "is_authenticated", False)
                and getattr(target_user, "pk", None) is not None
            )

        def _dedupe(values: list[str]) -> list[str]:
            seen: set[str] = set()
            deduped: list[str] = []
            for value in values:
                normalized = str(value or "").strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                deduped.append(normalized)
            return deduped

        def _permission_reason(required_permissions: list[str]) -> str:
            if not required_permissions:
                return "Authentication required"
            return f"Permission required: {', '.join(required_permissions)}"

        def _user_has_permission(
            permission: str,
            *,
            operation: str,
        ) -> bool:
            if not _is_authenticated(user):
                return False

            context = PermissionContext(
                user=user,
                model_class=model,
                object_instance=instance,
                object_id=str(getattr(instance, "pk", "")) if instance is not None else None,
                operation=operation,
            )
            try:
                return bool(role_manager.has_permission(user, permission, context))
            except Exception:
                has_perm = getattr(user, "has_perm", None)
                if callable(has_perm):
                    try:
                        return bool(has_perm(permission))
                    except Exception:
                        return False
                return False

        def _evaluate_operation_access(
            *,
            operation: str,
            guard_operation: str,
            model_permission: str | None,
        ) -> dict[str, Any]:
            guards = getattr(graphql_meta, "_operation_guards", None)
            guard = None
            if isinstance(guards, dict):
                guard = guards.get(guard_operation) or guards.get("*")

            describe = getattr(graphql_meta, "describe_operation_guard", None)
            guard_state = {"guarded": False, "allowed": True, "reason": None}
            if callable(describe):
                try:
                    state = describe(guard_operation, user=user, instance=instance)
                    if isinstance(state, dict):
                        guard_state = state
                except Exception:
                    guard_state = {"guarded": False, "allowed": True, "reason": None}

            required_permissions: list[str] = []
            if guard:
                guard_permissions = list(getattr(guard, "permissions", []) or [])
                required_permissions = _dedupe(guard_permissions)

                requires_authentication = bool(
                    getattr(guard, "require_authentication", True)
                ) and not bool(getattr(guard, "allow_anonymous", False))
                if required_permissions:
                    requires_authentication = True

                allowed = bool(guard_state.get("allowed", True))
                reason = str(guard_state.get("reason") or "") or None

                if allowed and required_permissions:
                    if not _is_authenticated(user):
                        return {
                            "allowed": False,
                            "required_permissions": required_permissions,
                            "requires_authentication": True,
                            "reason": "Authentication required",
                        }

                    missing_permissions = [
                        permission
                        for permission in required_permissions
                        if not _user_has_permission(
                            permission,
                            operation=operation,
                        )
                    ]
                    if missing_permissions:
                        return {
                            "allowed": False,
                            "required_permissions": required_permissions,
                            "requires_authentication": True,
                            "reason": _permission_reason(missing_permissions),
                        }

                return {
                    "allowed": allowed,
                    "required_permissions": required_permissions,
                    "requires_authentication": requires_authentication,
                    "reason": reason,
                }

            if model_permission:
                required_permissions = _dedupe([model_permission])
            else:
                required_permissions = []

            requires_authentication = bool(required_permissions)
            if not required_permissions:
                return {
                    "allowed": True,
                    "required_permissions": [],
                    "requires_authentication": False,
                    "reason": None,
                }

            if not _is_authenticated(user):
                return {
                    "allowed": False,
                    "required_permissions": required_permissions,
                    "requires_authentication": True,
                    "reason": "Authentication required",
                }

            missing_permissions = [
                permission
                for permission in required_permissions
                if not _user_has_permission(
                    permission,
                    operation=operation,
                )
            ]
            if missing_permissions:
                return {
                    "allowed": False,
                    "required_permissions": required_permissions,
                    "requires_authentication": requires_authentication,
                    "reason": _permission_reason(missing_permissions),
                }

            return {
                "allowed": True,
                "required_permissions": required_permissions,
                "requires_authentication": requires_authentication,
                "reason": None,
            }

        def _build_model_permission(operation: str) -> str | None:
            op = str(operation or "").strip().lower()
            if op == "view":
                if not require_query_permissions:
                    return None
                codename = str(
                    getattr(query_settings, "model_permission_codename", "view") or ""
                ).strip()
                if not codename:
                    return None
                return f"{app_label}.{codename}_{model_name}"

            if op not in {"create", "update", "delete"}:
                return None
            if not require_mutation_permissions:
                return None

            mapping = getattr(mutation_settings, "model_permission_codenames", None)
            if not isinstance(mapping, dict):
                return None
            codename = str(mapping.get(op) or "").strip()
            if not codename:
                return None
            return f"{app_label}.{codename}_{model_name}"

        view_guard_operation = (
            "retrieve" if instance is not None or str(mode).upper() in {"UPDATE", "VIEW"} else "list"
        )
        operation_matrix = {
            "view": _evaluate_operation_access(
                operation="view",
                guard_operation=view_guard_operation,
                model_permission=_build_model_permission("view"),
            ),
            "create": _evaluate_operation_access(
                operation="create",
                guard_operation="create",
                model_permission=_build_model_permission("create"),
            ),
            "update": _evaluate_operation_access(
                operation="update",
                guard_operation="update",
                model_permission=_build_model_permission("update"),
            ),
            "delete": _evaluate_operation_access(
                operation="delete",
                guard_operation="delete",
                model_permission=_build_model_permission("delete"),
            ),
        }

        perms = {
            "can_create": bool(operation_matrix["create"]["allowed"]),
            "can_update": bool(operation_matrix["update"]["allowed"]),
            "can_delete": bool(operation_matrix["delete"]["allowed"]),
            "can_view": bool(operation_matrix["view"]["allowed"]),
            "operations": operation_matrix,
            "field_permissions": [],
        }

        field_permissions = []

        def _append_field_permission(entry: dict[str, Any]) -> None:
            aliases = [
                str(value).strip()
                for value in (
                    entry.get("name"),
                    entry.get("field_name"),
                    entry.get("path"),
                )
                if str(value or "").strip()
            ]
            model_field = str(entry.get("field_name") or entry.get("name") or "").strip()
            if not model_field:
                return

            hidden = bool(entry.get("hidden", False))
            can_read = bool(entry.get("readable", not hidden))
            can_write = bool(entry.get("writable", not entry.get("read_only", False)))
            visibility = "HIDDEN" if hidden or not can_read else "VISIBLE"

            field_permissions.append(
                {
                    "field": model_field,
                    "can_read": can_read,
                    "can_write": can_write,
                    "visibility": visibility,
                    "aliases": _dedupe(aliases + [model_field]),
                    "model_field": model_field,
                }
            )

        for field in fields:
            _append_field_permission(field)

        for relation in relations:
            _append_field_permission(relation)

        # Override with field permission manager when available
        if user:
            for entry in field_permissions:
                field_name = entry.get("model_field")
                if not field_name:
                    continue
                try:
                    perm = field_permission_manager.check_field_permission(
                        user, model, field_name, instance=instance
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
        perms["denial_reasons"] = {
            operation: details.get("reason")
            for operation, details in operation_matrix.items()
            if details.get("reason")
        }
        return perms

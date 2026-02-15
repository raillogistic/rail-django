"""
Relationship extraction for Form API.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from django.db import models

from ....security.field_permissions import FieldVisibility, field_permission_manager
from ....security.rbac import PermissionContext, role_manager

logger = logging.getLogger(__name__)


class RelationExtractorMixin:
    """Mixin for extracting relation configurations."""

    @staticmethod
    def _split_relation_verbose_name(raw_value: Any) -> tuple[Optional[str], Optional[str]]:
        text = str(raw_value or "").strip()
        if "/" not in text:
            return None, None

        left, right = text.split("/", 1)
        left_value = left.strip() or None
        right_value = right.strip() or None
        return left_value, right_value

    @staticmethod
    def _normalize_relation_name(raw_name: Optional[str]) -> Optional[str]:
        if not raw_name:
            return None
        cleaned = str(raw_name).replace("_", "").strip()
        return cleaned or None

    def _get_relation_label(
        self,
        *,
        field: Any,
        related_model: type[models.Model],
        is_reverse: bool,
    ) -> str:
        field_name = field.name if hasattr(field, "name") else field.get_accessor_name()
        field_verbose_name = str(
            getattr(
                field,
                "verbose_name",
                field_name,
            )
        )

        if not is_reverse:
            forward_label, _ = self._split_relation_verbose_name(field_verbose_name)
            return forward_label or field_verbose_name

        # Reverse relations should use the source field verbose_name when available.
        source_field = getattr(field, "field", None)
        source_verbose_name = getattr(source_field, "verbose_name", None)
        _, reverse_label = self._split_relation_verbose_name(source_verbose_name)
        if reverse_label:
            return reverse_label

        if bool(getattr(field, "many_to_many", False) or getattr(field, "one_to_many", False)):
            return str(related_model._meta.verbose_name_plural)
        if bool(getattr(field, "one_to_one", False)):
            return str(related_model._meta.verbose_name)

        fallback_name = None
        if hasattr(field, "get_accessor_name"):
            fallback_name = field.get_accessor_name()
        normalized_name = self._normalize_relation_name(fallback_name)
        return normalized_name or field_verbose_name

    def _extract_relations(
        self,
        model: type[models.Model],
        user: Any,
        *,
        instance: Optional[models.Model] = None,
        graphql_meta: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []
        field_metadata = getattr(graphql_meta, "field_metadata", None) or {}
        for field in model._meta.get_fields():
            if not field.is_relation:
                continue

            field_key = (
                field.name if hasattr(field, "name") else field.get_accessor_name()
            )

            # Keep relation exposure consistent with GraphQLMeta field policies.
            # This lets include/exclude/read_only rules hide unsupported reverse
            # relation paths from generated form contracts.
            if graphql_meta is not None:
                try:
                    if not graphql_meta.should_expose_field(
                        field_key, for_input=True
                    ):
                        continue
                except Exception:
                    pass

            rel_schema = self._extract_relation(
                model,
                field,
                user,
                instance=instance,
                field_metadata=field_metadata.get(field_key),
                graphql_meta=graphql_meta,
            )
            if rel_schema:
                relationships.append(rel_schema)
        return relationships

    def _extract_relation(
        self,
        model: type[models.Model],
        field: Any,
        user: Any,
        *,
        instance: Optional[models.Model] = None,
        field_metadata: Optional[dict[str, Any]] = None,
        graphql_meta: Optional[Any] = None,
    ) -> Optional[dict[str, Any]]:
        try:
            from graphene.utils.str_converters import to_camel_case

            is_reverse = not hasattr(field, "remote_field") or field.auto_created
            field_key = (
                field.name if hasattr(field, "name") else field.get_accessor_name()
            )
            if is_reverse:
                related_model = field.related_model
                relation_type = "REVERSE_M2M" if field.many_to_many else "REVERSE_FK"
            else:
                related_model = field.related_model
                if field.many_to_many:
                    relation_type = "MANY_TO_MANY"
                elif field.one_to_one:
                    relation_type = "ONE_TO_ONE"
                else:
                    relation_type = "FOREIGN_KEY"

            is_to_many = relation_type in ("MANY_TO_MANY", "REVERSE_FK", "REVERSE_M2M")

            readable, writable = True, True
            if user and hasattr(field, "name"):
                try:
                    perm = field_permission_manager.check_field_permission(
                        user, model, field.name, instance=instance
                    )
                    readable = perm.visibility != FieldVisibility.HIDDEN
                    writable = perm.can_write
                except Exception:
                    pass

            if related_model is None:
                return None

            operations = self._extract_relation_operations(
                model,
                field_key,
                field=field,
                is_to_many=is_to_many,
                is_reverse=is_reverse,
                graphql_meta=graphql_meta,
                user=user,
            )

            relation_label = self._get_relation_label(
                field=field,
                related_model=related_model,
                is_reverse=is_reverse,
            )

            return {
                "name": to_camel_case(field.name)
                if hasattr(field, "name")
                else to_camel_case(field.get_accessor_name()),
                "field_name": field.name
                if hasattr(field, "name")
                else field.get_accessor_name(),
                "label": relation_label,
                "description": str(getattr(field, "help_text", "") or "") or None,
                "related_app": related_model._meta.app_label,
                "related_model": related_model.__name__,
                "related_verbose_name": str(related_model._meta.verbose_name),
                "relation_type": relation_type,
                "is_to_many": bool(is_to_many),
                "required": not is_reverse and not getattr(field, "null", True),
                "read_only": not bool(getattr(field, "editable", True)),
                "disabled": False,
                "hidden": False,
                "operations": operations,
                "query_config": {
                    "query_name": None,
                    "value_field": "id",
                    "label_field": "desc",
                    "description_field": None,
                    "search_fields": [],
                    "ordering": None,
                    "limit": 50,
                    "filters": None,
                },
                "nested_form_config": self._extract_nested_form_config(
                    model, field_key, graphql_meta=graphql_meta
                ),
                "placeholder": None,
                "help_text": str(getattr(field, "help_text", "") or "") or None,
                "order": None,
                "metadata": self._serialize_metadata(field_metadata),
                "readable": readable,
                "writable": writable,
            }
        except Exception:
            logger.warning(
                "Failed to extract relation metadata for %s.%s.",
                model._meta.label,
                (
                    getattr(field, "name", None)
                    or getattr(field, "get_accessor_name", lambda: "<unknown>")()
                ),
                exc_info=True,
            )
            return None

    def _serialize_metadata(self, metadata: Any) -> Any:
        if metadata is None:
            return None
        try:
            json.dumps(metadata)
            return metadata
        except TypeError:
            return str(metadata)

    def _extract_relation_operations(
        self,
        model: type[models.Model],
        field_name: str,
        *,
        field: Any,
        is_to_many: bool,
        is_reverse: bool,
        graphql_meta: Optional[Any] = None,
        user: Any = None,
    ) -> dict[str, Any]:
        cfg = None
        if graphql_meta is not None:
            try:
                cfg = graphql_meta.get_relation_config(field_name)
            except Exception:
                cfg = None

        def _enabled(attr: str, default_value: bool = True) -> bool:
            if cfg is None:
                return default_value
            op_cfg = getattr(cfg, attr, None)
            return bool(getattr(op_cfg, "enabled", default_value))

        def _permission(attr: str) -> Optional[str]:
            if cfg is None:
                return None
            op_cfg = getattr(cfg, attr, None)
            return getattr(op_cfg, "require_permission", None)

        def _is_authenticated(target_user: Any) -> bool:
            return bool(
                target_user
                and getattr(target_user, "is_authenticated", False)
                and getattr(target_user, "pk", None) is not None
            )

        def _has_permission(permission: Optional[str], operation: str) -> bool:
            normalized = str(permission or "").strip()
            if not normalized:
                return True
            if not _is_authenticated(user):
                return False

            context = PermissionContext(
                user=user,
                model_class=model,
                object_instance=None,
                object_id=None,
                operation=operation,
            )
            try:
                return bool(role_manager.has_permission(user, normalized, context))
            except Exception:
                has_perm = getattr(user, "has_perm", None)
                if callable(has_perm):
                    try:
                        return bool(has_perm(normalized))
                    except Exception:
                        return False
                return False

        def _resolve_operation(attr: str, default_value: bool = True) -> tuple[bool, Optional[str], Optional[str]]:
            enabled = _enabled(attr, default_value)
            required_permission = _permission(attr)
            if not enabled:
                return False, required_permission, None

            if _has_permission(required_permission, operation=attr):
                return True, required_permission, None

            if required_permission:
                if not _is_authenticated(user):
                    return False, required_permission, "Authentication required"
                return False, required_permission, f"Permission required: {required_permission}"
            return False, required_permission, None

        singular_nullable = True
        if not is_to_many:
            if is_reverse:
                source_field = getattr(field, "field", None)
                singular_nullable = bool(getattr(source_field, "null", True))
            else:
                singular_nullable = bool(getattr(field, "null", True))

        disconnect_default = True if is_to_many else singular_nullable
        set_default = True if is_to_many else singular_nullable

        can_connect, connect_permission, connect_reason = _resolve_operation("connect")
        can_create, create_permission, create_reason = _resolve_operation("create")
        can_update, update_permission, update_reason = _resolve_operation("update")
        can_disconnect, disconnect_permission, disconnect_reason = _resolve_operation(
            "disconnect",
            disconnect_default,
        )
        can_set, set_permission, set_reason = _resolve_operation("set", set_default)
        can_delete, delete_permission, delete_reason = _resolve_operation(
            "delete",
            False,
        )
        can_clear, clear_permission, clear_reason = _resolve_operation("clear", False)

        if not is_to_many and not singular_nullable:
            can_disconnect = False
            can_set = False

        return {
            "can_connect": can_connect,
            "can_create": can_create,
            "can_update": can_update,
            "can_disconnect": can_disconnect,
            "can_set": can_set,
            "can_delete": can_delete,
            "can_clear": can_clear,
            "connect_permission": connect_permission,
            "create_permission": create_permission,
            "update_permission": update_permission,
            "delete_permission": delete_permission,
            "disconnect_permission": disconnect_permission,
            "set_permission": set_permission,
            "clear_permission": clear_permission,
            "connect_reason": connect_reason,
            "create_reason": create_reason,
            "update_reason": update_reason,
            "disconnect_reason": disconnect_reason,
            "set_reason": set_reason,
            "delete_reason": delete_reason,
            "clear_reason": clear_reason,
        }

    def _extract_nested_form_config(
        self,
        model: type[models.Model],
        field_name: str,
        *,
        graphql_meta: Optional[Any] = None,
    ) -> Optional[dict[str, Any]]:
        if graphql_meta is None:
            return None
        try:
            cfg = graphql_meta.get_relation_config(field_name)
        except Exception:
            cfg = None
        if cfg is None:
            return None
        nested_cfg = getattr(cfg, "nested_form", None)
        if nested_cfg is None:
            return None
        return {
            "enabled": bool(getattr(nested_cfg, "enabled", False)),
            "fields": getattr(nested_cfg, "fields", None),
            "exclude_fields": getattr(nested_cfg, "exclude_fields", None),
            "layout": getattr(nested_cfg, "layout", None),
            "max_items": getattr(nested_cfg, "max_items", None),
            "min_items": getattr(nested_cfg, "min_items", None),
        }

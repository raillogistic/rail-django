"""
Relationship extraction for Form API.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from django.db import models

from ....security.field_permissions import FieldVisibility, field_permission_manager


class RelationExtractorMixin:
    """Mixin for extracting relation configurations."""

    def _extract_relations(
        self,
        model: type[models.Model],
        user: Any,
        *,
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
            rel_schema = self._extract_relation(
                model,
                field,
                user,
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
                        user, model, field.name, instance=None
                    )
                    readable = perm.visibility != FieldVisibility.HIDDEN
                    writable = perm.can_write
                except Exception:
                    pass

            if related_model is None:
                return None

            operations = self._extract_relation_operations(
                model, field_key, graphql_meta=graphql_meta
            )

            return {
                "name": to_camel_case(field.name)
                if hasattr(field, "name")
                else to_camel_case(field.get_accessor_name()),
                "field_name": field.name
                if hasattr(field, "name")
                else field.get_accessor_name(),
                "label": str(
                    getattr(
                        field,
                        "verbose_name",
                        field.name if hasattr(field, "name") else "",
                    )
                ),
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
        graphql_meta: Optional[Any] = None,
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

        return {
            "can_connect": _enabled("connect"),
            "can_create": _enabled("create"),
            "can_update": _enabled("update"),
            "can_disconnect": _enabled("disconnect"),
            "can_set": _enabled("set"),
            "can_delete": _enabled("delete", False),
            "can_clear": _enabled("clear", False),
            "connect_permission": _permission("connect"),
            "create_permission": _permission("create"),
            "update_permission": _permission("update"),
            "delete_permission": _permission("delete"),
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

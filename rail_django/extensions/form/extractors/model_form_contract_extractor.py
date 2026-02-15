"""
Generated model-form contract extractor.
"""

from __future__ import annotations

from typing import Any, Iterable

from django.apps import apps
from django.utils import timezone
from graphene.utils.str_converters import to_camel_case
from graphql import GraphQLError

from ..config import (
    DEFAULT_BULK_ROW_PATH_PREFIX,
    DEFAULT_FORM_ERROR_KEY,
    get_generated_form_overrides,
    is_generated_form_enabled,
)
from ..utils.graphql_meta import get_model_form_mutation_bindings
from ..utils.pathing import normalize_path, split_path
from .base import FormConfigExtractor

FIELD_KIND_MAP: dict[str, str] = {
    "TEXT": "TEXT",
    "TEXTAREA": "TEXTAREA",
    "NUMBER": "NUMBER",
    "DECIMAL": "DECIMAL",
    "SWITCH": "BOOLEAN",
    "DATE": "DATE",
    "TIME": "TIME",
    "DATETIME": "DATETIME",
    "SELECT": "CHOICE",
    "MULTISELECT": "MULTI_CHOICE",
    "JSON": "JSON",
    "FILE": "FILE",
    "IMAGE": "FILE",
}


class ModelFormContractExtractor(FormConfigExtractor):
    def extract_contract(
        self,
        app_name: str,
        model_name: str,
        *,
        user: Any = None,
        mode: str = "CREATE",
        include_nested: bool = False,
        enforce_opt_in: bool = True,
    ) -> dict[str, Any]:
        model = self._resolve_model(app_name, model_name)
        if enforce_opt_in and not is_generated_form_enabled(model):
            raise GraphQLError(
                f"Generated form contract is not enabled for '{app_name}.{model_name}'."
            )

        config = self.extract(app_name, model_name, user=user, mode=mode)
        permissions = self._build_contract_permissions(config, mode=mode)
        primary_key_name = getattr(getattr(model, "_meta", None), "pk", None)
        primary_key_name = getattr(primary_key_name, "name", None)
        fields = self._build_fields(
            config,
            primary_key_name=primary_key_name,
            mode=mode,
            contract_permissions=permissions,
        )
        relations = self._build_relations(
            config,
            include_nested=include_nested,
            mode=mode,
            contract_permissions=permissions,
        )
        sections = self._build_sections(
            config,
            fields,
            model=model,
            relations=relations,
        )

        contract: dict[str, Any] = {
            "id": f"{app_name}.{model_name}.{str(mode).upper()}",
            "app_label": app_name,
            "model_name": model_name,
            "mode": str(mode).upper(),
            "version": str(config.get("version") or "1"),
            "config_version": str(config.get("config_version") or "1"),
            "generated_at": config.get("generated_at") or timezone.now(),
            "fields": fields,
            "sections": sections,
            "relations": relations,
            "permissions": permissions,
            "mutation_bindings": get_model_form_mutation_bindings(model),
            "error_policy": {
                "canonical_form_error_key": DEFAULT_FORM_ERROR_KEY,
                "field_path_notation": "dot",
                "bulk_row_prefix_pattern": f"{DEFAULT_BULK_ROW_PATH_PREFIX}.<row>.<field>",
            },
        }
        self._apply_declared_overrides(contract, model, mode=mode)
        return contract

    def extract_contract_page(
        self,
        model_refs: Iterable[dict[str, str]],
        *,
        user: Any = None,
        mode: str = "CREATE",
        include_nested: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        eligible_refs: list[dict[str, str]] = []
        for ref in model_refs or []:
            app_name = ref.get("app_label") or ref.get("app")
            model_name = ref.get("model_name") or ref.get("model")
            if not app_name or not model_name:
                continue
            try:
                model = self._resolve_model(app_name, model_name)
            except GraphQLError:
                continue
            if not is_generated_form_enabled(model):
                continue
            eligible_refs.append(
                {
                    "app_label": model._meta.app_label,
                    "model_name": model.__name__,
                }
            )

        safe_page = max(int(page or 1), 1)
        safe_per_page = max(min(int(per_page or 50), 200), 1)
        start = (safe_page - 1) * safe_per_page
        end = start + safe_per_page

        page_refs = eligible_refs[start:end]
        contracts: list[dict[str, Any]] = []
        for ref in page_refs:
            contracts.append(
                self.extract_contract(
                    ref["app_label"],
                    ref["model_name"],
                    user=user,
                    mode=mode,
                    include_nested=include_nested,
                    enforce_opt_in=False,
                )
            )

        return {
            "page": safe_page,
            "per_page": safe_per_page,
            "total": len(eligible_refs),
            "results": contracts,
        }

    def extract_initial_data_payload(
        self,
        app_name: str,
        model_name: str,
        *,
        object_id: str,
        user: Any = None,
        include_nested: bool = False,
        nested_fields: list[str] | None = None,
        runtime_overrides: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        values = self.extract_initial_values(
            app_name,
            model_name,
            object_id=object_id,
            user=user,
            include_nested=include_nested,
            nested_fields=nested_fields,
        )
        values = self._apply_runtime_overrides(values, runtime_overrides or [])
        return {
            "app_label": app_name,
            "model_name": model_name,
            "object_id": str(object_id),
            "values": values,
            "readonly_values": {},
            "loaded_at": timezone.now(),
        }

    def _resolve_model(self, app_name: str, model_name: str):
        try:
            return apps.get_model(app_name, model_name)
        except LookupError as exc:
            raise GraphQLError(f"Model '{app_name}.{model_name}' not found.") from exc

    def _build_fields(
        self,
        config: dict[str, Any],
        *,
        primary_key_name: str | None = None,
        mode: str = "CREATE",
        contract_permissions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        permission_lookup = self._build_field_permission_lookup(contract_permissions)
        is_view_mode = str(mode).upper() == "VIEW"
        fields: list[dict[str, Any]] = []
        for field in config.get("fields", []) or []:
            path = normalize_path(field.get("field_name") or field.get("name"))
            if not path:
                continue
            field_name = field.get("field_name") or path
            contract_name = (
                str(field.get("name")).strip()
                if field.get("name")
                else to_camel_case(str(field_name))
            )
            is_primary_key = (
                bool(primary_key_name)
                and str(field_name).lower() == str(primary_key_name).lower()
            )
            kind = FIELD_KIND_MAP.get(str(field.get("input_type") or "").upper(), "CUSTOM")
            permission_entry = self._resolve_field_permission_entry(
                permission_lookup,
                [
                    path,
                    str(field_name),
                    str(contract_name),
                    to_camel_case(str(field_name)),
                ],
            )
            readable = bool(permission_entry.get("can_read", True))
            writable = bool(permission_entry.get("can_write", True))
            visibility = self._normalize_visibility(permission_entry.get("visibility"))
            hidden = bool(
                field.get("hidden", False)
                or is_primary_key
                or not readable
                or visibility == "HIDDEN"
            )
            read_only = bool(
                field.get("read_only", False)
                or is_primary_key
                or not writable
                or is_view_mode
            )
            fields.append(
                {
                    "name": contract_name,
                    "path": path,
                    "field_name": field_name,
                    "label": field.get("label") or path,
                    "kind": kind,
                    "graphql_type": field.get("graphql_type") or "String",
                    "python_type": field.get("python_type") or "str",
                    "required": bool(field.get("required", False)),
                    "nullable": bool(field.get("nullable", True)),
                    "read_only": read_only,
                    "hidden": hidden,
                    "default_value": field.get("default_value"),
                    "constraints": field.get("constraints") or {},
                    "validators": field.get("validators") or [],
                    "ui": field.get("input_props") or {},
                    "metadata": field.get("metadata"),
                    "readable": readable,
                    "writable": writable,
                    "visibility": visibility,
                }
            )
        return fields

    def _build_sections(
        self,
        config: dict[str, Any],
        fields: list[dict[str, Any]],
        *,
        model: Any | None = None,
        relations: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        sections = config.get("sections") or []
        normalized_relations = relations or []
        if not sections:
            field_paths = self._build_default_section_paths(
                model=model,
                fields=fields,
                relations=normalized_relations,
            )
            return [
                {
                    "id": "default",
                    "title": None,
                    "description": None,
                    "field_paths": field_paths,
                    "order": 0,
                    "layout": None,
                    "visible": True,
                }
            ]

        normalized_sections: list[dict[str, Any]] = []
        for index, section in enumerate(sections):
            raw_fields = section.get("fields") or section.get("fieldPaths") or []
            field_paths = [normalize_path(item) for item in raw_fields if normalize_path(item)]
            normalized_sections.append(
                {
                    "id": section.get("id") or f"section_{index + 1}",
                    "title": section.get("title"),
                    "description": section.get("description"),
                    "field_paths": field_paths,
                    "order": section.get("order", index),
                    "layout": section.get("layout"),
                    "visible": bool(section.get("visible", True)),
                }
            )
        return normalized_sections

    def _build_default_section_paths(
        self,
        *,
        model: Any | None,
        fields: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> list[str]:
        known_field_paths = [
            item["path"] for item in fields if normalize_path(item.get("path"))
        ]
        known_relation_paths = [
            str(item.get("name") or item.get("path"))
            for item in relations
            if item.get("name") or normalize_path(item.get("path"))
        ]
        known_paths = set([*known_field_paths, *known_relation_paths])
        ordered_paths: list[str] = []
        seen: set[str] = set()

        def add_path(path: str | None) -> None:
            normalized = normalize_path(path)
            if not normalized or normalized in seen or normalized not in known_paths:
                return
            seen.add(normalized)
            ordered_paths.append(normalized)

        # Preserve declared model field order, including forward many-to-many
        # relations which Django stores separately.
        if model is not None and getattr(model, "_meta", None) is not None:
            local_fields = list(getattr(model._meta, "local_fields", []) or [])
            local_many_to_many = list(
                getattr(model._meta, "local_many_to_many", []) or []
            )
            declared_fields = sorted(
                [*local_fields, *local_many_to_many],
                key=lambda field: getattr(field, "creation_counter", 0),
            )
            for field in declared_fields:
                add_path(getattr(field, "name", None))

        # Keep backend extractor ordering as fallback for anything not covered
        # by declared local model fields.
        for path in known_field_paths:
            add_path(path)
        for path in known_relation_paths:
            add_path(path)

        return ordered_paths

    def _build_relations(
        self,
        config: dict[str, Any],
        *,
        include_nested: bool,
        mode: str = "CREATE",
        contract_permissions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        permission_lookup = self._build_field_permission_lookup(contract_permissions)
        is_view_mode = str(mode).upper() == "VIEW"
        relations: list[dict[str, Any]] = []
        all_actions = ("CONNECT", "CREATE", "UPDATE", "DISCONNECT", "DELETE", "SET", "CLEAR")
        for relation in config.get("relations", []) or []:
            operations = relation.get("operations") or {}
            nested_config = relation.get("nested_form_config") or {}
            relation_path = normalize_path(
                relation.get("field_name") or relation.get("name")
            ) or str(relation.get("field_name") or relation.get("name") or "").strip()
            if not relation_path:
                continue
            relation_name = relation.get("name") or to_camel_case(
                str(relation.get("field_name") or relation.get("name") or "")
            )
            permission_entry = self._resolve_field_permission_entry(
                permission_lookup,
                [
                    relation_path,
                    str(relation.get("field_name") or ""),
                    str(relation_name),
                    to_camel_case(str(relation.get("field_name") or "")),
                ],
            )
            readable = bool(permission_entry.get("can_read", True))
            writable = bool(permission_entry.get("can_write", True))
            visibility = self._normalize_visibility(permission_entry.get("visibility"))
            relation_hidden = not readable or visibility == "HIDDEN"

            allowed_actions = [
                action.upper()
                for action, enabled in {
                    "connect": operations.get("can_connect", True),
                    "create": operations.get("can_create", True),
                    "update": operations.get("can_update", True),
                    "disconnect": operations.get("can_disconnect", True),
                    "delete": operations.get("can_delete", False),
                    "set": operations.get("can_set", True),
                    "clear": operations.get("can_clear", False),
                }.items()
                if bool(enabled)
            ]
            if relation_hidden or not writable or is_view_mode:
                allowed_actions = []
            blocked_actions = [
                action.upper()
                for action in all_actions
                if action not in set(allowed_actions)
            ]
            relations.append(
                {
                    "name": relation_name,
                    "path": relation_path,
                    "label": relation.get("label") or relation.get("name"),
                    "relation_type": relation.get("relation_type"),
                    "to_many": bool(relation.get("is_to_many", False)),
                    "related_app_label": relation.get("related_app"),
                    "related_model_name": relation.get("related_model"),
                    "policy": {
                        "path": normalize_path(
                            relation.get("field_name") or relation.get("name")
                        ),
                        "allowed_actions": allowed_actions,
                        "blocked_actions": blocked_actions,
                        "nested_enabled": bool(
                            nested_config.get("enabled", False)
                        ),
                    },
                    "readable": readable,
                    "writable": writable,
                    "nested_form": nested_config
                    if include_nested
                    else None,
                }
            )
        return relations

    def _build_contract_permissions(
        self,
        config: dict[str, Any],
        *,
        mode: str,
    ) -> dict[str, Any]:
        raw_permissions = config.get("permissions") or {}
        operation_matrix = raw_permissions.get("operations") or {}

        def _normalize_operation(operation: str, fallback_allowed: bool) -> dict[str, Any]:
            details = operation_matrix.get(operation) or {}
            required_permissions = details.get("required_permissions") or []
            return {
                "allowed": bool(details.get("allowed", fallback_allowed)),
                "required_permissions": [str(item) for item in required_permissions if str(item or "").strip()],
                "requires_authentication": bool(details.get("requires_authentication", False)),
                "reason": details.get("reason"),
            }

        create = _normalize_operation("create", bool(raw_permissions.get("can_create", True)))
        update = _normalize_operation("update", bool(raw_permissions.get("can_update", True)))
        delete = _normalize_operation("delete", bool(raw_permissions.get("can_delete", True)))
        view = _normalize_operation("view", bool(raw_permissions.get("can_view", True)))

        field_permissions = []
        for entry in raw_permissions.get("field_permissions", []) or []:
            field_name = str(entry.get("field") or "").strip()
            if not field_name:
                continue
            field_permissions.append(
                {
                    "field": field_name,
                    "can_read": bool(entry.get("can_read", True)),
                    "can_write": bool(entry.get("can_write", True)),
                    "visibility": self._normalize_visibility(entry.get("visibility")),
                    "aliases": [
                        str(alias).strip()
                        for alias in (entry.get("aliases") or [])
                        if str(alias or "").strip()
                    ],
                }
            )

        return {
            "can_create": create["allowed"],
            "can_update": update["allowed"],
            "can_delete": delete["allowed"],
            "can_view": view["allowed"],
            "create": create,
            "update": update,
            "delete": delete,
            "view": view,
            "field_permissions": field_permissions,
            "mode": str(mode).upper(),
        }

    def _build_field_permission_lookup(
        self,
        contract_permissions: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        if not isinstance(contract_permissions, dict):
            return lookup
        for entry in contract_permissions.get("field_permissions", []) or []:
            if not isinstance(entry, dict):
                continue
            keys = [entry.get("field"), *(entry.get("aliases") or [])]
            for key in keys:
                normalized = normalize_path(key) or str(key or "").strip()
                if not normalized:
                    continue
                lookup[normalized] = entry
        return lookup

    def _resolve_field_permission_entry(
        self,
        permission_lookup: dict[str, dict[str, Any]],
        candidates: list[str],
    ) -> dict[str, Any]:
        for candidate in candidates:
            normalized = normalize_path(candidate) or str(candidate or "").strip()
            if not normalized:
                continue
            entry = permission_lookup.get(normalized)
            if entry is not None:
                return entry
        return {}

    def _normalize_visibility(self, value: Any) -> str:
        normalized = str(value or "").strip().upper()
        if normalized in {"VISIBLE", "HIDDEN", "MASKED", "REDACTED"}:
            return normalized
        return "VISIBLE"

    def _apply_declared_overrides(
        self,
        contract: dict[str, Any],
        model: Any,
        *,
        mode: str,
    ) -> None:
        overrides = get_generated_form_overrides(model, mode=mode)
        if not overrides:
            return

        field_overrides = overrides.get("fields") if isinstance(overrides, dict) else None
        if isinstance(field_overrides, dict):
            for field in contract.get("fields", []):
                patch = field_overrides.get(field["path"])
                if isinstance(patch, dict):
                    field.update(patch)

        section_overrides = (
            overrides.get("sections") if isinstance(overrides, dict) else None
        )
        if isinstance(section_overrides, dict):
            for section in contract.get("sections", []):
                patch = section_overrides.get(section["id"])
                if isinstance(patch, dict):
                    section.update(patch)

    def _apply_runtime_overrides(
        self,
        values: dict[str, Any],
        runtime_overrides: list[dict[str, Any]],
    ) -> dict[str, Any]:
        next_values = dict(values)
        for override in runtime_overrides:
            path = normalize_path(override.get("path"))
            if not path:
                continue
            action = str(override.get("action") or "REPLACE").upper()
            if action == "UNSET":
                self._unset_path(next_values, path)
                continue
            self._set_path(next_values, path, override.get("value"), merge=action == "MERGE")
        return next_values

    def _set_path(
        self,
        target: dict[str, Any],
        path: str,
        value: Any,
        *,
        merge: bool = False,
    ) -> None:
        parts = split_path(path)
        if not parts:
            return
        cursor: Any = target
        for token in parts[:-1]:
            if token not in cursor or not isinstance(cursor[token], dict):
                cursor[token] = {}
            cursor = cursor[token]
        leaf = parts[-1]
        if merge and isinstance(cursor.get(leaf), dict) and isinstance(value, dict):
            cursor[leaf] = {**cursor[leaf], **value}
        else:
            cursor[leaf] = value

    def _unset_path(self, target: dict[str, Any], path: str) -> None:
        parts = split_path(path)
        if not parts:
            return
        cursor: Any = target
        for token in parts[:-1]:
            next_item = cursor.get(token)
            if not isinstance(next_item, dict):
                return
            cursor = next_item
        cursor.pop(parts[-1], None)

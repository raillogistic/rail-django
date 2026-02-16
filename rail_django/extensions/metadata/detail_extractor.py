"""
Detail contract extractor.

Builds a model detail contract from existing metadata extraction output so
frontend detail rendering can stay metadata-driven and backward-compatible.
"""

from __future__ import annotations

from typing import Any, Mapping

from django.apps import apps
from graphql import GraphQLError

from .detail_actions import extract_detail_action_definitions
from .extractor import ModelSchemaExtractor


class DetailContractExtractor:
    """Resolve detail contracts from metadata + permission state."""

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name

    def extract(
        self,
        app_name: str,
        model_name: str,
        *,
        user: Any = None,
        object_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            model_cls = apps.get_model(app_name, model_name)
        except LookupError as exc:
            raise GraphQLError(f"Model '{app_name}.{model_name}' not found.") from exc

        extractor = ModelSchemaExtractor(schema_name=self.schema_name)
        model_schema = extractor.extract(
            app_name,
            model_name,
            user=user,
            object_id=object_id,
        )
        relation_data_sources = self._extract_relation_data_sources(
            model_cls,
            model_schema,
        )
        default_descriptors = self._collect_default_descriptors(model_schema)
        permission_snapshot = extractor._extract_detail_permission_snapshot(  # noqa: SLF001
            model_cls,
            user,
            schema_payload=model_schema,
        )

        default_include_fields = [descriptor["name"] for descriptor in default_descriptors]

        return {
            "app_label": app_name,
            "model_name": model_name,
            "query_root": self._resolve_query_root(model_name),
            "identifier_arg": "id",
            "layout_version": "v2",
            "default_include_fields": default_include_fields,
            "default_exclude_fields": [],
            "permissions": permission_snapshot,
            "layout_nodes": self._build_layout_nodes(model_schema, default_descriptors),
            "relation_data_sources": relation_data_sources,
            "actions": extract_detail_action_definitions(
                model_schema,
                object_id=object_id,
            ),
            "metadata_version": model_schema.get("metadata_version"),
        }

    @staticmethod
    def _resolve_query_root(model_name: str) -> str:
        if not model_name:
            return ""
        return model_name[0].lower() + model_name[1:]

    def _collect_default_descriptors(
        self,
        model_schema: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        descriptors: list[dict[str, Any]] = [
            self._to_field_descriptor(field)
            for field in (model_schema.get("fields") or [])
            if isinstance(field, Mapping) and field.get("readable", False)
        ]
        seen = {entry["name"] for entry in descriptors}

        # Ensure readable forward to-one relations are available in defaults.
        for relation in (model_schema.get("relationships") or []):
            if not isinstance(relation, Mapping):
                continue
            if relation.get("is_reverse", False):
                continue
            if not relation.get("is_to_one", False):
                continue
            if not relation.get("readable", False):
                continue

            relation_name = str(relation.get("name") or "").strip()
            if not relation_name or relation_name in seen:
                continue
            descriptors.append(
                {
                    "name": relation_name,
                    "title": relation.get("verbose_name") or relation_name,
                    "type": "RelationField",
                    "include": True,
                    "exclude": False,
                    "nested": {"mode": "SECTION"},
                    "formatter_key": None,
                    "permission_key": relation_name,
                }
            )
            seen.add(relation_name)

        return descriptors

    def _build_layout_nodes(
        self,
        model_schema: Mapping[str, Any],
        default_descriptors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        fields: list[Mapping[str, Any]] = [
            field
            for field in (model_schema.get("fields") or [])
            if isinstance(field, Mapping) and field.get("readable", False)
        ]

        field_map: dict[str, Mapping[str, Any]] = {
            str(field.get("name")): field
            for field in fields
            if field.get("name")
        }
        groups = [
            group
            for group in (model_schema.get("field_groups") or [])
            if isinstance(group, Mapping)
        ]
        template_keys = [
            str(template.get("key"))
            for template in (model_schema.get("templates") or [])
            if isinstance(template, Mapping) and template.get("key")
        ]

        if groups:
            nodes: list[dict[str, Any]] = []
            for index, group in enumerate(groups):
                group_fields = [
                    self._to_field_descriptor(field_map[name]) for name in (group.get("fields") or []) if name in field_map
                ]
                if not group_fields:
                    continue
                nodes.append(
                    {
                        "id": group.get("key") or f"group-{index}",
                        "type": "SECTION",
                        "title": group.get("label"),
                        "order": index,
                        "fields": group_fields,
                        "children": [],
                        "relation_source_id": None,
                        "visibility_rule": {
                            "group": {
                                "description": group.get("description"),
                                "collapsed": bool(group.get("collapsed", False)),
                            },
                            "templates": template_keys,
                        },
                        "actions": [],
                    }
                )
        else:
            nodes = [
                {
                    "id": "default-section",
                    "type": "SECTION",
                    "title": "Details",
                    "order": 0,
                    "fields": default_descriptors,
                    "children": [],
                    "relation_source_id": None,
                    "visibility_rule": {
                        "group": {
                            "description": None,
                            "collapsed": False,
                        },
                        "templates": template_keys,
                    },
                    "actions": [],
                }
            ]

        reverse_relations = [
            relation
            for relation in (model_schema.get("relationships") or [])
            if isinstance(relation, Mapping)
            and relation.get("readable", False)
            and relation.get("is_reverse", False)
            and relation.get("is_to_many", False)
        ]

        next_order = len(nodes)
        for relation in reverse_relations:
            relation_name = str(relation.get("name"))
            nodes.append(
                {
                    "id": f"relation-{relation_name}",
                    "type": "TABLE",
                    "title": relation.get("verbose_name") or relation_name,
                    "order": next_order,
                    "fields": [],
                    "children": [],
                    "relation_source_id": relation_name,
                    "visibility_rule": {
                        "group": {
                            "description": None,
                            "collapsed": False,
                        },
                        "templates": template_keys,
                    },
                    "actions": [],
                }
            )
            next_order += 1
        return nodes

    def _extract_relation_data_sources(
        self,
        model_cls: type,
        model_schema: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        max_depth = self._resolve_max_depth(model_schema)
        root_label = model_cls._meta.label

        sources: list[dict[str, Any]] = []
        for relation in model_schema.get("relationships", []) or []:
            if not isinstance(relation, Mapping):
                continue
            if not relation.get("readable", False):
                continue

            relation_name = str(relation.get("name") or "").strip()
            related_app = str(relation.get("related_app") or "").strip()
            related_model = str(relation.get("related_model") or "").strip()
            if not relation_name or not related_app or not related_model:
                continue

            direction = "REVERSE" if relation.get("is_reverse", False) else "FORWARD"
            is_to_many = bool(relation.get("is_to_many", False))
            mode = "TABLE" if is_to_many else "SECTION"
            load_strategy = "LAZY" if is_to_many else "PRIMARY"
            query_name = self._build_page_query_name(related_model)
            lookup_field = relation.get("lookup_field")
            cache_key = (
                f"{model_cls._meta.app_label}.{model_cls.__name__}:{relation_name}"
            )

            guard_state = self._walk_relation_graph_guard(
                root_label=root_label,
                related_app=related_app,
                related_model=related_model,
                max_depth=max_depth,
            )
            if guard_state["blocked"]:
                continue

            pagination = (
                {
                    "page_arg": "page",
                    "per_page_arg": "perPage",
                    "default_per_page": 20,
                    "max_depth": max_depth,
                    "cycle_guard_enabled": True,
                    "cycle_detected": bool(guard_state.get("cycle_detected", False)),
                    "guard_path": guard_state["path"],
                    "depth": guard_state["depth"],
                }
                if is_to_many
                else {
                    "max_depth": max_depth,
                    "cycle_guard_enabled": True,
                    "cycle_detected": bool(guard_state.get("cycle_detected", False)),
                    "guard_path": guard_state["path"],
                    "depth": guard_state["depth"],
                }
            )

            sources.append(
                {
                    "id": relation_name,
                    "relation_name": relation_name,
                    "related_app": related_app,
                    "related_model": related_model,
                    "direction": direction,
                    "mode": mode,
                    "load_strategy": load_strategy,
                    "query_name": query_name,
                    "lookup_field": lookup_field,
                    "pagination": pagination,
                    "cache_key": cache_key,
                }
            )
        return sources

    @staticmethod
    def _resolve_max_depth(model_schema: Mapping[str, Any]) -> int:
        default_depth = 3
        custom_metadata = model_schema.get("custom_metadata")
        if not isinstance(custom_metadata, Mapping):
            return default_depth
        detail_meta = custom_metadata.get("detail")
        if not isinstance(detail_meta, Mapping):
            return default_depth
        value = detail_meta.get("max_depth")
        if isinstance(value, int) and value > 0:
            return value
        return default_depth

    @staticmethod
    def _build_page_query_name(model_name: str) -> str:
        if not model_name:
            return "page"
        token = model_name[0].lower() + model_name[1:]
        return f"{token}Page"

    def _walk_relation_graph_guard(
        self,
        *,
        root_label: str,
        related_app: str,
        related_model: str,
        max_depth: int,
    ) -> dict[str, Any]:
        """
        Walk relation graph to enforce depth limits and cycle protection.
        """
        try:
            start_model = apps.get_model(related_app, related_model)
        except LookupError:
            return {"blocked": True, "depth": 0, "path": [root_label]}

        seen_paths: set[tuple[str, ...]] = set()
        start_label = start_model._meta.label
        stack: list[tuple[type, list[str], int]] = [
            (start_model, [root_label, start_label], 1)
        ]
        best_depth = 1
        best_path = [root_label, start_label]
        cycle_detected = start_label == root_label

        while stack:
            current_model, path, depth = stack.pop()
            path_key = tuple(path)
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)

            if depth > best_depth:
                best_depth = depth
                best_path = path

            if depth >= max_depth:
                continue

            for field in current_model._meta.get_fields():
                if not getattr(field, "is_relation", False):
                    continue
                related = getattr(field, "related_model", None)
                if related is None or not hasattr(related, "_meta"):
                    continue
                related_label = related._meta.label
                if related_label in path:
                    cycle_detected = True
                    continue
                stack.append((related, [*path, related_label], depth + 1))

        return {
            "blocked": False,
            "depth": best_depth,
            "path": best_path,
            "cycle_detected": cycle_detected,
        }

    @staticmethod
    def _to_field_descriptor(field: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "name": field.get("name"),
            "title": field.get("verbose_name"),
            "type": field.get("field_type"),
            "include": True,
            "exclude": False,
            "nested": None,
            "formatter_key": None,
            "permission_key": field.get("name"),
        }

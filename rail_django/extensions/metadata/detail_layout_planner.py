"""
Detail layout planner.

Builds layout nodes and relation data sources from model metadata. The planner
centralizes detail-view structure decisions so extractor orchestration stays
thin and testable.
"""

from __future__ import annotations

from typing import Any, Mapping

from django.apps import apps
from graphene.utils.str_converters import to_camel_case
from graphql import GraphQLError

from .extractor import ModelSchemaExtractor


class DetailLayoutPlanner:
    """Plan detail layout and relation sources from metadata."""

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name

    def plan(
        self,
        *,
        model_cls: type,
        model_schema: Mapping[str, Any],
        user: Any = None,
        nested: list[str] | None = None,
    ) -> dict[str, Any]:
        nested_targets = self._resolve_nested_targets(model_schema, nested=nested)
        default_descriptors = self._collect_default_descriptors(model_schema)

        return {
            "default_descriptors": default_descriptors,
            "default_include_fields": [
                descriptor["name"] for descriptor in default_descriptors
            ],
            "layout_nodes": self._build_layout_nodes(
                model_schema,
                default_descriptors,
                nested_targets=nested_targets,
                user=user,
            ),
            "relation_data_sources": self._extract_relation_data_sources(
                model_cls,
                model_schema,
                nested_targets=nested_targets,
            ),
            "nested_targets": nested_targets,
        }

    @staticmethod
    def _normalize_nested(nested: list[str] | None) -> list[str]:
        if not nested:
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for entry in nested:
            candidate = to_camel_case(str(entry or "").strip())
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return normalized

    def _resolve_nested_targets(
        self,
        model_schema: Mapping[str, Any],
        *,
        nested: list[str] | None = None,
    ) -> list[Mapping[str, Any]]:
        requested = self._normalize_nested(nested)
        if not requested:
            return []
        relationships = [
            relation
            for relation in (model_schema.get("relationships") or [])
            if isinstance(relation, Mapping) and relation.get("readable", False)
        ]
        by_name: dict[str, Mapping[str, Any]] = {
            str(relation.get("name") or "").strip(): relation for relation in relationships
        }
        resolved: list[Mapping[str, Any]] = []
        missing: list[str] = []
        for target_name in requested:
            relation = by_name.get(target_name)
            if relation is None:
                missing.append(target_name)
                continue
            resolved.append(relation)

        if missing:
            joined = ", ".join(missing)
            raise GraphQLError(
                f"Nested relations are not readable on this model: {joined}."
            )

        return resolved

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
        *,
        nested_targets: list[Mapping[str, Any]] | None = None,
        user: Any = None,
    ) -> list[dict[str, Any]]:
        fields: list[Mapping[str, Any]] = [
            field
            for field in (model_schema.get("fields") or [])
            if isinstance(field, Mapping) and field.get("readable", False)
        ]

        field_map: dict[str, Mapping[str, Any]] = {
            str(field.get("name")): field for field in fields if field.get("name")
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
                    self._to_field_descriptor(field_map[name])
                    for name in (group.get("fields") or [])
                    if name in field_map
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

        next_order = len(nodes)

        if nested_targets:
            nested_target_names = {
                str(target.get("name") or "").strip()
                for target in nested_targets
                if str(target.get("name") or "").strip()
            }
            parent_app = str(model_schema.get("app") or "").strip()
            parent_model = str(model_schema.get("model") or "").strip()
            if nested_target_names:
                for node in nodes:
                    fields = node.get("fields") or []
                    node["fields"] = [
                        descriptor
                        for descriptor in fields
                        if str(descriptor.get("name") or "").strip()
                        not in nested_target_names
                    ]

            for nested_target in nested_targets:
                relation_name = str(nested_target.get("name") or "").strip()
                if not relation_name:
                    continue
                if bool(nested_target.get("is_to_many", False)):
                    nodes.append(
                        self._build_relation_table_node(
                            relation=nested_target,
                            relation_name=relation_name,
                            order=next_order,
                            template_keys=template_keys,
                            user=user,
                            parent_app=parent_app,
                            parent_model=parent_model,
                        )
                    )
                else:
                    nodes.append(
                        self._build_relation_section_node(
                            relation=nested_target,
                            relation_name=relation_name,
                            order=next_order,
                            template_keys=template_keys,
                            user=user,
                        )
                    )
                next_order += 1
            return nodes

        # Backward-compatible default: append reverse to-many relations as tables.
        reverse_relations = [
            relation
            for relation in (model_schema.get("relationships") or [])
            if isinstance(relation, Mapping)
            and relation.get("readable", False)
            and relation.get("is_reverse", False)
            and relation.get("is_to_many", False)
        ]

        for relation in reverse_relations:
            relation_name = str(relation.get("name"))
            nodes.append(
                self._build_relation_table_node(
                    relation=relation,
                    relation_name=relation_name,
                    order=next_order,
                    template_keys=template_keys,
                    user=user,
                    parent_app=str(model_schema.get("app") or "").strip(),
                    parent_model=str(model_schema.get("model") or "").strip(),
                )
            )
            next_order += 1
        return nodes

    def _build_relation_table_node(
        self,
        *,
        relation: Mapping[str, Any],
        relation_name: str,
        order: int,
        template_keys: list[str],
        user: Any = None,
        parent_app: str | None = None,
        parent_model: str | None = None,
    ) -> dict[str, Any]:
        fields = self._extract_related_table_fields(
            relation,
            user=user,
            parent_app=parent_app,
            parent_model=parent_model,
        )
        return {
            "id": f"relation-{relation_name}",
            "type": "TABLE",
            "title": relation.get("verbose_name") or relation_name,
            "order": order,
            "fields": fields,
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

    def _build_relation_section_node(
        self,
        *,
        relation: Mapping[str, Any],
        relation_name: str,
        order: int,
        template_keys: list[str],
        user: Any = None,
    ) -> dict[str, Any]:
        fields = self._extract_related_fields(relation, user=user)
        return {
            "id": f"relation-{relation_name}",
            "type": "SECTION",
            "title": relation.get("verbose_name") or relation_name,
            "order": order,
            "fields": fields,
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

    def _extract_related_table_fields(
        self,
        relation: Mapping[str, Any],
        *,
        user: Any = None,
        parent_app: str | None = None,
        parent_model: str | None = None,
    ) -> list[dict[str, Any]]:
        fields = self._extract_related_fields(relation, user=user)
        table_relation_fields = self._extract_related_to_one_relation_fields(
            relation,
            user=user,
            parent_app=parent_app,
            parent_model=parent_model,
        )
        if table_relation_fields:
            seen = {
                str(descriptor.get("name") or "").strip()
                for descriptor in fields
                if str(descriptor.get("name") or "").strip()
            }
            for descriptor in table_relation_fields:
                name = str(descriptor.get("name") or "").strip()
                if not name or name in seen:
                    continue
                fields.append(descriptor)
                seen.add(name)

        return fields

    def _extract_related_to_one_relation_fields(
        self,
        relation: Mapping[str, Any],
        *,
        user: Any = None,
        parent_app: str | None = None,
        parent_model: str | None = None,
    ) -> list[dict[str, Any]]:
        related_app = str(relation.get("related_app") or "").strip()
        related_model = str(relation.get("related_model") or "").strip()
        if not related_app or not related_model:
            return []

        extractor = ModelSchemaExtractor(schema_name=self.schema_name)
        try:
            related_schema = extractor.extract(related_app, related_model, user=user)
        except Exception:
            return []

        descriptors: list[dict[str, Any]] = []
        for rel in (related_schema.get("relationships") or []):
            if not isinstance(rel, Mapping):
                continue
            if rel.get("is_reverse", False):
                continue
            if not rel.get("is_to_one", False):
                continue
            if not rel.get("readable", False):
                continue
            relation_name = str(rel.get("name") or "").strip()
            if not relation_name:
                continue
            rel_target_app = str(rel.get("related_app") or "").strip()
            rel_target_model = str(rel.get("related_model") or "").strip()
            if (
                parent_app
                and parent_model
                and rel_target_app == str(parent_app).strip()
                and rel_target_model == str(parent_model).strip()
            ):
                continue
            descriptors.append(
                {
                    "name": relation_name,
                    "title": rel.get("verbose_name") or relation_name,
                    "type": "RelationField",
                    "include": True,
                    "exclude": False,
                    "nested": {"mode": "SECTION"},
                    "formatter_key": None,
                    "permission_key": relation_name,
                }
            )
        return descriptors

    def _extract_related_fields(
        self,
        relation: Mapping[str, Any],
        *,
        user: Any = None,
    ) -> list[dict[str, Any]]:
        related_app = str(relation.get("related_app") or "").strip()
        related_model = str(relation.get("related_model") or "").strip()
        if not related_app or not related_model:
            return []

        extractor = ModelSchemaExtractor(schema_name=self.schema_name)
        try:
            related_schema = extractor.extract(related_app, related_model, user=user)
        except Exception:
            return []

        return [
            self._to_field_descriptor(field)
            for field in (related_schema.get("fields") or [])
            if isinstance(field, Mapping) and field.get("readable", False)
        ]

    def _extract_relation_data_sources(
        self,
        model_cls: type,
        model_schema: Mapping[str, Any],
        *,
        nested_targets: list[Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        max_depth = self._resolve_max_depth(model_schema)
        root_label = model_cls._meta.label
        nested_target_names = {
            str(target.get("name") or "").strip()
            for target in (nested_targets or [])
            if str(target.get("name") or "").strip()
        }

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
            if nested_target_names and relation_name not in nested_target_names and is_to_many:
                mode = "SECTION"
            load_strategy = "LAZY" if mode == "TABLE" else "PRIMARY"
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
                if mode == "TABLE"
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

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
from .detail_layout_planner import DetailLayoutPlanner


class DetailContractExtractor:
    """Resolve detail contracts from metadata + permission state."""

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name
        self.layout_planner = DetailLayoutPlanner(schema_name=schema_name)

    def extract(
        self,
        app_name: str,
        model_name: str,
        *,
        user: Any = None,
        object_id: str | None = None,
        nested: list[str] | None = None,
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
        plan = self.layout_planner.plan(
            model_cls=model_cls,
            model_schema=model_schema,
            user=user,
            nested=nested,
        )
        permission_snapshot = extractor._extract_detail_permission_snapshot(  # noqa: SLF001
            model_cls,
            user,
            schema_payload=model_schema,
        )

        return {
            "app_label": app_name,
            "model_name": model_name,
            "query_root": self._resolve_query_root(model_name),
            "identifier_arg": "id",
            "layout_version": "v2",
            "default_include_fields": plan["default_include_fields"],
            "default_exclude_fields": [],
            "permissions": permission_snapshot,
            "layout_nodes": plan["layout_nodes"],
            "relation_data_sources": plan["relation_data_sources"],
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
        return self.layout_planner._collect_default_descriptors(model_schema)

    def _build_layout_nodes(
        self,
        model_schema: Mapping[str, Any],
        default_descriptors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self.layout_planner._build_layout_nodes(
            model_schema,
            default_descriptors,
        )

    def _extract_relation_data_sources(
        self,
        model_cls: type,
        model_schema: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.layout_planner._extract_relation_data_sources(
            model_cls,
            model_schema,
        )

    @staticmethod
    def _resolve_max_depth(model_schema: Mapping[str, Any]) -> int:
        return DetailLayoutPlanner._resolve_max_depth(model_schema)

    @staticmethod
    def _build_page_query_name(model_name: str) -> str:
        return DetailLayoutPlanner._build_page_query_name(model_name)

    def _walk_relation_graph_guard(
        self,
        *,
        root_label: str,
        related_app: str,
        related_model: str,
        max_depth: int,
    ) -> dict[str, Any]:
        return self.layout_planner._walk_relation_graph_guard(
            root_label=root_label,
            related_app=related_app,
            related_model=related_model,
            max_depth=max_depth,
        )

    @staticmethod
    def _to_field_descriptor(field: Mapping[str, Any]) -> dict[str, Any]:
        return DetailLayoutPlanner._to_field_descriptor(field)

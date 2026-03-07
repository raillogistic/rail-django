"""
FormConfigExtractor implementation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import timezone
from graphql import GraphQLError

from .field_extractor import FieldExtractorMixin
from .relation_extractor import RelationExtractorMixin
from .permission_extractor import PermissionExtractorMixin
from .validation_extractor import ValidationExtractorMixin
from .automation_extractor import AutomationExtractorMixin
from ..utils.cache import (
    compute_config_version,
    get_cached_config,
    get_form_version,
    set_cached_config,
)
from ..config import get_form_settings
from ..utils.graphql_meta import get_graphql_meta
from ....utils.history_detection import (
    is_historical_records_attribute,
    is_historical_relation_field,
)

logger = logging.getLogger(__name__)


class FormConfigExtractor(
    FieldExtractorMixin,
    RelationExtractorMixin,
    PermissionExtractorMixin,
    ValidationExtractorMixin,
    AutomationExtractorMixin,
):
    """Main extractor for Form API configuration."""

    def __init__(self, schema_name: str = "default") -> None:
        self.schema_name = schema_name

    def extract(
        self,
        app_name: str,
        model_name: str,
        *,
        user: Any = None,
        object_id: Optional[str] = None,
        mode: str = "CREATE",
        instance: Optional[models.Model] = None,
    ) -> dict[str, Any]:
        user_id = str(user.pk) if user and hasattr(user, "pk") else None
        cached = get_cached_config(
            app_name, model_name, user_id=user_id, object_id=object_id, mode=mode
        )
        if cached:
            return cached

        try:
            model = apps.get_model(app_name, model_name)
        except LookupError:
            raise GraphQLError(f"Model '{app_name}.{model_name}' not found.")

        graphql_meta = get_graphql_meta(model)

        if instance is None and object_id:
            instance = self._load_instance(model, object_id=object_id)

        fields = self._extract_fields(
            model, user, instance=instance, graphql_meta=graphql_meta
        )
        relations = self._extract_relations(
            model, user, instance=instance, graphql_meta=graphql_meta
        )

        permissions = self._extract_permissions(
            model,
            user,
            fields=fields,
            relations=relations,
            graphql_meta=graphql_meta,
            instance=instance,
            mode=mode,
        )
        operation_permissions = permissions.get("operations", {})
        create_access = operation_permissions.get("create", {})
        update_access = operation_permissions.get("update", {})
        delete_access = operation_permissions.get("delete", {})

        conditional_rules = self._extract_conditional_rules(
            model, graphql_meta=graphql_meta
        )
        computed_fields = self._extract_computed_fields(
            model, graphql_meta=graphql_meta
        )
        validation_rules = self._extract_validation_rules(
            model, graphql_meta=graphql_meta
        )

        sections = getattr(graphql_meta, "form_sections", None)
        if sections is None:
            sections = getattr(graphql_meta, "sections", None)

        from graphene.utils.str_converters import to_camel_case

        config: dict[str, Any] = {
            "id": f"{app_name}.{model_name}",
            "app": app_name,
            "model": model_name,
            "verbose_name": str(model._meta.verbose_name),
            "verbose_name_plural": str(model._meta.verbose_name_plural),
            "fields": fields,
            "relations": relations,
            "sections": sections,
            "create_mutation": {
                "name": f"create{model_name}",
                "operation": "CREATE",
                "description": f"Create {model._meta.verbose_name}",
                "input_fields": [],
                "allowed": bool(create_access.get("allowed", permissions.get("can_create", True))),
                "permission": ", ".join(create_access.get("required_permissions", []))
                or None,
                "denial_reason": create_access.get("reason"),
                "success_message": None,
                "requires_optimistic_lock": False,
                "optimistic_lock_field": None,
            },
            "update_mutation": {
                "name": f"update{model_name}",
                "operation": "UPDATE",
                "description": f"Update {model._meta.verbose_name}",
                "input_fields": [],
                "allowed": bool(update_access.get("allowed", permissions.get("can_update", True))),
                "permission": ", ".join(update_access.get("required_permissions", []))
                or None,
                "denial_reason": update_access.get("reason"),
                "success_message": None,
                "requires_optimistic_lock": True,
                "optimistic_lock_field": to_camel_case("updated_at")
                if hasattr(model, "updated_at")
                else None,
            },
            "delete_mutation": {
                "name": f"delete{model_name}",
                "operation": "DELETE",
                "description": f"Delete {model._meta.verbose_name}",
                "input_fields": [],
                "allowed": bool(delete_access.get("allowed", permissions.get("can_delete", True))),
                "permission": ", ".join(delete_access.get("required_permissions", []))
                or None,
                "denial_reason": delete_access.get("reason"),
                "success_message": None,
                "requires_optimistic_lock": False,
                "optimistic_lock_field": None,
            },
            "custom_mutations": [],
            "permissions": permissions,
            "conditional_rules": conditional_rules,
            "computed_fields": computed_fields,
            "validation_rules": validation_rules,
            "version": get_form_version(app_name, model_name),
            "generated_at": timezone.now(),
        }

        config["config_version"] = compute_config_version(config)

        set_cached_config(
            app_name,
            model_name,
            config,
            user_id=user_id,
            object_id=object_id,
            mode=mode,
        )

        return config

    def extract_initial_values(
        self,
        app_name: str,
        model_name: str,
        *,
        object_id: str,
        user: Any = None,
        include_nested: bool = False,
        nested_fields: Optional[list[str]] = None,
        max_nested_depth: int = 2,
        instance: Optional[models.Model] = None,
    ) -> dict[str, Any]:
        try:
            model = apps.get_model(app_name, model_name)
        except LookupError:
            raise GraphQLError(f"Model '{app_name}.{model_name}' not found.")

        from graphene.utils.str_converters import to_camel_case

        graphql_meta = get_graphql_meta(model)
        relation_limit = int(get_form_settings().initial_data_relation_limit)

        nested_field_set: set[str] = set()
        for item in nested_fields or []:
            normalized = str(item or "").strip()
            if normalized:
                nested_field_set.add(normalized)

        if instance is None:
            instance = self._load_instance(
                model,
                object_id=object_id,
                graphql_meta=graphql_meta,
                include_nested=include_nested,
                nested_field_set=nested_field_set,
                max_nested_depth=max_nested_depth,
            )
        if instance is None:
            raise GraphQLError(
                f"Instance '{app_name}.{model_name}' with id {object_id} not found."
            )

        def should_include_nested_relation(field_name: str) -> bool:
            if nested_field_set:
                return field_name in nested_field_set or (
                    to_camel_case(field_name) in nested_field_set
                )
            return include_nested

        data: dict[str, Any] = {}
        for field in model._meta.get_fields():
            field_name = getattr(field, "name", None)
            if field_name and is_historical_records_attribute(model, field_name):
                continue
            if is_historical_relation_field(field):
                continue
            if field_name and graphql_meta is not None:
                try:
                    if not graphql_meta.should_expose_field(field_name, for_input=True):
                        continue
                except Exception:
                    logger.debug(
                        "Failed to evaluate field exposure for initial data: %s.%s.",
                        model._meta.label,
                        field_name,
                    )

            if field.is_relation:
                # For relations, return ids
                if not hasattr(field, "name"):
                    continue
                if field.one_to_many or field.many_to_many or field.one_to_one or field.many_to_one:
                    include_this_relation_nested = should_include_nested_relation(
                        field.name
                    )
                    try:
                        if field.many_to_many or field.one_to_many:
                            related_manager = getattr(instance, field.name, None)
                            if related_manager is not None:
                                relation_qs = related_manager.all()
                                if include_this_relation_nested:
                                    relation_qs = self._optimize_related_queryset(
                                        relation_qs,
                                        max_depth=max_nested_depth - 1,
                                    )
                                if relation_limit > 0:
                                    relation_qs = relation_qs[:relation_limit]
                                if include_this_relation_nested:
                                    exclude_relations: set[str] = set()
                                    if field.one_to_many:
                                        remote_field = getattr(field, "field", None)
                                        remote_field_name = getattr(
                                            remote_field, "name", None
                                        )
                                        if remote_field_name:
                                            exclude_relations.add(
                                                str(remote_field_name)
                                            )
                                    data[field.name] = [
                                        self._serialize_related_instance(
                                            obj,
                                            depth=1,
                                            max_depth=max_nested_depth,
                                            exclude_relation_fields=exclude_relations,
                                        )
                                        for obj in relation_qs
                                    ]
                                else:
                                    try:
                                        data[field.name] = list(
                                            relation_qs.values_list("pk", flat=True)
                                        )
                                    except Exception:
                                        data[field.name] = [
                                            obj.pk for obj in relation_qs
                                        ]
                        else:
                            related_obj = getattr(instance, field.name, None)
                            if include_this_relation_nested and related_obj is not None:
                                data[field.name] = self._serialize_related_instance(
                                    related_obj,
                                    depth=1,
                                    max_depth=max_nested_depth,
                                )
                            else:
                                data[field.name] = (
                                    related_obj.pk if related_obj else None
                                )
                    except Exception:
                        logger.debug(
                            "Failed to extract relation initial value for %s.%s.",
                            model._meta.label,
                            field.name,
                            exc_info=True,
                        )
                        data[field.name] = None
                continue

            try:
                value = getattr(instance, field.name)
                data[field.name] = self._to_json_value(value)
            except Exception:
                logger.debug(
                    "Failed to extract scalar initial value for %s.%s.",
                    model._meta.label,
                    field.name,
                    exc_info=True,
                )
                data[field.name] = None

        # Convert keys to camelCase for frontend consistency
        return {to_camel_case(k): v for k, v in data.items()}

    def _load_instance(
        self,
        model: type[models.Model],
        *,
        object_id: str,
        graphql_meta: Optional[Any] = None,
        include_nested: bool = False,
        nested_field_set: Optional[set[str]] = None,
        max_nested_depth: int = 2,
    ) -> Optional[models.Model]:
        queryset = model.objects.all()
        queryset = self._apply_initial_value_queryset_optimizations(
            queryset,
            model,
            graphql_meta=graphql_meta,
            include_nested=include_nested,
            nested_field_set=nested_field_set,
            max_nested_depth=max_nested_depth,
        )
        try:
            return queryset.get(pk=object_id)
        except (model.DoesNotExist, ObjectDoesNotExist, TypeError, ValueError):
            return None

    def _apply_initial_value_queryset_optimizations(
        self,
        queryset: models.QuerySet,
        model: type[models.Model],
        *,
        graphql_meta: Optional[Any] = None,
        include_nested: bool = False,
        nested_field_set: Optional[set[str]] = None,
        max_nested_depth: int = 2,
    ) -> models.QuerySet:
        select_related_paths, prefetch_related_paths = self._collect_relation_paths(
            model,
            graphql_meta=graphql_meta,
            include_nested=include_nested,
            nested_field_set=nested_field_set,
            max_nested_depth=max_nested_depth,
        )
        if select_related_paths:
            queryset = queryset.select_related(*sorted(select_related_paths))
        if prefetch_related_paths:
            queryset = queryset.prefetch_related(*sorted(prefetch_related_paths))
        return queryset

    def _collect_relation_paths(
        self,
        model: type[models.Model],
        *,
        graphql_meta: Optional[Any] = None,
        include_nested: bool = False,
        nested_field_set: Optional[set[str]] = None,
        max_nested_depth: int = 2,
        prefix: str = "",
        depth: int = 0,
        force_prefetch: bool = False,
        visited: Optional[set[tuple[type[models.Model], int]]] = None,
    ) -> tuple[set[str], set[str]]:
        if visited is None:
            visited = set()
        visit_key = (model, depth)
        if visit_key in visited:
            return set(), set()
        visited.add(visit_key)

        select_related_paths: set[str] = set()
        prefetch_related_paths: set[str] = set()
        normalized_nested = {
            str(item).strip()
            for item in (nested_field_set or set())
            if str(item).strip()
        }

        for field in model._meta.get_fields():
            field_name = getattr(field, "name", None)
            if not field.is_relation or not field_name:
                continue
            if is_historical_records_attribute(model, field_name):
                continue
            if is_historical_relation_field(field):
                continue
            if graphql_meta is not None:
                try:
                    if not graphql_meta.should_expose_field(field_name, for_input=True):
                        continue
                except Exception:
                    pass

            path = f"{prefix}{field_name}" if prefix else field_name
            is_multi_relation = bool(field.many_to_many or field.one_to_many)
            should_prefetch = force_prefetch or is_multi_relation
            if should_prefetch:
                prefetch_related_paths.add(path)
            else:
                select_related_paths.add(path)

            include_relation = include_nested
            if normalized_nested:
                include_relation = (
                    field_name in normalized_nested
                    or path in normalized_nested
                )
            related_model = getattr(field, "related_model", None)
            if (
                include_relation
                and related_model is not None
                and depth + 1 < max_nested_depth
            ):
                related_meta = get_graphql_meta(related_model)
                child_select, child_prefetch = self._collect_relation_paths(
                    related_model,
                    graphql_meta=related_meta,
                    include_nested=True,
                    nested_field_set=None,
                    max_nested_depth=max_nested_depth,
                    prefix=f"{path}__",
                    depth=depth + 1,
                    force_prefetch=should_prefetch,
                    visited=visited,
                )
                select_related_paths.update(child_select)
                prefetch_related_paths.update(child_prefetch)

        return select_related_paths, prefetch_related_paths

    def _optimize_related_queryset(
        self,
        queryset: models.QuerySet,
        *,
        max_depth: int,
    ) -> models.QuerySet:
        model = queryset.model
        return self._apply_initial_value_queryset_optimizations(
            queryset,
            model,
            graphql_meta=get_graphql_meta(model),
            include_nested=max_depth > 1,
            nested_field_set=None,
            max_nested_depth=max_depth,
        )

    def _serialize_related_instance(
        self,
        instance: models.Model,
        *,
        depth: int,
        max_depth: int,
        exclude_relation_fields: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        from graphene.utils.str_converters import to_camel_case

        payload: dict[str, Any] = {"id": getattr(instance, "pk", None)}
        if depth > max_depth:
            return payload

        graphql_meta = get_graphql_meta(instance.__class__)
        relation_limit = int(get_form_settings().initial_data_relation_limit)
        excluded_relations = {str(name) for name in (exclude_relation_fields or set())}
        for field in instance._meta.get_fields():
            if not hasattr(field, "name"):
                continue
            if is_historical_records_attribute(instance.__class__, field.name):
                continue
            if is_historical_relation_field(field):
                continue
            if field.is_relation and field.name in excluded_relations:
                continue
            try:
                if not graphql_meta.should_expose_field(field.name, for_input=True):
                    continue
            except Exception:
                logger.debug(
                    "Failed to evaluate nested field exposure for %s.%s.",
                    instance.__class__._meta.label,
                    field.name,
                )
            if field.is_relation:
                if depth >= max_depth:
                    continue
                try:
                    if (
                        field.many_to_many
                        or field.one_to_many
                    ):
                        related_manager = getattr(instance, field.name, None)
                        if related_manager is None:
                            payload[to_camel_case(field.name)] = []
                            continue
                        relation_qs = self._optimize_related_queryset(
                            related_manager.all(),
                            max_depth=max_depth - depth,
                        )
                        if relation_limit > 0:
                            relation_qs = relation_qs[:relation_limit]
                        try:
                            payload[to_camel_case(field.name)] = list(
                                relation_qs.values_list("pk", flat=True)
                            )
                        except Exception:
                            payload[to_camel_case(field.name)] = [
                                obj.pk for obj in relation_qs
                            ]
                    else:
                        related_obj = getattr(instance, field.name, None)
                        payload[to_camel_case(field.name)] = (
                            related_obj.pk if related_obj else None
                        )
                except Exception:
                    logger.debug(
                        "Failed to serialize nested relation field %s.%s.",
                        instance.__class__._meta.label,
                        field.name,
                        exc_info=True,
                    )
                    if field.many_to_many or field.one_to_many:
                        payload[to_camel_case(field.name)] = []
                    else:
                        payload[to_camel_case(field.name)] = None
                continue
            try:
                value = getattr(instance, field.name)
                payload[to_camel_case(field.name)] = self._to_json_value(value)
            except Exception:
                logger.debug(
                    "Failed to serialize nested field %s.%s.",
                    instance.__class__._meta.label,
                    field.name,
                    exc_info=True,
                )
                payload[to_camel_case(field.name)] = None
        return payload

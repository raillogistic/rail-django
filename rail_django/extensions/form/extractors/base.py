"""
FormConfigExtractor implementation.
"""

from __future__ import annotations

from typing import Any, Optional

from django.apps import apps
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
from ..utils.graphql_meta import get_graphql_meta


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

        instance = None
        if object_id:
            try:
                instance = model.objects.get(pk=object_id)
            except Exception:
                instance = None

        fields = self._extract_fields(
            model, user, instance=instance, graphql_meta=graphql_meta
        )
        relations = self._extract_relations(
            model, user, graphql_meta=graphql_meta
        )

        permissions = self._extract_permissions(
            model, user, fields=fields, relations=relations
        )

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
                "allowed": permissions.get("can_create", True),
                "permission": None,
                "denial_reason": None,
                "success_message": None,
                "requires_optimistic_lock": False,
                "optimistic_lock_field": None,
            },
            "update_mutation": {
                "name": f"update{model_name}",
                "operation": "UPDATE",
                "description": f"Update {model._meta.verbose_name}",
                "input_fields": [],
                "allowed": permissions.get("can_update", True),
                "permission": None,
                "denial_reason": None,
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
                "allowed": permissions.get("can_delete", True),
                "permission": None,
                "denial_reason": None,
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
    ) -> dict[str, Any]:
        try:
            model = apps.get_model(app_name, model_name)
        except LookupError:
            raise GraphQLError(f"Model '{app_name}.{model_name}' not found.")

        try:
            instance = model.objects.get(pk=object_id)
        except Exception:
            raise GraphQLError(
                f"Instance '{app_name}.{model_name}' with id {object_id} not found."
            )

        from graphene.utils.str_converters import to_camel_case

        nested_field_set: set[str] = set()
        for item in nested_fields or []:
            normalized = str(item or "").strip()
            if normalized:
                nested_field_set.add(normalized)

        def should_include_nested_relation(field_name: str) -> bool:
            if nested_field_set:
                return field_name in nested_field_set or (
                    to_camel_case(field_name) in nested_field_set
                )
            return include_nested

        data: dict[str, Any] = {}
        for field in model._meta.get_fields():
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
                                if include_this_relation_nested:
                                    data[field.name] = [
                                        self._serialize_related_instance(
                                            obj,
                                            depth=1,
                                            max_depth=max_nested_depth,
                                        )
                                        for obj in related_manager.all()
                                    ]
                                else:
                                    data[field.name] = [
                                        obj.pk for obj in related_manager.all()
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
                        data[field.name] = None
                continue

            try:
                value = getattr(instance, field.name)
                data[field.name] = self._to_json_value(value)
            except Exception:
                data[field.name] = None

        # Convert keys to camelCase for frontend consistency
        return {to_camel_case(k): v for k, v in data.items()}

    def _serialize_related_instance(
        self,
        instance: models.Model,
        *,
        depth: int,
        max_depth: int,
    ) -> dict[str, Any]:
        from graphene.utils.str_converters import to_camel_case

        payload: dict[str, Any] = {"id": getattr(instance, "pk", None)}
        if depth > max_depth:
            return payload

        for field in instance._meta.get_fields():
            if field.is_relation:
                continue
            if not hasattr(field, "name"):
                continue
            try:
                value = getattr(instance, field.name)
                payload[to_camel_case(field.name)] = self._to_json_value(value)
            except Exception:
                payload[to_camel_case(field.name)] = None
        return payload

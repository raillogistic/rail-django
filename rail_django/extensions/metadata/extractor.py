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
            "fields": self._extract_fields(model, user, instance=instance),
            "relationships": self._extract_relationships(model, user),
            "filters": self._extract_filters(model),
            "filter_config": self._extract_filter_config(model),
            "relation_filters": self._extract_relation_filters(model),
            "mutations": self._extract_mutations(model, user),
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
        for group in graphql_meta.field_groups:
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

    def _extract_mutations(self, model: Any, user: Any) -> list[dict]:
        """Extract available mutations for the model."""
        settings = MutationGeneratorSettings.from_schema(self.schema_name)
        results = []
        model_name = model.__name__

        # CRUD
        if settings.enable_create:
            results.append(
                {
                    "name": f"create{model_name}",
                    "operation": "create",
                    "description": f"Create {model._meta.verbose_name}",
                    "method_name": None,
                    "input_fields": [],
                    "allowed": True,
                    "required_permissions": [],
                    "mutation_type": "create",
                    "model_name": model_name,
                    "requires_authentication": True,
                }
            )
        if settings.enable_update:
            results.append(
                {
                    "name": f"update{model_name}",
                    "operation": "update",
                    "description": f"Update {model._meta.verbose_name}",
                    "method_name": None,
                    "input_fields": [],
                    "allowed": True,
                    "required_permissions": [],
                    "mutation_type": "update",
                    "model_name": model_name,
                    "requires_authentication": True,
                }
            )
        if settings.enable_delete:
            results.append(
                {
                    "name": f"delete{model_name}",
                    "operation": "delete",
                    "description": f"Delete {model._meta.verbose_name}",
                    "method_name": None,
                    "input_fields": [],
                    "allowed": True,
                    "required_permissions": [],
                    "mutation_type": "delete",
                    "model_name": model_name,
                    "requires_authentication": True,
                }
            )

        # Method mutations
        introspector = ModelIntrospector.for_model(model)
        from graphene.utils.str_converters import to_camel_case
        for name, info in introspector.get_model_methods().items():
            if info.is_mutation:
                results.append(
                    {
                        "name": to_camel_case(name),
                        "operation": "custom",
                        "description": str(info.method.__doc__ or "").strip(),
                        "method_name": name,
                        "input_fields": [],  # Argument extraction omitted for brevity
                        "allowed": True,
                        "required_permissions": [],
                        "mutation_type": "custom",
                        "model_name": model_name,
                        "requires_authentication": True,
                    }
                )

        return results

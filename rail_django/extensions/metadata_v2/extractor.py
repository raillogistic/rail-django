"""
ModelSchemaExtractor implementation.
"""

import logging
from typing import Any, Optional

from django.apps import apps
from graphql import GraphQLError

from ...utils.graphql_meta import get_model_graphql_meta
from .utils import _cache_version, get_cached_schema, set_cached_schema, get_model_version

from .field_extractor import FieldExtractorMixin
from .filter_extractor import FilterExtractorMixin
from .permissions_extractor import PermissionExtractorMixin

logger = logging.getLogger(__name__)


class ModelSchemaExtractor(FieldExtractorMixin, FilterExtractorMixin, PermissionExtractorMixin):
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

        result = {
            "app": app_name,
            "model": model_name,
            "verbose_name": str(meta.verbose_name),
            "verbose_name_plural": str(meta.verbose_name_plural),
            "primary_key": meta.pk.name if meta.pk else "id",
            "ordering": list(meta.ordering) if meta.ordering else [],
            "unique_together": [list(ut) for ut in meta.unique_together]
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

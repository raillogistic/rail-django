"""
GraphQL Queries for Metadata V2.
"""

import logging
from typing import Optional

import graphene
from django.apps import apps
from graphql import GraphQLError

from .extractor import ModelSchemaExtractor
from .types import (
    FilterConfigType,
    FilterSchemaType,
    ModelInfoType,
    ModelSchemaType,
)

logger = logging.getLogger(__name__)


class ModelSchemaQuery(graphene.ObjectType):
    """
    GraphQL queries for model schema (Metadata V2).

    Provides comprehensive model introspection for frontend UI generation.
    """

    modelSchema = graphene.Field(
        ModelSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        objectId=graphene.ID(
            description="Instance ID for instance-specific permissions"
        ),
        description="Get complete schema information for a model.",
    )

    availableModels = graphene.List(
        ModelInfoType,
        app=graphene.String(description="Filter by app"),
        description="List all available models.",
    )

    appSchemas = graphene.List(
        ModelSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        description="Get schemas for all models in an app.",
    )

    filterSchema = graphene.List(
        FilterSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        description="Get all available filters for a model",
    )

    fieldFilterSchema = graphene.Field(
        FilterSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        field=graphene.String(required=True, description="Filter field name"),
        description="Get filter metadata for a specific field",
    )

    metadataDeployVersion = graphene.String(
        key=graphene.String(description="Deployment version key"),
        description="Deployment-level metadata version for cache invalidation.",
    )

    def resolve_modelSchema(
        self,
        info,
        app: str,
        model: str,
        objectId: Optional[str] = None,
    ) -> dict:
        """
        Resolve complete model schema.

        Args:
            info: GraphQL resolve info.
            app: Django app label.
            model: Model name.
            objectId: Optional instance ID.

        Returns:
            Complete model schema.
        """
        user = getattr(info.context, "user", None)
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        return extractor.extract(app, model, user=user, object_id=objectId)

    def resolve_filterSchema(
        self, info, app: str, model: str
    ) -> list[dict]:
        """Resolve available filters for a model."""
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        try:
            model_cls = apps.get_model(app, model)
            return extractor.extract_model_filters(model_cls)
        except LookupError:
            return []

    def resolve_fieldFilterSchema(
        self, info, app: str, model: str, field: str
    ) -> Optional[dict]:
        """Resolve metadata for a specific filter field."""
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        try:
            model_cls = apps.get_model(app, model)
            return extractor.extract_filter_field(model_cls, field)
        except LookupError:
            return None

    def resolve_metadataDeployVersion(self, info, key: Optional[str] = None) -> str:
        from .deploy_version import get_deploy_version

        return get_deploy_version(key)

    def resolve_availableModels(self, info, app: Optional[str] = None) -> list[dict]:
        """
        Resolve list of available models.

        Args:
            info: GraphQL resolve info.
            app: Optional app filter.

        Returns:
            List of model info dicts.
        """
        results = []
        for model in apps.get_models():
            if app and model._meta.app_label != app:
                continue
            if model._meta.app_label in ("admin", "auth", "contenttypes", "sessions"):
                continue
            results.append(
                {
                    "app": model._meta.app_label,
                    "model": model.__name__,
                    "verbose_name": str(model._meta.verbose_name),
                    "verbose_name_plural": str(model._meta.verbose_name_plural),
                }
            )
        return results

    def resolve_appSchemas(self, info, app: str) -> list[dict]:
        """
        Resolve schemas for all models in an app.

        Args:
            info: GraphQL resolve info.
            app: Django app label.

        Returns:
            List of model schemas.
        """
        user = getattr(info.context, "user", None)
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        schemas = []
        for model in apps.get_app_config(app).get_models():
            try:
                schemas.append(extractor.extract(app, model.__name__, user=user))
            except Exception as e:
                logger.warning(
                    f"Error extracting schema for {app}.{model.__name__}: {e}"
                )
        return schemas

"""GraphQL query types for model metadata.

This module provides the GraphQL query types for exposing Django model
metadata including available models, model metadata, form metadata,
table metadata, and app-level model listings.
"""

import logging
from typing import Optional

import graphene
from django.apps import apps
from graphql import GraphQLError

from .cache import _get_requested_field_names, _require_metadata_access
from .types import (
    ModelFormMetadataType,
    ModelMetadataType,
    ModelTableType,
)

logger = logging.getLogger(__name__)


class AvailableModelType(graphene.ObjectType):
    """GraphQL type representing an available model for metadata queries."""

    app_label = graphene.String(required=True, description="App label")
    model_name = graphene.String(required=True, description="Model name")
    verbose_name = graphene.String(required=True, description="Verbose name")


def _get_metadata_extractor(max_depth: int = 1):
    """Lazily import ModelMetadataExtractor to avoid circular imports."""
    from ..metadata import ModelMetadataExtractor
    return ModelMetadataExtractor(max_depth=max_depth)


def _get_form_metadata_extractor(max_depth: int = 1):
    """Lazily import ModelFormMetadataExtractor to avoid circular imports."""
    from ..metadata import ModelFormMetadataExtractor
    return ModelFormMetadataExtractor(max_depth=max_depth)


def _get_table_extractor(schema_name: Optional[str] = None):
    """Lazily import ModelTableExtractor to avoid circular imports."""
    from ..metadata import ModelTableExtractor
    return ModelTableExtractor(schema_name=schema_name)


def resolve_filter_schema(root, info, model, depth=1):
    """
    Resolver for filterSchema query.
    """
    from django.apps import apps
    from .types import FilterSchemaType, FilterFieldType, FilterOptionType, FilterPresetType
    from ...core.meta import get_model_graphql_meta
    from ...generators.filters.analysis import FilterMetadataGenerator
    from ...core.settings import FilteringSettings
    
    target_model = None
    for app_config in apps.get_app_configs():
        try:
            m = app_config.get_model(model)
            target_model = m
            break
        except LookupError:
            continue
            
    if not target_model:
        return None
        
    schema_name = getattr(info.context, "schema_name", "default")
    generator = FilterMetadataGenerator(schema_name=schema_name)
    grouped_filters = generator.get_grouped_filters(target_model)
    
    fields = []
    for gf in grouped_filters:
        ops = [
            FilterOptionType(
                name=op.name,
                lookup_expr=op.lookup_expr,
                help_text=op.description or op.name,
                filter_type=op.filter_type
            )
            for op in gf.operations
        ]
        
        fields.append(FilterFieldType(
            field_name=gf.field_name,
            is_nested=gf.field_type in ["ForeignKey", "ManyToManyField", "OneToOneField"],
            is_custom=False,
            field_label=gf.field_name.replace("_", " ").title(),
            options=ops
        ))
        
    presets = []
    meta = get_model_graphql_meta(target_model)
    raw_presets = {}
    if meta:
        if meta.filter_presets:
            raw_presets.update(meta.filter_presets)
        if hasattr(meta, "filtering") and hasattr(meta.filtering, "presets") and meta.filtering.presets:
            raw_presets.update(meta.filtering.presets)
        
    for name, filter_dict in raw_presets.items():
        presets.append(FilterPresetType(
            name=name,
            description=f"Preset {name}",
            filter_json=filter_dict
        ))
            
    try:
        f_settings = FilteringSettings.from_schema(schema_name)
        supports_fts = getattr(f_settings, "enable_full_text_search", False)
        supports_agg = getattr(f_settings, "enable_aggregation", True)
    except Exception:
        supports_fts = False
        supports_agg = False

    return FilterSchemaType(
        model=model,
        fields=fields,
        presets=presets,
        supports_fts=supports_fts,
        supports_aggregation=supports_agg
    )


class ModelMetadataQuery(graphene.ObjectType):
    """GraphQL queries for model metadata.

    Provides comprehensive metadata about Django models for frontend consumption.
    """

    available_models = graphene.List(
        AvailableModelType,
        description="List all available models in the project.",
    )

    model_metadata = graphene.Field(
        ModelMetadataType,
        app_name=graphene.String(required=True, description="Django app name"),
        model_name=graphene.String(required=True, description="Model class name"),
        nested_fields=graphene.Boolean(
            default_value=True, description="Include relationship metadata"
        ),
        permissions_included=graphene.Boolean(
            default_value=True, description="Include permission information"
        ),
        max_depth=graphene.Int(
            default_value=0,
            description="Maximum nesting depth for filters (default: 0)",
        ),
        description="Get comprehensive metadata for a Django model",
    )

    model_form_metadata = graphene.Field(
        ModelFormMetadataType,
        app_name=graphene.String(required=True, description="Django app name"),
        model_name=graphene.String(required=True, description="Model class name"),
        nested_fields=graphene.List(
            graphene.String,
            default_value=[],
            description="List of field names to include nested metadata for (depth 1)",
        ),
        exclude=graphene.List(
            graphene.String,
            default_value=[],
            description="List of regular field names to exclude from form metadata",
        ),
        only=graphene.List(
            graphene.String,
            default_value=[],
            description="List of regular field names to exclusively include in form metadata",
        ),
        exclude_relationships=graphene.List(
            graphene.String,
            default_value=[],
            description="Relationship field names to exclude from form metadata",
        ),
        only_relationships=graphene.List(
            graphene.String,
            default_value=[],
            description="Relationship field names to exclusively include in form metadata",
        ),
        description="Get comprehensive form metadata for a Django model",
    )

    model_table = graphene.Field(
        ModelTableType,
        app_name=graphene.String(required=True, description="Django app name"),
        model_name=graphene.String(required=True, description="Model class name"),
        counts=graphene.Boolean(
            default_value=False, description="Show reverse relationship count"
        ),
        exclude=graphene.List(
            graphene.String,
            default_value=[],
            description="List of field names to exclude from filters",
        ),
        only=graphene.List(
            graphene.String,
            default_value=[],
            description="List of field names to exclusively include in filters",
        ),
        include_nested=graphene.Boolean(
            default_value=True,
            description="Whether to include nested filter groups",
        ),
        only_lookup=graphene.List(
            graphene.String,
            default_value=[],
            description="Restrict filter options to these lookup expressions",
        ),
        exclude_lookup=graphene.List(
            graphene.String,
            default_value=[],
            description="Exclude these lookup expressions from filter options",
        ),
        description="Get comprehensive table metadata for a Django model",
    )

    app_models = graphene.List(
        ModelMetadataType,
        app_name=graphene.String(required=True, description="Django app name"),
        nested_fields=graphene.Boolean(
            default_value=True,
            description="Include nested relationship metadata for each model",
        ),
        permissions_included=graphene.Boolean(
            default_value=True,
            description="Include permission metadata when the user is authenticated",
        ),
        max_depth=graphene.Int(
            default_value=1, description="Maximum relationship depth to explore"
        ),
        description="Return the metadata for every model declared in the specified Django app.",
    )

    def resolve_available_models(self, info) -> list[AvailableModelType]:
        """Resolve list of all available models.

        Returns models from all installed apps, excluding Django's
        built-in admin, auth, contenttypes, and sessions apps.
        Also filters out Historical models from django-simple-history.

        Args:
            info: GraphQL resolve info context.

        Returns:
            list[AvailableModelType]: List of available model descriptors.

        Raises:
            GraphQLError: If metadata access is not permitted.
        """
        _require_metadata_access(info)
        available_models = []
        excluded_apps = ["admin", "auth", "contenttypes", "sessions"]

        for app_config in apps.get_app_configs():
            if app_config.label in excluded_apps:
                continue

            for model in app_config.get_models():
                # Filter out Historical models (django-simple-history)
                if model.__name__.startswith("Historical"):
                    continue

                available_models.append(
                    AvailableModelType(
                        app_label=app_config.label,
                        model_name=model.__name__,
                        verbose_name=str(model._meta.verbose_name),
                    )
                )
        return available_models

    def resolve_model_metadata(
        self,
        info,
        app_name: str,
        model_name: str,
        nested_fields: bool = True,
        permissions_included: bool = True,
        max_depth: int = 1,
    ) -> Optional[ModelMetadataType]:
        """Resolve model metadata with permission checking and settings validation.

        Extracts comprehensive metadata about a Django model including
        fields, relationships, permissions, filters, and mutations.

        Args:
            info: GraphQL resolve info context.
            app_name: Django app name containing the model.
            model_name: Model class name.
            nested_fields: Include nested relationship metadata.
            permissions_included: Include permission-based field filtering.
            max_depth: Maximum nesting depth for filters.

        Returns:
            ModelMetadataType: Comprehensive model metadata or None if not accessible.

        Raises:
            GraphQLError: If metadata access fails or model is not found.
        """
        user = _require_metadata_access(info)
        selection_names = _get_requested_field_names(info)
        selection_defined = bool(selection_names)
        include_filters = (
            True if not selection_defined else "filters" in selection_names
        )
        include_mutations = (
            True if not selection_defined else "mutations" in selection_names
        )

        extractor = _get_metadata_extractor(max_depth=max_depth)
        try:
            metadata = extractor.extract_model_metadata(
                app_name=app_name,
                model_name=model_name,
                user=user,
                nested_fields=nested_fields,
                permissions_included=permissions_included,
                include_filters=include_filters,
                include_mutations=include_mutations,
            )
        except Exception as exc:
            logger.warning(
                "Failed to extract metadata for %s.%s: %s",
                app_name,
                model_name,
                exc,
            )
            raise GraphQLError("Unable to load model metadata.")

        if metadata is None:
            raise GraphQLError("Model metadata not available.")

        return metadata

    def resolve_model_table(
        self,
        info,
        app_name: str,
        model_name: str,
        counts: bool = False,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        include_nested: bool = True,
        only_lookup: Optional[list[str]] = None,
        exclude_lookup: Optional[list[str]] = None,
    ) -> Optional[ModelTableType]:
        """Resolve comprehensive table metadata for a Django model.

        Extracts metadata suitable for table/list view rendering including
        columns, filters, and available mutations.

        Args:
            info: GraphQL resolve info context.
            app_name: Django app name containing the model.
            model_name: Model class name.
            counts: Include reverse relationship counts.
            exclude: Field names to exclude from filters.
            only: Field names to exclusively include in filters.
            include_nested: Include nested filter groups.
            only_lookup: Restrict filter options to these lookups.
            exclude_lookup: Exclude these lookup expressions.

        Returns:
            ModelTableType: Table metadata or None if not accessible.

        Raises:
            GraphQLError: If metadata access fails or model is not found.
        """
        user = _require_metadata_access(info)
        extractor = _get_table_extractor()
        selection_names = _get_requested_field_names(info)
        selection_defined = bool(selection_names)
        include_filters = (
            True if not selection_defined else "filters" in selection_names
        )
        include_mutations = (
            True if not selection_defined else "mutations" in selection_names
        )
        include_pdf_templates = (
            True if not selection_defined else "pdfTemplates" in selection_names
        )
        try:
            metadata = extractor.extract_model_table_metadata(
                app_name=app_name,
                model_name=model_name,
                counts=counts,
                exclude=exclude or [],
                only=only or [],
                include_nested=include_nested,
                only_lookup=only_lookup or [],
                exclude_lookup=exclude_lookup or [],
                include_filters=include_filters,
                include_mutations=include_mutations,
                include_pdf_templates=include_pdf_templates,
                user=user,
            )
        except Exception as exc:
            logger.warning(
                "Failed to extract table metadata for %s.%s: %s",
                app_name,
                model_name,
                exc,
            )
            raise GraphQLError("Unable to load table metadata.")

        if metadata is None:
            raise GraphQLError("Table metadata not available.")

        return metadata

    def resolve_model_form_metadata(
        self,
        info,
        app_name: str,
        model_name: str,
        nested_fields: list[str] = None,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        exclude_relationships: Optional[list[str]] = None,
        only_relationships: Optional[list[str]] = None,
    ) -> Optional[ModelFormMetadataType]:
        """Resolve model form metadata for frontend form construction.

        Extracts metadata suitable for dynamic form generation including
        field types, validation rules, and choices.

        Args:
            info: GraphQL resolve info context.
            app_name: Django app name containing the model.
            model_name: Model class name.
            nested_fields: Field names to include nested metadata for.
            exclude: Regular field names to exclude.
            only: Regular field names to exclusively include.
            exclude_relationships: Relationship field names to exclude.
            only_relationships: Relationship field names to include.

        Returns:
            ModelFormMetadataType: Form metadata or None if not accessible.

        Raises:
            GraphQLError: If metadata access fails or model is not found.
        """
        user = _require_metadata_access(info)

        extractor = _get_form_metadata_extractor(max_depth=1)
        try:
            metadata = extractor.extract_model_form_metadata(
                app_name=app_name,
                model_name=model_name,
                user=user,
                nested_fields=nested_fields or [],
                exclude=exclude or [],
                only=only or [],
                exclude_relationships=exclude_relationships or [],
                only_relationships=only_relationships or [],
            )
        except Exception as exc:
            logger.warning(
                "Failed to extract form metadata for %s.%s: %s",
                app_name,
                model_name,
                exc,
            )
            raise GraphQLError("Unable to load form metadata.")

        if metadata is None:
            raise GraphQLError("Form metadata not available.")

        return metadata

    def resolve_app_models(
        self,
        info,
        app_name: str,
        nested_fields: bool = True,
        permissions_included: bool = True,
        max_depth: int = 1,
    ) -> list[ModelMetadataType]:
        """Resolve metadata for every model inside the provided Django app.

        Iterates through all models in the specified app and extracts
        metadata for each one.

        Args:
            info: GraphQL resolve info context.
            app_name: Django app label.
            nested_fields: Include relationship metadata.
            permissions_included: Include permission information when authenticated.
            max_depth: Maximum relationship depth for related metadata.

        Returns:
            list[ModelMetadataType]: Metadata for all models in the app.

        Raises:
            GraphQLError: If the app is not found or access is denied.
        """
        user = _require_metadata_access(info)
        selection_names = _get_requested_field_names(info)
        selection_defined = bool(selection_names)
        include_filters = (
            True if not selection_defined else "filters" in selection_names
        )
        include_mutations = (
            True if not selection_defined else "mutations" in selection_names
        )

        try:
            app_config = apps.get_app_config(app_name)
        except LookupError:
            logger.warning("app_models requested for unknown app '%s'", app_name)
            raise GraphQLError("Unknown app requested.")

        extractor = _get_metadata_extractor(max_depth=max_depth)
        models_metadata: list[ModelMetadataType] = []

        for model in app_config.get_models():
            # Filter out Historical models (django-simple-history)
            if model.__name__.startswith("Historical"):
                continue
            try:
                metadata = extractor.extract_model_metadata(
                    app_name=app_name,
                    model_name=model.__name__,
                    user=user,
                    nested_fields=nested_fields,
                    permissions_included=permissions_included,
                    include_filters=include_filters,
                    include_mutations=include_mutations,
                )
                if metadata is not None:
                    models_metadata.append(metadata)
            except Exception as exc:
                logger.warning(
                    "Failed to load metadata for %s.%s: %s",
                    app_name,
                    model.__name__,
                    exc,
                )

        return models_metadata


__all__ = [
    "AvailableModelType",
    "ModelMetadataQuery",
]

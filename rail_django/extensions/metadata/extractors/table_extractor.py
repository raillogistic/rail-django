"""Table metadata extractor.

This module provides the ModelTableExtractor class which extracts
comprehensive table metadata from Django models for data grid displays,
including fields, filters, mutations, and PDF template actions.
"""

import logging
import time
from typing import Any, Optional

from django.apps import apps
from django.db import models

from ..types import (
    ModelTableMetadata,
    MutationMetadata,
    TemplateActionMetadata,
)
from .base import BaseMetadataExtractor, _build_model_permission_matrix
from .model_extractor import ModelMetadataExtractor
from .table_fields import TableFieldExtractionMixin, TableFilterExtractionMixin

logger = logging.getLogger(__name__)


# Try to import template registry
try:
    from ...templating import (
        template_registry,
        _url_prefix as _templating_url_prefix,
        evaluate_template_access,
    )
except Exception:
    template_registry = None
    evaluate_template_access = None

    def _templating_url_prefix() -> str:
        return "templates"


def _get_metadata_version_value(app_name: str, model_name: str) -> str:
    """Get the metadata version value for a model."""
    try:
        from ...metadata import _get_metadata_version_value as get_version
        return get_version(app_name, model_name)
    except ImportError:
        return str(int(time.time() * 1000))


class ModelTableExtractor(
    TableFieldExtractionMixin, TableFilterExtractionMixin, BaseMetadataExtractor
):
    """
    Extractor for comprehensive table metadata.

    Provides all necessary information for data grid displays including
    fields, filters, mutations, and PDF template actions.
    """

    def __init__(self, schema_name: str = "default"):
        """
        Initialize the table metadata extractor.

        Args:
            schema_name: Name of the schema configuration to use.
        """
        super().__init__(schema_name=schema_name, max_depth=1)
        self.metadata_extractor = ModelMetadataExtractor(schema_name=schema_name)

    def _get_model(self, app_name: str, model_name: str):
        """Get a Django model by app and model name."""
        try:
            return apps.get_model(app_name, model_name)
        except Exception as e:
            logger.error(
                "Model '%s' not found in app '%s': %s", model_name, app_name, e
            )
            return None

    def _collect_pdf_templates(
        self, model: type[models.Model], user=None
    ) -> list[TemplateActionMetadata]:
        """
        Gather template metadata registered via @model_pdf_template.

        Args:
            model: Django model class.
            user: Optional user for permission evaluation.

        Returns:
            List of TemplateActionMetadata for available templates.
        """
        if not template_registry:
            return []

        try:
            registry_entries = template_registry.all().items()
        except Exception:
            return []

        prefix = _templating_url_prefix().strip("/")
        api_prefix = f"/api/{prefix}".rstrip("/")
        templates: list[TemplateActionMetadata] = []

        for url_path, definition in registry_entries:
            if definition.model is not model:
                continue

            endpoint = f"{api_prefix}/{url_path.strip('/')}"
            decision = (
                evaluate_template_access(definition, user=user)
                if evaluate_template_access
                else None
            )
            allowed = decision.allowed if decision else True
            denial_reason = (
                decision.reason if decision and not decision.allowed else None
            )
            templates.append(
                TemplateActionMetadata(
                    key=f"{model._meta.app_label}.{model._meta.model_name}.{definition.method_name}",
                    method_name=definition.method_name,
                    title=definition.title,
                    endpoint=endpoint,
                    url_path=url_path,
                    guard=definition.guard or "retrieve",
                    require_authentication=definition.require_authentication,
                    roles=list(definition.roles or []),
                    permissions=list(definition.permissions or []),
                    allowed=allowed,
                    denial_reason=denial_reason,
                    allow_client_data=definition.allow_client_data,
                    client_data_fields=list(definition.client_data_fields or []),
                    client_data_schema=[
                        {
                            "name": entry.get("name"),
                            "type": entry.get("type", "string"),
                        }
                        for entry in (definition.client_data_schema or [])
                        if entry.get("name")
                    ],
                )
            )

        templates.sort(key=lambda tpl: tpl.title.lower())
        return templates

    def extract_model_table_metadata(
        self,
        app_name: str,
        model_name: str,
        custom_fields: Optional[list[str]] = None,
        counts: bool = False,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        include_nested: bool = True,
        only_lookup: Optional[list[str]] = None,
        exclude_lookup: Optional[list[str]] = None,
        include_filters: bool = True,
        include_mutations: bool = True,
        include_pdf_templates: bool = True,
        user=None,
    ) -> Optional[ModelTableMetadata]:
        """
        Extract comprehensive table metadata for a Django model.

        Args:
            app_name: Django app name.
            model_name: Model class name.
            custom_fields: Custom field names (deprecated).
            counts: Include reverse relationship count fields.
            exclude: Field names to exclude from filters.
            only: Field names to exclusively include in filters.
            include_nested: Whether to include nested filter groups.
            only_lookup: Lookup expressions to include.
            exclude_lookup: Lookup expressions to exclude.
            include_filters: Whether to include filter metadata.
            include_mutations: Whether to include mutation metadata.
            include_pdf_templates: Whether to include PDF template metadata.
            user: Optional user for permission checking.

        Returns:
            ModelTableMetadata with comprehensive table information.
        """
        from ....generators.introspector import ModelIntrospector

        model = self._get_model(app_name, model_name)
        if not model:
            return None

        meta = model._meta
        introspector = ModelIntrospector.for_model(model, self.schema_name)

        # Extract mutations
        mutations: list[MutationMetadata] = []
        if include_mutations:
            try:
                mutations = self.metadata_extractor.extract_mutations_metadata(
                    model, user=user
                )
            except Exception as exc:
                logger.warning(
                    "Unable to extract mutations metadata for %s.%s: %s",
                    app_name,
                    model_name,
                    exc,
                )
                mutations = []

        # Detect polymorphic models
        is_polymorphic_model = self._detect_polymorphic_model(model, meta)

        # Table-level metadata
        app_label = meta.app_label
        model_label = model.__name__
        verbose_name = str(meta.verbose_name)
        verbose_name_plural = str(meta.verbose_name_plural)
        table_name = str(meta.db_table)
        primary_key = meta.pk.name if meta.pk else "id"
        ordering = list(meta.ordering) if getattr(meta, "ordering", None) else []

        if not ordering:
            if getattr(meta, "get_latest_by", None):
                ordering = [f"-{meta.get_latest_by}"]
            else:
                ordering = [primary_key]

        default_ordering = ordering.copy()
        get_latest_by = getattr(meta, "get_latest_by", None)
        managers = [m.name for m in getattr(meta, "managers", [])] or [
            m.name for m in model._meta.managers
        ]
        managed = bool(getattr(meta, "managed", True))

        # Build table fields
        table_fields, generic_fields = self._extract_table_fields(
            model, meta, introspector, is_polymorphic_model, counts, user
        )

        # Extract filters
        filters: list[dict[str, Any]] = []
        if include_filters:
            filters = self._extract_table_filters(
                model,
                introspector,
                exclude=exclude,
                only=only,
                include_nested=include_nested,
                only_lookup=only_lookup,
                exclude_lookup=exclude_lookup,
            )

        # Collect PDF templates
        pdf_templates = (
            self._collect_pdf_templates(model, user=user)
            if include_pdf_templates
            else []
        )

        return ModelTableMetadata(
            metadata_version=_get_metadata_version_value(app_name, model_name),
            app=app_label,
            model=model_label,
            verbose_name=verbose_name,
            verbose_name_plural=verbose_name_plural,
            table_name=table_name,
            primary_key=primary_key,
            ordering=ordering,
            default_ordering=default_ordering,
            get_latest_by=get_latest_by,
            managers=managers,
            managed=managed,
            fields=table_fields,
            generics=generic_fields,
            filters=filters,
            permissions=_build_model_permission_matrix(model, user),
            mutations=mutations,
            pdf_templates=pdf_templates,
        )

    def _detect_polymorphic_model(self, model, meta) -> bool:
        """Detect if model uses polymorphic or multi-table inheritance."""
        try:
            from ....generators.inheritance import inheritance_handler
            inheritance_info = inheritance_handler.analyze_model_inheritance(model)
        except Exception:
            inheritance_info = {}

        is_polymorphic = False

        try:
            for _f in meta.get_fields():
                if getattr(_f, "name", None) == "polymorphic_ctype":
                    is_polymorphic = True
                    break
        except Exception:
            pass

        if getattr(meta, "parents", None):
            try:
                if len(meta.parents) > 0:
                    is_polymorphic = True
            except Exception:
                is_polymorphic = True

        if inheritance_info and (
            inheritance_info.get("child_models")
            or inheritance_info.get("concrete_parents")
        ):
            is_polymorphic = True

        return is_polymorphic

    def _extract_table_fields(
        self, model, meta, introspector, is_polymorphic_model: bool, counts: bool, user
    ) -> tuple[list, list]:
        """Extract table fields and generic fields."""
        from ..types import TableFieldMetadata

        table_fields = []
        generic_fields = []

        if is_polymorphic_model:
            try:
                all_fields = meta.get_fields(include_parents=True)
            except Exception:
                all_fields = meta.get_fields()
        else:
            all_fields = meta.get_fields()

        for f in all_fields:
            if getattr(f, "auto_created", False) and getattr(f, "is_relation", False):
                continue

            if (
                f.name == "polymorphic_ctype"
                or f.name == "id"
                or f.name.endswith("_ptr")
            ):
                continue

            if is_polymorphic_model and isinstance(f, models.OneToOneField):
                continue

            if getattr(f, "concrete", False) or (
                getattr(f, "is_relation", False)
                and not getattr(f, "auto_created", False)
            ):
                try:
                    try:
                        from django.contrib.contenttypes.fields import GenericRelation
                        if isinstance(f, GenericRelation):
                            meta_val = self._build_table_field_from_django_field(
                                f, user=user
                            )
                            if meta_val:
                                generic_fields.append(meta_val)
                            continue
                    except Exception:
                        pass
                    field_meta = self._build_table_field_from_django_field(f, user=user)
                    if field_meta:
                        table_fields.append(field_meta)
                except Exception as e:
                    logger.warning(f"Unable to build field metadata for {f.name}: {e}")

        # Add properties from introspector
        try:
            properties_dict = getattr(introspector, "properties", {}) or {}
            existing_names = {getattr(tf, "name", None) for tf in table_fields}

            for prop_name, prop_info in properties_dict.items():
                if (
                    prop_name == "pk"
                    or prop_name == "polymorphic_ctype"
                    or str(prop_name).endswith("_ptr")
                ):
                    continue

                if prop_name in existing_names:
                    continue

                verbose = getattr(prop_info, "verbose_name", prop_name)
                return_type = getattr(prop_info, "return_type", None)
                table_fields.append(
                    self._build_table_field_for_property(
                        prop_name, return_type, verbose
                    )
                )
        except Exception as e:
            logger.debug(f"Properties extraction unavailable for {model.__name__}: {e}")

        # Add reverse relationship counts
        if counts:
            table_fields.extend(
                self._build_table_field_for_reverse_count(introspector, model)
            )

        return table_fields, generic_fields


__all__ = ["ModelTableExtractor"]

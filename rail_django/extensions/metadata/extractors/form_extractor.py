"""Form metadata extractor.

This module provides the ModelFormMetadataExtractor class which extracts
comprehensive form metadata from Django models for frontend form generation.
"""

import logging
from typing import Any, Optional

from django.apps import apps
from django.db import models

from ..types import ModelFormMetadata
from .base import BaseMetadataExtractor, _build_model_permission_matrix
from .form_fields import FormFieldExtractionMixin

logger = logging.getLogger(__name__)


def _get_metadata_version_value(app_name: str, model_name: str) -> str:
    """Get the metadata version value for a model."""
    try:
        from ...metadata import _get_metadata_version_value as get_version
        return get_version(app_name, model_name)
    except ImportError:
        import time
        return str(int(time.time() * 1000))


class ModelFormMetadataExtractor(FormFieldExtractionMixin, BaseMetadataExtractor):
    """
    Extractor for Django model form metadata.

    Provides all necessary information to construct forms on the frontend,
    including field types, validation rules, relationship handling, and
    permission-based visibility.
    """

    def extract_model_form_metadata(
        self,
        app_name: str,
        model_name: str,
        user,
        nested_fields: list[str] = None,
        exclude: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        exclude_relationships: Optional[list[str]] = None,
        only_relationships: Optional[list[str]] = None,
        current_depth: int = 0,
        visited_models: set = None,
    ) -> Optional[ModelFormMetadata]:
        """
        Extract comprehensive form metadata for a Django model.

        Args:
            app_name: Django app name.
            model_name: Model class name.
            user: User instance for permission checking.
            nested_fields: Field names to include nested metadata for.
            exclude: Regular form field names to exclude.
            only: Regular form field names to exclusively include.
            exclude_relationships: Relationship field names to exclude.
            only_relationships: Relationship field names to exclusively include.
            current_depth: Current nesting depth for recursive extraction.
            visited_models: Set of already visited models.

        Returns:
            ModelFormMetadata with form-specific information.
        """
        if visited_models is None:
            visited_models = set()

        model_key = f"{app_name}.{model_name}"

        # Check for circular references
        if model_key in visited_models:
            logger.warning(
                f"Circular reference detected for model {model_key}, skipping"
            )
            return None

        visited_models.add(model_key)

        try:
            model = apps.get_model(app_name, model_name)
        except (LookupError, ValueError) as e:
            logger.error(f"Model {app_name}.{model_name} not found: {e}")
            visited_models.discard(model_key)
            return None

        if not model or not hasattr(model, "_meta"):
            visited_models.discard(model_key)
            return None

        meta = model._meta
        nested_fields = nested_fields or []

        # Normalize selection inputs
        exclude = exclude or []
        only = only or []
        exclude_relationships = exclude_relationships or []
        only_relationships = only_relationships or []

        # Detect polymorphic/multi-table inheritance
        is_polymorphic_model = self._detect_polymorphic_model(model, meta)

        # Always exclude these known fields
        excluded_names = {"report_rows", "stock_policies", "stock_snapshots"}

        # Extract form fields and relationships
        form_fields = []
        form_relationships = []
        declared_forward_order: list[str] = []
        declared_reverse_order: list[str] = []

        for field in meta.get_fields():
            if field.name in excluded_names:
                continue
            if field.name == "polymorphic_ctype":
                continue
            if field.name.endswith("_ptr"):
                continue

            if hasattr(field, "related_model") and field.related_model:
                if is_polymorphic_model and getattr(field, "one_to_one", False):
                    if getattr(field, "auto_created", False):
                        continue

                relationship_metadata = self._extract_form_relationship_metadata(
                    field, user, current_depth, visited_models
                )
                if relationship_metadata:
                    form_relationships.append(relationship_metadata)
                    if getattr(relationship_metadata, "is_reverse", False):
                        declared_reverse_order.append(field.name)
                    else:
                        declared_forward_order.append(field.name)
            else:
                if not field.name.startswith("_") and field.concrete:
                    if is_polymorphic_model and isinstance(field, models.OneToOneField):
                        if getattr(field, "parent_link", False):
                            continue
                    if field.name.endswith("_ptr"):
                        continue
                    field_metadata = self._extract_form_field_metadata(field, user)
                    if field_metadata:
                        form_fields.append(field_metadata)
                        declared_forward_order.append(field.name)

        # Apply selection filters
        if only:
            form_fields = [f for f in form_fields if f.name in set(only)]
        if exclude:
            form_fields = [f for f in form_fields if f.name not in set(exclude)]

        if only_relationships:
            form_relationships = [
                r for r in form_relationships if r.name in set(only_relationships)
            ]
        if exclude_relationships:
            form_relationships = [
                r for r in form_relationships if r.name not in set(exclude_relationships)
            ]

        # Final safeguard
        if excluded_names:
            form_fields = [f for f in form_fields if f.name not in excluded_names]
            form_relationships = [
                r for r in form_relationships if r.name not in excluded_names
            ]

        # Build field order
        final_field_names = {f.name for f in form_fields}
        final_relationship_names = {r.name for r in form_relationships}
        field_order_forward = [
            name for name in declared_forward_order
            if (name in final_field_names or name in final_relationship_names)
        ]
        field_order_reverse = [
            name for name in declared_reverse_order
            if (name in final_field_names or name in final_relationship_names)
        ]
        field_order = field_order_forward + field_order_reverse

        # Ensure reverse relationships appear at the end
        reverse_names = {
            r.name for r in form_relationships if getattr(r, "is_reverse", False)
        }
        if reverse_names:
            non_reverse_order = [
                name for name in field_order if name not in reverse_names
            ]
            reverse_order = [name for name in field_order if name in reverse_names]
            field_order = non_reverse_order + reverse_order

        # Get excluded and readonly fields
        exclude_fields = []
        readonly_fields = []

        for field in meta.get_fields():
            if (
                field.auto_created
                or (hasattr(field, "auto_now") and field.auto_now)
                or (hasattr(field, "auto_now_add") and field.auto_now_add)
            ):
                exclude_fields.append(field.name)

            if getattr(field, "primary_key", None) or not field.editable:
                readonly_fields.append(field.name)

        # Required permissions
        required_permissions = [
            f"{app_name}.add_{model_name.lower()}",
            f"{app_name}.change_{model_name.lower()}",
        ]

        # Extract nested metadata
        nested_metadata = self._extract_nested_metadata(
            model, meta, user, nested_fields, current_depth, visited_models
        )

        # If a relationship is in nested, exclude it from top-level
        if nested_metadata:
            nested_names = {n.name for n in nested_metadata if getattr(n, "name", None)}
            if nested_names:
                form_relationships = [
                    r for r in form_relationships if r.name not in nested_names
                ]

        visited_models.discard(model_key)

        form_title = f"Form for {meta.verbose_name}"
        form_description = f"Create or edit {meta.verbose_name.lower()}"

        return ModelFormMetadata(
            metadata_version=_get_metadata_version_value(app_name, model_name),
            app_name=app_name,
            model_name=model_name,
            verbose_name=str(meta.verbose_name),
            verbose_name_plural=str(meta.verbose_name_plural),
            form_title=form_title,
            form_description=form_description,
            fields=form_fields,
            relationships=form_relationships,
            nested=nested_metadata,
            field_order=field_order,
            exclude_fields=exclude_fields,
            readonly_fields=readonly_fields,
            required_permissions=required_permissions,
            form_validation_rules=self._get_form_validation_rules(model),
            form_layout=self._get_form_layout(model),
            css_classes=self._get_form_css_classes(model),
            form_attributes=self._get_form_attributes(model),
            permissions=_build_model_permission_matrix(model, user),
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

    def _extract_nested_metadata(
        self, model, meta, user, nested_fields, current_depth, visited_models
    ) -> list[ModelFormMetadata]:
        """Extract nested form metadata for specified relationship fields."""
        nested_metadata = []

        if not nested_fields:
            return nested_metadata

        for field_name in nested_fields:
            try:
                field = meta.get_field(field_name)
                if hasattr(field, "related_model") and field.related_model:
                    related_model = field.related_model
                    related_meta = related_model._meta

                    nested_form_metadata = self.extract_model_form_metadata(
                        app_name=related_meta.app_label,
                        model_name=related_model.__name__,
                        user=user,
                        nested_fields=[],
                        current_depth=current_depth + 1,
                        visited_models=visited_models.copy(),
                    )

                    if nested_form_metadata:
                        nested_form_metadata.name = field.name
                        nested_form_metadata.field_name = field.name
                        nested_form_metadata.relationship_type = (
                            field.__class__.__name__
                        )
                        nested_form_metadata.to_field = (
                            field.remote_field.name
                            if hasattr(field, "remote_field") and field.remote_field
                            else None
                        )
                        nested_form_metadata.from_field = field.name
                        nested_form_metadata.is_required = not getattr(
                            field, "blank", True
                        )
                        nested_metadata.append(nested_form_metadata)
            except Exception as e:
                logger.warning(
                    f"Could not extract nested metadata for field {field_name}: {e}"
                )

        return nested_metadata

    def _get_form_validation_rules(self, model) -> Optional[dict[str, Any]]:
        """Get form validation rules for the model."""
        return {
            "validate_on_blur": True,
            "validate_on_change": True,
            "show_errors_inline": True,
        }

    def _get_form_layout(self, model) -> Optional[dict[str, Any]]:
        """Get form layout configuration."""
        return {
            "layout_type": "vertical",
            "field_spacing": "medium",
            "group_related_fields": True,
        }

    def _get_form_css_classes(self, model) -> Optional[str]:
        """Get CSS classes for the form."""
        return f"model-form {model._meta.app_label}-{model._meta.model_name}-form"

    def _get_form_attributes(self, model) -> Optional[dict[str, Any]]:
        """Get form HTML attributes."""
        return {
            "novalidate": False,
            "autocomplete": "on",
            "data-model": f"{model._meta.app_label}.{model._meta.model_name}",
        }


__all__ = ["ModelFormMetadataExtractor"]

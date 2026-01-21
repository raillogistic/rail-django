"""Model metadata extractor.

This module provides the ModelMetadataExtractor class which extracts
comprehensive metadata from Django models including fields, relationships,
permissions, filters, and mutations.
"""

import logging
from typing import Any, Optional

from django.apps import apps
from django.db import models
from django.utils.encoding import force_str

from ..types import ModelMetadata, RelationshipMetadata
from .base import BaseMetadataExtractor, _relationship_cardinality
from .model_fields import ModelFieldExtractionMixin
from .model_mutations import MutationExtractionMixin

logger = logging.getLogger(__name__)


def _get_metadata_version_value(app_name: str, model_name: str) -> str:
    """Get the metadata version value for a model."""
    try:
        from ...metadata import _get_metadata_version_value as get_version
        return get_version(app_name, model_name)
    except ImportError:
        import time
        return str(int(time.time() * 1000))


class ModelMetadataExtractor(
    ModelFieldExtractionMixin, MutationExtractionMixin, BaseMetadataExtractor
):
    """Extracts comprehensive metadata from Django models."""

    def _extract_filter_metadata(self, model) -> list[dict[str, Any]]:
        """
        Extract comprehensive filter metadata for a Django model.

        Args:
            model: Django model class.

        Returns:
            List of grouped filter field metadata dictionaries.
        """
        try:
            from ....generators.filter_inputs import EnhancedFilterGenerator
            from ....utils.graphql_meta import get_model_graphql_meta

            max_depth = self.max_depth
            enhanced_generator = EnhancedFilterGenerator(
                max_nested_depth=max_depth,
                enable_nested_filters=True,
                schema_name=self.schema_name,
            )

            grouped_filters = enhanced_generator.get_grouped_filters(model)
            graphql_meta = get_model_graphql_meta(model)
            grouped_filter_dict = {}

            for grouped_filter in grouped_filters:
                field_name = grouped_filter.field_name

                if field_name == "id" or "quick" in field_name:
                    continue

                try:
                    field = model._meta.get_field(field_name)
                    verbose_name = str(field.verbose_name)
                except Exception:
                    field = None
                    verbose_name = field_name

                options = []
                for operation in grouped_filter.operations:
                    filter_name = (
                        f"{field_name}__{operation.lookup_expr}"
                        if operation.lookup_expr != "exact"
                        else field_name
                    )

                    help_text = self._translate_help_text_to_french(
                        operation.description or operation.lookup_expr, verbose_name
                    )

                    option_choices = self._get_field_choices(field, operation.lookup_expr)

                    options.append({
                        "name": filter_name,
                        "lookup_expr": operation.lookup_expr,
                        "help_text": help_text,
                        "filter_type": operation.filter_type,
                        "choices": option_choices,
                    })

                related_model_name = (
                    field.related_model.__name__
                    if (field is not None and getattr(field, "related_model", None))
                    else None
                )

                grouped_filter_dict[field_name] = {
                    "field_name": field_name,
                    "is_nested": False,
                    "related_model": related_model_name,
                    "is_custom": False,
                    "field_label": verbose_name,
                    "options": options,
                }

            # Add quick filter if configured
            if graphql_meta and hasattr(graphql_meta, "quick_filter_fields"):
                if graphql_meta.quick_filter_fields:
                    quick_fields = graphql_meta.quick_filter_fields
                    grouped_filter_dict["quick"] = {
                        "field_name": "quick",
                        "is_nested": False,
                        "related_model": None,
                        "is_custom": True,
                        "field_label": "Quick filter",
                        "options": [{
                            "name": "quick",
                            "lookup_expr": "icontains",
                            "help_text": f"Recherche rapide dans les champs: {', '.join(quick_fields)}",
                            "filter_type": "CharFilter",
                        }],
                    }

            result = list(grouped_filter_dict.values())
            result.sort(key=lambda x: (x["is_custom"], x["is_nested"], x["field_name"]))
            return result

        except Exception as e:
            logger.error(f"Error extracting filter metadata for {model.__name__}: {e}")
            return []

    def _get_field_choices(self, field, lookup_expr: str) -> Optional[list]:
        """Get choices for a CharField field if applicable."""
        if field is None or not isinstance(field, models.CharField):
            return None
        raw_choices = getattr(field, "choices", None)
        if not raw_choices or lookup_expr not in ("exact", "in"):
            return None
        try:
            return [
                {"value": self._json_safe_value(val), "label": force_str(lbl)}
                for val, lbl in raw_choices
            ]
        except Exception:
            return None

    def extract_model_metadata(
        self,
        app_name: str,
        model_name: str,
        user,
        nested_fields: bool = True,
        permissions_included: bool = True,
        include_filters: bool = True,
        include_mutations: bool = True,
        current_depth: int = 0,
    ) -> Optional[ModelMetadata]:
        """
        Extract complete metadata for a Django model.

        Args:
            app_name: Django app label.
            model_name: Model class name.
            user: Current user for permission checking.
            nested_fields: Whether to include relationship metadata.
            permissions_included: Whether to include permission information.
            include_filters: Whether to include filter metadata.
            include_mutations: Whether to include mutation metadata.
            current_depth: Current nesting depth for recursive extraction.

        Returns:
            ModelMetadata with filtered fields based on permissions.
        """
        try:
            model = apps.get_model(app_name, model_name)
        except Exception as e:
            logger.error("Model '%s' not found in app '%s': %s", model_name, app_name, e)
            return None

        # Extract field metadata
        fields = []
        for django_field in model._meta.get_fields():
            if getattr(django_field, "is_relation", False):
                continue
            if getattr(django_field, "auto_created", False):
                continue
            field_metadata = self._extract_field_metadata(django_field, user)
            if field_metadata:
                fields.append(field_metadata)

        # Extract relationships
        relationships = self._extract_relationships(
            model, user, nested_fields, current_depth
        )

        # Get permissions
        permissions = self._get_model_permissions(model, user, permissions_included)

        # Get ordering
        ordering = list(model._meta.ordering) if model._meta.ordering else []
        default_ordering = self._get_default_ordering(model, ordering)

        # Get constraints and indexes
        unique_together = self._get_unique_together(model)
        unique_constraints = self._get_unique_constraints(model)
        indexes = self._get_indexes(model)

        # Extract filters and mutations
        filters = self._extract_filter_metadata(model) if include_filters else []
        mutations = self.extract_mutations_metadata(model, user) if include_mutations else []

        return ModelMetadata(
            metadata_version=_get_metadata_version_value(app_name, model_name),
            app_name=model._meta.app_label,
            model_name=model.__name__,
            verbose_name=str(model._meta.verbose_name),
            verbose_name_plural=str(model._meta.verbose_name_plural),
            table_name=model._meta.db_table,
            primary_key_field=model._meta.pk.name,
            fields=fields,
            relationships=relationships,
            permissions=permissions,
            ordering=ordering,
            default_ordering=default_ordering,
            unique_together=unique_together,
            unique_constraints=unique_constraints,
            indexes=indexes,
            abstract=model._meta.abstract,
            proxy=model._meta.proxy,
            managed=model._meta.managed,
            filters=filters,
            mutations=mutations,
        )

    def _get_default_ordering(self, model, ordering: list) -> list:
        """Get default ordering for model."""
        if ordering:
            return ordering.copy()
        if getattr(model._meta, "get_latest_by", None):
            return [f"-{model._meta.get_latest_by}"]
        return [model._meta.pk.name]

    def _extract_relationships(
        self, model, user, nested_fields: bool, current_depth: int
    ) -> list[RelationshipMetadata]:
        """Extract relationship metadata including reverse relations."""
        relationships = []

        if not nested_fields:
            return relationships

        # Forward relationships
        for django_field in model._meta.get_fields():
            if not getattr(django_field, "is_relation", False):
                continue
            if django_field.name == "polymorphic_ctype":
                continue
            if getattr(django_field, "auto_created", False):
                continue
            rel_metadata = self._extract_relationship_metadata(
                django_field, user, current_depth=current_depth
            )
            if rel_metadata:
                relationships.append(rel_metadata)

        # Reverse relationships
        relationships.extend(self._extract_reverse_relationships(model))
        return relationships

    def _extract_reverse_relationships(self, model) -> list[RelationshipMetadata]:
        """Extract reverse relationship metadata."""
        relationships = []
        reverse_relations = list(getattr(model._meta, "related_objects", []))

        for rel in reverse_relations:
            related_model = getattr(rel, "related_model", None)
            if related_model is None or not hasattr(related_model, "_meta"):
                continue

            accessor_name = rel.get_accessor_name()
            rel_field = getattr(rel, "field", None)
            many_to_many = bool(getattr(rel, "many_to_many", False)) or (
                rel_field and isinstance(rel_field, models.ManyToManyField)
            )
            one_to_one = bool(getattr(rel, "one_to_one", False)) or (
                rel_field and isinstance(rel_field, models.OneToOneField)
            )
            foreign_key = bool(getattr(rel, "many_to_one", False)) or (
                rel_field and isinstance(rel_field, models.ForeignKey)
            )
            relationship_type = rel_field.__class__.__name__ if rel_field else "ReverseRelation"
            related_app_label = getattr(related_model._meta, "app_label", "")

            relationships.append(
                RelationshipMetadata(
                    name=accessor_name,
                    verbose_name=related_model._meta.verbose_name,
                    relationship_type=relationship_type,
                    cardinality=_relationship_cardinality(
                        True, many_to_many, one_to_one, foreign_key
                    ),
                    related_model=related_model.__name__,
                    related_app=related_app_label,
                    to_field=getattr(rel_field, "name", None),
                    is_required=False,
                    from_field=accessor_name,
                    is_reverse=True,
                    many_to_many=many_to_many,
                    one_to_one=one_to_one,
                    foreign_key=foreign_key,
                    on_delete=None,
                    related_name=accessor_name,
                    has_permission=True,
                )
            )
        return relationships

    def _get_model_permissions(self, model, user, include: bool) -> list[str]:
        """Get model permissions for the user."""
        if not include or not user:
            return []

        from django.contrib.auth.models import AnonymousUser
        if isinstance(user, AnonymousUser):
            return []

        permissions = []
        app_label = model._meta.app_label
        model_name_code = model._meta.model_name

        for action in ["add", "change", "delete", "view"]:
            perm_code = f"{app_label}.{action}_{model_name_code}"
            try:
                if user.has_perm(perm_code):
                    permissions.append(perm_code)
            except Exception:
                continue
        return permissions

    def _get_unique_together(self, model) -> list[list[str]]:
        """Get unique_together constraints."""
        if not hasattr(model._meta, "unique_together") or not model._meta.unique_together:
            return []
        return [list(constraint) for constraint in model._meta.unique_together]

    def _get_unique_constraints(self, model) -> list[dict[str, Any]]:
        """Get unique constraints."""
        unique_constraints = []
        if hasattr(model._meta, "constraints"):
            for constraint in model._meta.constraints:
                if isinstance(constraint, models.UniqueConstraint):
                    unique_constraints.append({
                        "name": constraint.name,
                        "fields": list(getattr(constraint, "fields", []) or []),
                        "condition": str(constraint.condition) if getattr(constraint, "condition", None) else None,
                        "deferrable": getattr(constraint, "deferrable", None),
                    })
        return unique_constraints

    def _get_indexes(self, model) -> list[dict[str, Any]]:
        """Get model indexes."""
        indexes = []
        if hasattr(model._meta, "indexes"):
            for index in model._meta.indexes:
                indexes.append({
                    "name": index.name,
                    "fields": list(index.fields),
                    "unique": getattr(index, "unique", False),
                    "condition": str(index.condition) if getattr(index, "condition", None) else None,
                    "include": list(getattr(index, "include", []) or []),
                })
        return indexes


__all__ = ["ModelMetadataExtractor"]

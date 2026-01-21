"""Model field extraction methods.

This module provides mixin classes for extracting field metadata
from Django models for GraphQL schema generation.
"""

import logging
from typing import Any, Optional

from django.db import models
from django.utils.encoding import force_str

from ..types import FieldMetadata, RelationshipMetadata
from .base import _is_fsm_field_instance, _relationship_cardinality

logger = logging.getLogger(__name__)


class ModelFieldExtractionMixin:
    """
    Mixin providing model field extraction functionality.

    This mixin should be used with BaseMetadataExtractor to provide
    field extraction capabilities.
    """

    def _extract_field_metadata(self, field, user) -> Optional[FieldMetadata]:
        """
        Extract metadata for a single field with permission checking.

        Args:
            field: Django model field instance.
            user: User instance for permission checking.

        Returns:
            FieldMetadata if user has permission, None otherwise.
        """
        # Get field choices
        choices = None
        if hasattr(field, "choices") and field.choices:
            choices = [
                {
                    "value": self._json_safe_value(choice[0]),
                    "label": force_str(choice[1]),
                }
                for choice in field.choices
            ]

        # Get validation attributes
        max_length = getattr(field, "max_length", None)
        min_length = getattr(field, "min_length", None)
        min_value, max_value, regex = self._extract_validators(field)

        db_column = getattr(field, "db_column", None) or getattr(field, "column", None)
        internal_type = self._get_internal_type(field)
        db_type = self._get_db_type(field)

        # Permission flag
        has_permission = True
        is_fsm_field = _is_fsm_field_instance(field)
        editable_flag = bool(field.editable) and not is_fsm_field
        default_value = (
            self._json_safe_value(field.default)
            if field.default != models.NOT_PROVIDED
            else None
        )

        return FieldMetadata(
            name=field.name,
            field_type=field.__class__.__name__,
            is_required=not field.blank and field.default == models.NOT_PROVIDED,
            is_nullable=field.null,
            null=field.null,
            default_value=default_value,
            help_text=field.help_text or "",
            db_column=db_column,
            db_type=db_type,
            internal_type=internal_type,
            max_length=max_length,
            min_length=min_length,
            min_value=min_value,
            max_value=max_value,
            regex=regex,
            choices=choices,
            is_primary_key=getattr(field, "primary_key", None),
            is_foreign_key=isinstance(field, models.ForeignKey),
            is_unique=field.unique,
            is_indexed=field.db_index,
            has_auto_now=getattr(field, "auto_now", False),
            has_auto_now_add=getattr(field, "auto_now_add", False),
            blank=field.blank,
            editable=editable_flag,
            verbose_name=str(field.verbose_name),
            has_permission=has_permission,
        )

    def _extract_validators(self, field) -> tuple[Any, Any, Optional[str]]:
        """Extract min/max values and regex pattern from field validators."""
        min_value = None
        max_value = None
        regex = None
        validators = getattr(field, "validators", None) or []
        max_length = getattr(field, "max_length", None)
        min_length = getattr(field, "min_length", None)

        try:
            from django.core.validators import (
                MaxLengthValidator,
                MaxValueValidator,
                MinLengthValidator,
                MinValueValidator,
                RegexValidator,
            )
        except (ImportError, AttributeError):
            return min_value, max_value, regex

        for validator in validators:
            if isinstance(validator, MinValueValidator):
                min_value = validator.limit_value
            elif isinstance(validator, MaxValueValidator):
                max_value = validator.limit_value
            elif isinstance(validator, MinLengthValidator) and min_length is None:
                min_length = validator.limit_value
            elif isinstance(validator, MaxLengthValidator) and max_length is None:
                max_length = validator.limit_value
            elif isinstance(validator, RegexValidator):
                try:
                    regex = validator.regex.pattern
                except (AttributeError, TypeError):
                    regex = str(getattr(validator, "regex", None) or "")

        return min_value, max_value, regex

    def _get_internal_type(self, field) -> Optional[str]:
        """Get the internal type of a field."""
        try:
            return field.get_internal_type()
        except (AttributeError, TypeError, NotImplementedError):
            return None

    def _get_db_type(self, field) -> Optional[str]:
        """Get the database type of a field."""
        try:
            from django.db import connection
            return field.db_type(connection)
        except Exception:
            return None

    def _extract_relationship_metadata(
        self, field, user, current_depth: int = 0
    ) -> Optional[RelationshipMetadata]:
        """
        Extract metadata for relationship fields.

        Args:
            field: Django relationship field instance.
            user: User instance for permission checking.
            current_depth: Current nesting depth.

        Returns:
            RelationshipMetadata if user has permission, None otherwise.
        """
        related_model = field.related_model
        on_delete = None

        if getattr(field, "remote_field", None) is not None:
            remote_on_delete = getattr(field.remote_field, "on_delete", None)
            if remote_on_delete:
                on_delete = getattr(remote_on_delete, "__name__", None)

        has_permission = True

        if related_model is None or not hasattr(related_model, "_meta"):
            return None

        related_app_label = getattr(related_model._meta, "app_label", "")
        related_model_class_name = related_model.__name__
        many_to_many = isinstance(field, models.ManyToManyField)
        one_to_one = isinstance(field, models.OneToOneField)
        foreign_key = isinstance(field, models.ForeignKey)

        return RelationshipMetadata(
            name=field.name,
            relationship_type=field.__class__.__name__,
            cardinality=_relationship_cardinality(
                False, many_to_many, one_to_one, foreign_key
            ),
            related_model=related_model_class_name,
            is_required=not field.blank,
            related_app=related_app_label,
            to_field=field.remote_field.name
            if hasattr(field, "remote_field") and field.remote_field
            else None,
            from_field=field.name,
            is_reverse=False,
            many_to_many=many_to_many,
            one_to_one=one_to_one,
            foreign_key=foreign_key,
            on_delete=on_delete,
            related_name=getattr(field, "related_name", None),
            has_permission=has_permission,
            verbose_name=field.verbose_name,
        )


__all__ = ["ModelFieldExtractionMixin"]

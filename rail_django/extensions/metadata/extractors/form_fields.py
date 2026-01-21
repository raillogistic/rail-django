"""Form field extraction methods.

This module provides mixin classes for extracting form field metadata
from Django models for frontend form generation.
"""

import logging
from typing import Any, Optional

from django.db import models
from django.utils.encoding import force_str

from ..types import (
    FormFieldMetadata,
    FormRelationshipMetadata,
)
from .base import (
    _build_field_permission_snapshot,
    _is_fsm_field_instance,
    _relationship_cardinality,
)

logger = logging.getLogger(__name__)


class FormFieldExtractionMixin:
    """
    Mixin providing form field extraction functionality.

    This mixin should be used with BaseMetadataExtractor to provide
    form field extraction capabilities.
    """

    def _extract_form_field_metadata(
        self, field, user
    ) -> Optional[FormFieldMetadata]:
        """
        Extract form-specific metadata for a single field.

        Args:
            field: Django model field instance.
            user: User instance for permission checking.

        Returns:
            FormFieldMetadata if user has permission, None otherwise.
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

        # Determine widget type
        widget_type = self._get_form_widget_type(field)

        # Generate placeholder text
        placeholder = self._generate_placeholder(field)

        # Get validation attributes
        max_length = getattr(field, "max_length", None)
        min_length = (
            getattr(field, "min_length", None) if hasattr(field, "min_length") else None
        )
        max_value = (
            getattr(field, "max_value", None) if hasattr(field, "max_value") else None
        )
        min_value = (
            getattr(field, "min_value", None) if hasattr(field, "min_value") else None
        )

        # Handle decimal fields
        decimal_places = getattr(field, "decimal_places", None)
        max_digits = getattr(field, "max_digits", None)

        # Determine if field is required for forms
        is_required = not field.blank and field.default == models.NOT_PROVIDED

        # Get default value for forms
        default_value = None
        if field.default != models.NOT_PROVIDED:
            if callable(field.default):
                try:
                    default_value = field.default()
                except Exception:
                    default_value = None
            else:
                default_value = field.default
        default_value = self._to_json_safe(default_value)

        model = field.model
        permission_snapshot = _build_field_permission_snapshot(user, model, field.name)
        if permission_snapshot and not permission_snapshot.can_read:
            return None
        has_permission = permission_snapshot.can_read if permission_snapshot else True

        is_fsm_field = _is_fsm_field_instance(field)
        editable_flag = bool(field.editable) and not is_fsm_field
        disabled_flag = not editable_flag
        readonly_flag = (not editable_flag) or bool(
            getattr(field, "primary_key", False)
        )
        if permission_snapshot and not permission_snapshot.can_write:
            disabled_flag = True
            readonly_flag = True

        validators = self._extract_field_validators(field)
        error_messages = self._extract_error_messages(field)

        return FormFieldMetadata(
            name=field.name,
            field_type=field.__class__.__name__,
            is_required=is_required,
            verbose_name=str(field.verbose_name),
            help_text=field.help_text or "",
            widget_type=widget_type,
            placeholder=placeholder,
            default_value=default_value,
            choices=choices,
            max_length=max_length,
            min_length=min_length,
            decimal_places=decimal_places,
            max_digits=max_digits,
            min_value=min_value,
            max_value=max_value,
            auto_now=getattr(field, "auto_now", False),
            auto_now_add=getattr(field, "auto_now_add", False),
            blank=field.blank,
            null=field.null,
            unique=field.unique,
            editable=editable_flag,
            validators=validators,
            error_messages=error_messages,
            has_permission=has_permission,
            disabled=disabled_flag,
            readonly=readonly_flag,
            css_classes=self._get_css_classes(field),
            data_attributes=self._to_json_safe(self._get_data_attributes(field)),
            permissions=permission_snapshot,
        )

    def _extract_form_relationship_metadata(
        self, field, user, current_depth: int = 0, visited_models: set = None
    ) -> Optional[FormRelationshipMetadata]:
        """
        Extract form-specific metadata for relationship fields.

        Args:
            field: Django relationship field instance.
            user: User instance for permission checking.
            current_depth: Current nesting depth.
            visited_models: Set of already visited models.

        Returns:
            FormRelationshipMetadata if user has permission, None otherwise.
        """
        related_model = field.related_model

        if related_model is None or not hasattr(related_model, "_meta"):
            return None

        related_app_label = getattr(related_model._meta, "app_label", "")
        related_model_class_name = related_model.__name__

        # Determine widget type for relationship
        widget_type = self._get_relationship_widget_type(field)

        model = field.model
        permission_snapshot = _build_field_permission_snapshot(user, model, field.name)
        if permission_snapshot and not permission_snapshot.can_read:
            return None
        has_permission = permission_snapshot.can_read if permission_snapshot else True

        # Handle verbose_name for reverse relationships
        if hasattr(field, "verbose_name"):
            verbose_name = str(field.verbose_name)
        else:
            verbose_name = field.name.replace("_", " ").title()

        many_to_many = isinstance(field, models.ManyToManyField)
        one_to_one = isinstance(field, models.OneToOneField)
        foreign_key = isinstance(field, models.ForeignKey)

        # Detect reverse relationships
        is_reverse = False
        try:
            from django.db.models.fields.reverse_related import (
                ManyToOneRel,
                ManyToManyRel,
                OneToOneRel,
            )
            is_reverse = isinstance(field, (ManyToOneRel, ManyToManyRel, OneToOneRel))
            if isinstance(field, ManyToManyRel):
                many_to_many = True
            elif isinstance(field, OneToOneRel):
                one_to_one = True
            elif isinstance(field, ManyToOneRel):
                foreign_key = True
        except Exception:
            if bool(getattr(field, "auto_created", False)) and not isinstance(
                field,
                (models.ForeignKey, models.OneToOneField, models.ManyToManyField),
            ):
                is_reverse = True

        return FormRelationshipMetadata(
            name=field.name,
            relationship_type=field.__class__.__name__,
            cardinality=_relationship_cardinality(
                is_reverse, many_to_many, one_to_one, foreign_key
            ),
            verbose_name=verbose_name,
            help_text=getattr(field, "help_text", "") or "",
            widget_type=widget_type,
            is_required=not getattr(field, "blank", True),
            related_model=related_model_class_name,
            related_app=related_app_label,
            to_field=field.remote_field.name
            if hasattr(field, "remote_field") and field.remote_field
            else None,
            from_field=field.name,
            many_to_many=many_to_many,
            one_to_one=one_to_one,
            foreign_key=foreign_key,
            is_reverse=is_reverse,
            multiple=many_to_many,
            queryset_filters=self._to_json_safe(self._get_queryset_filters(field)),
            empty_label=self._get_empty_label(field),
            limit_choices_to=self._to_json_safe(
                getattr(field, "limit_choices_to", None)
            ),
            has_permission=has_permission,
            disabled=(not field.editable)
            or (permission_snapshot and not permission_snapshot.can_write),
            readonly=(
                not field.editable
                or getattr(field, "primary_key", None)
                or (permission_snapshot and not permission_snapshot.can_write)
            ),
            css_classes=self._get_css_classes(field),
            data_attributes=self._to_json_safe(self._get_data_attributes(field)),
            permissions=permission_snapshot,
        )

    def _get_form_widget_type(self, field) -> str:
        """Get the recommended widget type for a form field."""
        widget_mapping = {
            models.CharField: "text",
            models.TextField: "textarea",
            models.EmailField: "email",
            models.URLField: "url",
            models.IntegerField: "number",
            models.FloatField: "number",
            models.DecimalField: "number",
            models.BooleanField: "checkbox",
            models.DateField: "date",
            models.DateTimeField: "datetime-local",
            models.TimeField: "time",
            models.FileField: "file",
            models.ImageField: "file",
            models.ForeignKey: "select",
            models.ManyToManyField: "select",
            models.OneToOneField: "select",
        }

        if hasattr(field, "choices") and field.choices:
            return "select"

        return widget_mapping.get(field.__class__, "text")

    def _get_relationship_widget_type(self, field) -> str:
        """Get the recommended widget type for relationship fields."""
        if isinstance(field, models.ManyToManyField):
            return "multiselect"
        elif isinstance(field, (models.ForeignKey, models.OneToOneField)):
            return "select"
        return "select"

    def _generate_placeholder(self, field) -> Optional[str]:
        """Generate placeholder text for form fields."""
        if hasattr(field, "help_text") and field.help_text:
            return field.help_text
        return f"Enter {field.verbose_name.lower()}"

    def _get_queryset_filters(self, field) -> Optional[dict[str, Any]]:
        """Get queryset filters for relationship fields."""
        if hasattr(field, "limit_choices_to") and field.limit_choices_to:
            return field.limit_choices_to
        return None

    def _get_empty_label(self, field) -> Optional[str]:
        """Get empty label for choice fields."""
        if hasattr(field, "choices") and field.choices:
            return f"Select {field.verbose_name.lower()}"
        return None

    def _get_css_classes(self, field) -> Optional[str]:
        """Get CSS classes for form fields."""
        classes = ["form-control"]

        if isinstance(field, models.TextField):
            classes.append("form-textarea")
        elif isinstance(
            field, (models.DateField, models.DateTimeField, models.TimeField)
        ):
            classes.append("form-date")
        elif isinstance(
            field, (models.IntegerField, models.FloatField, models.DecimalField)
        ):
            classes.append("form-number")
        elif isinstance(field, models.BooleanField):
            classes.append("form-checkbox")
        elif isinstance(field, (models.FileField, models.ImageField)):
            classes.append("form-file")

        if getattr(field, "primary_key", None):
            classes.append("form-readonly")

        return " ".join(classes)

    def _get_data_attributes(self, field) -> Optional[dict[str, Any]]:
        """Get data attributes for form fields."""
        attributes = {}

        if hasattr(field, "max_length") and field.max_length:
            attributes["maxlength"] = field.max_length

        if hasattr(field, "min_length") and field.min_length:
            attributes["minlength"] = field.min_length

        return attributes if attributes else None

    def _extract_field_validators(self, field) -> Optional[list[str]]:
        """Return validator identifiers suitable for frontend metadata."""
        validators = getattr(field, "validators", None) or []
        validator_names = []
        for validator in validators:
            name = getattr(validator, "__name__", None) or validator.__class__.__name__
            if name:
                validator_names.append(name)
        return validator_names or None

    def _extract_error_messages(self, field) -> Optional[dict[str, str]]:
        """Return field error message templates as plain strings."""
        error_messages = getattr(field, "error_messages", None) or {}
        if not error_messages:
            return None
        cleaned = {}
        for key, message in error_messages.items():
            if message in (None, ""):
                continue
            cleaned[force_str(key)] = force_str(message)
        return cleaned or None


__all__ = ["FormFieldExtractionMixin"]

"""Mutation input field extraction methods.

This module provides helper functions for extracting input field metadata
from Django models and Python method signatures for GraphQL mutations.
"""

import inspect
import logging
from typing import Any, Optional, Union, get_args, get_origin

from django.db import models
from django.utils.encoding import force_str

from ..types import InputFieldMetadata

logger = logging.getLogger(__name__)


class InputFieldExtractionMixin:
    """Mixin for extracting input fields from models and methods."""

    def _extract_input_fields_from_model(
        self, model: type[models.Model], mutation_type: str
    ) -> list[InputFieldMetadata]:
        """Extract input fields from Django model fields."""
        input_fields = []

        for field in model._meta.fields:
            if getattr(field, "primary_key", None) and mutation_type == "create":
                continue
            if hasattr(field, "auto_now") or hasattr(field, "auto_now_add"):
                continue

            input_field = self._convert_django_field_to_input_metadata(
                field, mutation_type
            )
            if input_field:
                input_fields.append(input_field)

        return input_fields

    def _convert_django_field_to_input_metadata(
        self, field, mutation_type: str
    ) -> Optional[InputFieldMetadata]:
        """Convert Django field to InputFieldMetadata."""
        try:
            field_name = field.name
            field_type = "String"
            required = (
                not field.null and not field.blank and not hasattr(field, "default")
            )

            if mutation_type == "update":
                required = False

            # Map Django field types to GraphQL types
            field_type = self._get_graphql_type_for_field(field)

            choices = None
            if hasattr(field, "choices") and field.choices:
                choices = [
                    {
                        "value": self._json_safe_value(choice[0]),
                        "label": force_str(choice[1]),
                    }
                    for choice in field.choices
                ]

            widget_type = self._get_widget_type_for_field(field)

            return InputFieldMetadata(
                name=field_name,
                field_type=field_type,
                required=required,
                description=str(field.verbose_name)
                if hasattr(field, "verbose_name")
                else None,
                choices=choices,
                widget_type=widget_type,
                help_text=str(field.help_text)
                if hasattr(field, "help_text") and field.help_text
                else None,
                max_length=getattr(field, "max_length", None),
                related_model=field.related_model.__name__
                if hasattr(field, "related_model") and field.related_model
                else None,
                multiple=isinstance(field, models.ManyToManyField),
            )
        except Exception as e:
            logger.error(f"Error converting field {field.name}: {e}")
            return None

    def _get_graphql_type_for_field(self, field) -> str:
        """Map Django field types to GraphQL types."""
        if isinstance(field, models.CharField):
            return "String"
        elif isinstance(field, models.TextField):
            return "String"
        elif isinstance(field, models.IntegerField):
            return "Int"
        elif isinstance(field, models.FloatField):
            return "Float"
        elif isinstance(field, models.BooleanField):
            return "Boolean"
        elif isinstance(field, models.DateTimeField):
            return "DateTime"
        elif isinstance(field, models.DateField):
            return "Date"
        elif isinstance(field, models.EmailField):
            return "String"
        elif isinstance(field, models.URLField):
            return "String"
        elif isinstance(field, models.ForeignKey):
            return "ID"
        elif isinstance(field, models.ManyToManyField):
            return "List[ID]"
        return "String"

    def _get_widget_type_for_field(self, field) -> str:
        """Determine the appropriate widget type for a Django field."""
        if isinstance(field, models.TextField):
            return "textarea"
        elif isinstance(field, models.EmailField):
            return "email"
        elif isinstance(field, models.URLField):
            return "url"
        elif isinstance(field, models.BooleanField):
            return "checkbox"
        elif isinstance(field, models.DateTimeField):
            return "datetime-local"
        elif isinstance(field, models.DateField):
            return "date"
        elif isinstance(field, models.IntegerField):
            return "number"
        elif isinstance(field, models.FloatField):
            return "number"
        elif isinstance(field, models.ForeignKey):
            return "select"
        elif isinstance(field, models.ManyToManyField):
            return "multiselect"
        elif hasattr(field, "choices") and field.choices:
            return "select"
        return "text"

    def _extract_input_fields_from_method(self, method) -> list[InputFieldMetadata]:
        """Extract input fields from method signature."""
        from datetime import date, datetime, time

        input_fields: list[InputFieldMetadata] = []
        signature = inspect.signature(method)
        action_ui = getattr(method, "_action_ui", {}) or {}
        field_overrides: dict[str, dict[str, Any]] = action_ui.get("fields", {}) or {}

        for param_name, param in signature.parameters.items():
            if param_name == "self":
                continue

            field_type = "String"
            required = param.default == inspect.Parameter.empty
            default_value = (
                param.default if param.default != inspect.Parameter.empty else None
            )

            if param.annotation != inspect.Parameter.empty:
                field_type, required = self._resolve_param_type(
                    param.annotation, required
                )

            input_field = InputFieldMetadata(
                name=param_name,
                field_type=field_type,
                required=required,
                default_value=default_value,
                description=f"Parameter {param_name} for method execution",
            )

            override = field_overrides.get(param_name) or {}
            if override:
                self._apply_field_overrides(input_field, override)

            input_fields.append(input_field)

        return input_fields

    def _resolve_param_type(self, annotation, required: bool) -> tuple[str, bool]:
        """Resolve parameter type annotation to GraphQL type."""
        from datetime import date, datetime, time

        origin = get_origin(annotation)
        args = get_args(annotation)
        base_annotation = annotation

        if origin is Union:
            non_none = [arg for arg in args if arg is not type(None)]
            if non_none:
                base_annotation = non_none[0]
                required = False

        if base_annotation == int:
            return "Int", required
        elif base_annotation == float:
            return "Float", required
        elif base_annotation == bool:
            return "Boolean", required
        elif base_annotation in (date, datetime):
            return "Date" if base_annotation is date else "DateTime", required
        elif base_annotation is time:
            return "Time", required
        elif origin in (list, tuple, set):
            inner = args[0] if args else Any
            inner_type = "String"
            if inner == int:
                inner_type = "Int"
            elif inner == float:
                inner_type = "Float"
            elif inner == bool:
                inner_type = "Boolean"
            return f"List[{inner_type}]", required

        return "String", required

    def _apply_field_overrides(
        self, input_field: InputFieldMetadata, override: dict
    ) -> None:
        """Apply field overrides from action UI configuration."""
        if "label" in override:
            input_field.description = force_str(override.get("label"))
        if "required" in override:
            input_field.required = bool(override.get("required"))
        if "widget_type" in override:
            input_field.widget_type = override.get("widget_type")
        if "placeholder" in override:
            input_field.placeholder = override.get("placeholder")
        if "help_text" in override:
            input_field.help_text = override.get("help_text")


__all__ = ["InputFieldExtractionMixin"]

"""
Schema Settings Mixin for Rail Django.

Checks if models/apps are excluded from the schema based on
schema settings configuration.
"""

from __future__ import annotations

from typing import Type

from django.db import models


class SchemaSettingsMixin:
    """
    Mixin for schema settings integration.

    Checks if models/apps are excluded from the schema.
    """

    def __init__(self, schema_name: str = "default"):
        """
        Initialize the mixin with schema name.

        Args:
            schema_name: Name of the schema to check settings for
        """
        self.schema_name = schema_name

    def is_model_excluded(self, model: Type[models.Model]) -> bool:
        """
        Check if model is excluded from schema.

        Args:
            model: Django model class

        Returns:
            True if model should be excluded
        """
        if model is None or not hasattr(model, "_meta"):
            return False

        try:
            from rail_django.core.settings import SchemaSettings

            settings = SchemaSettings.from_schema(self.schema_name)
        except (ImportError, AttributeError, KeyError):
            return False

        app_label = getattr(model._meta, "app_label", "")
        if app_label in (settings.excluded_apps or []):
            return True

        excluded_models = set(settings.excluded_models or [])
        if not excluded_models:
            return False

        model_name = getattr(model, "__name__", "")
        model_label = getattr(model._meta, "model_name", "")
        full_model_name = f"{app_label}.{model_name}" if app_label else model_name

        return (
            model_name in excluded_models
            or model_label in excluded_models
            or full_model_name in excluded_models
        )


__all__ = ["SchemaSettingsMixin"]

"""
Registration Mixin - App and model registration methods.

This module provides the RegistrationMixin class with methods for
registering and unregistering apps and models from schema generation.
"""

import logging
from typing import Union, Optional

import graphene
from django.apps import apps
from django.db import models
from graphene.utils.str_converters import to_snake_case

logger = logging.getLogger(__name__)


class RegistrationMixin:
    """
    Mixin providing app and model registration methods.

    This mixin is designed to be used with SchemaBuilderCore to provide
    methods for dynamically registering and unregistering apps and models.
    """

    def register_app(self, app_label: str) -> None:
        """
        Registers a Django app for schema generation.

        Args:
            app_label: Django app label to register
        """
        if app_label in self.settings.excluded_apps:
            self.settings.excluded_apps.remove(app_label)
            self.rebuild_schema()
            logger.info(
                f"App '{app_label}' registered for schema "
                f"'{self.schema_name}' generation"
            )

    def unregister_app(self, app_label: str) -> None:
        """
        Unregisters a Django app from schema generation.

        Args:
            app_label: Django app label to unregister
        """
        if app_label not in self.settings.excluded_apps:
            self.settings.excluded_apps.append(app_label)
            self.rebuild_schema()
            logger.info(
                f"App '{app_label}' unregistered from schema "
                f"'{self.schema_name}' generation"
            )

    def register_model(self, model: Union[type[models.Model], str]) -> None:
        """
        Registers a model for schema generation.

        Args:
            model: Django model class or model name to register
        """
        model_identifier = model.__name__ if isinstance(model, type) else model
        if model_identifier in self.settings.excluded_models:
            self.settings.excluded_models.remove(model_identifier)
            self.rebuild_schema()
            logger.info(
                f"Model '{model_identifier}' registered for schema "
                f"'{self.schema_name}' generation"
            )

    def unregister_model(self, model: Union[type[models.Model], str]) -> None:
        """
        Unregisters a model from schema generation.

        Args:
            model: Django model class or model name to unregister
        """
        model_identifier = model.__name__ if isinstance(model, type) else model
        if model_identifier not in self.settings.excluded_models:
            self.settings.excluded_models.append(model_identifier)
            self.rebuild_schema()
            logger.info(
                f"Model '{model_identifier}' unregistered from schema "
                f"'{self.schema_name}' generation"
            )

    def register_mutation(self, mutation_class: type[graphene.Mutation], name: Optional[str] = None) -> None:
        """
        Registers a custom mutation class.

        Args:
            mutation_class: Graphene mutation class to register
            name: Optional name for the mutation field (defaults to snake_case of class name)
        """
        if not name:
            name = to_snake_case(mutation_class.__name__)
        
        with self._lock:
            self._mutation_fields[name] = mutation_class.Field()
            self.rebuild_schema()
            
        logger.info(
            f"Custom mutation '{name}' registered for schema "
            f"'{self.schema_name}'"
        )

    def reload_app_schema(self, app_label: str) -> None:
        """
        Reloads schema for a specific app.

        Args:
            app_label: Django app label to reload
        """
        try:
            apps.get_app_config(app_label)
            # Rebuild the full schema to guarantee naming consistency and avoid
            # stale root fields when naming conventions evolve.
            self.rebuild_schema()

            logger.info(
                f"Schema reloaded for app '{app_label}' in schema '{self.schema_name}'"
            )

        except Exception as e:
            logger.error(
                f"Failed to reload schema for app '{app_label}' in "
                f"schema '{self.schema_name}': {str(e)}",
                exc_info=True,
            )
            raise

    def _register_schema_in_registry(
        self, discovered_models: list[type[models.Model]]
    ) -> None:
        """Register the schema in the schema registry."""
        try:
            from ..registry import register_schema, schema_registry

            existing = schema_registry.get_schema(self.schema_name)
            description = (
                existing.description
                if existing and existing.description
                else f"Auto-generated GraphQL schema for {self.schema_name}"
            )
            schema_apps = existing.apps if existing else None
            exclude_models = existing.exclude_models if existing else None
            settings_payload = existing.settings if existing else None
            auto_discover = existing.auto_discover if existing else True
            enabled = existing.enabled if existing else True

            models_list = None
            if existing is not None and existing.models:
                raw_models = existing.models or []
                normalized_models = []
                for model in raw_models:
                    if hasattr(model, "_meta"):
                        normalized_models.append(model._meta.label)
                    else:
                        normalized_models.append(str(model))
                if normalized_models:
                    models_list = normalized_models
            if models_list is None:
                models_list = [model._meta.label for model in self._registered_models]

            register_schema(
                name=self.schema_name,
                description=description,
                version=str(self._schema_version),
                apps=schema_apps,
                models=models_list,
                exclude_models=exclude_models,
                settings=settings_payload,
                auto_discover=auto_discover,
                enabled=enabled,
            )
            logger.info(
                f"Schema '{self.schema_name}' registered in schema registry"
            )
        except ImportError as e:
            logger.warning(
                f"Could not register schema '{self.schema_name}' in registry: {e}"
            )

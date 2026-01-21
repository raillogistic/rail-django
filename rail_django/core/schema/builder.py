"""
Schema Builder Core - Core SchemaBuilder class with initialization and settings.

This module provides the core SchemaBuilder class with model discovery,
settings management, and schema lifecycle methods.
"""

import logging
import threading
from typing import Any, Optional, Set, Type, Union

import graphene
from django.apps import apps
from django.conf import settings as django_settings
from django.db import models
from django.db.models.signals import post_delete, post_migrate, post_save

logger = logging.getLogger(__name__)

_SYSTEM_EXCLUDED_APPS = {"admin", "contenttypes", "sessions"}
_SYSTEM_EXCLUDED_MODEL_NAMES = {"logentry"}


class SchemaBuilderCore:
    """
    Core SchemaBuilder functionality including initialization,
    settings management, and model discovery.
    """

    _instances: dict[str, "SchemaBuilderCore"] = {}
    _lock = threading.Lock()

    def __new__(
        cls,
        settings: Optional[Any] = None,
        schema_name: str = "default",
        *args,
        **kwargs,
    ):
        """Create or return existing SchemaBuilder instance for the given schema name."""
        with cls._lock:
            if schema_name not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[schema_name] = instance
            return cls._instances[schema_name]

    def __init__(
        self,
        settings: Optional[Any] = None,
        schema_name: str = "default",
        raw_settings: Optional[dict] = None,
        registry=None,
    ):
        """
        Initialize the SchemaBuilder.

        Args:
            settings: Schema settings instance or None for defaults
            schema_name: Name of the schema (for multi-schema support)
            raw_settings: Raw settings dictionary containing schema_settings
            registry: Schema registry instance for model discovery
        """
        # Avoid re-initialization
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.schema_name = schema_name
        self.registry = registry

        # Store the raw settings dictionary for schema_settings extraction
        self._raw_settings = raw_settings or {}

        # Load settings using the new configuration system
        self._settings_locked = settings is not None
        if settings is None:
            try:
                from ...config_proxy import get_core_schema_settings
                from ..settings import SchemaSettings

                # Get schema-specific settings
                settings_dict = get_core_schema_settings(schema_name)
                if settings_dict:
                    # Convert dictionary to SchemaSettings dataclass
                    self.settings = SchemaSettings(**settings_dict)
                else:
                    # Use default settings if empty
                    self.settings = SchemaSettings()

                # If no raw_settings provided, use the settings_dict
                if not self._raw_settings:
                    self._raw_settings = settings_dict or {}
            except ImportError:
                # Fallback to legacy settings
                from ..settings import SchemaSettings

                self.settings = SchemaSettings()
        else:
            self.settings = settings
            # If raw_settings is provided, use it; otherwise, initialize empty
            if not self._raw_settings:
                self._raw_settings = {}

        # Initialize generators with lazy imports to avoid circular dependencies
        self._type_generator = None
        self._query_generator = None
        self._mutation_generator = None
        self._subscription_generator = None

        # Schema state
        self._schema = None
        self._query_fields: dict[str, Union[graphene.Field, graphene.List]] = {}
        self._mutation_fields: dict[str, type[graphene.Mutation]] = {}
        self._subscription_fields: dict[str, graphene.Field] = {}
        self._registered_models: set[type[models.Model]] = set()
        self._schema_version = 0

        self._initialized = True
        self._connect_signals()

    def _refresh_settings_if_needed(self) -> None:
        """Refresh settings from config proxy if not locked."""
        if self._settings_locked:
            return
        try:
            from ...config_proxy import get_core_schema_settings
            from ..settings import SchemaSettings

            settings_dict = get_core_schema_settings(self.schema_name) or {}
        except ImportError:
            return

        if settings_dict != (self._raw_settings or {}):
            self.settings = (
                SchemaSettings(**settings_dict) if settings_dict else SchemaSettings()
            )
            self._raw_settings = settings_dict or {}
            self._schema = None

    @property
    def type_generator(self):
        """Lazy-loaded type generator."""
        if self._type_generator is None:
            from ...generators.types import TypeGenerator

            self._type_generator = TypeGenerator(schema_name=self.schema_name)
        return self._type_generator

    @property
    def query_generator(self):
        """Lazy-loaded query generator."""
        if self._query_generator is None:
            from ...generators.queries import QueryGenerator

            self._query_generator = QueryGenerator(
                self.type_generator,
                schema_name=self.schema_name,
            )
        return self._query_generator

    @property
    def mutation_generator(self):
        """Lazy-loaded mutation generator."""
        if self._mutation_generator is None:
            from ...config_proxy import get_mutation_generator_settings
            from ...generators.mutations import MutationGenerator

            mutation_settings = get_mutation_generator_settings(self.schema_name)
            self._mutation_generator = MutationGenerator(
                self.type_generator,
                settings=mutation_settings,
                schema_name=self.schema_name,
            )
        return self._mutation_generator

    @property
    def subscription_generator(self):
        """Lazy-loaded subscription generator."""
        if self._subscription_generator is None:
            from ...config_proxy import get_subscription_generator_settings
            from ...generators.subscriptions import SubscriptionGenerator

            subscription_settings = get_subscription_generator_settings(
                self.schema_name
            )
            self._subscription_generator = SubscriptionGenerator(
                self.type_generator,
                settings=subscription_settings,
                schema_name=self.schema_name,
            )
        return self._subscription_generator

    def _get_schema_setting(self, key: str, default: Any = None) -> Any:
        """
        Extract a setting from the settings object or raw settings.

        Args:
            key: Setting key to extract
            default: Default value if key is not found

        Returns:
            Setting value or default
        """
        # First try to get from the settings object
        if hasattr(self.settings, key):
            return getattr(self.settings, key)

        # Fallback to raw settings for backward compatibility
        return self._raw_settings.get(key, default)

    def _connect_signals(self) -> None:
        """Connects Django signals for automatic schema rebuilding."""
        # Only rebuild after migrations if enabled in schema settings
        if self._get_schema_setting("auto_refresh_on_migration", True):
            post_migrate.connect(self._handle_post_migrate)
        if self._get_schema_setting("auto_refresh_on_model_change", False):
            post_save.connect(self._handle_model_change)
            post_delete.connect(self._handle_model_change)

    def _handle_post_migrate(self, sender, **kwargs) -> None:
        """Handles post-migrate signal to rebuild schema after migrations."""
        logger.info(f"Rebuilding schema '{self.schema_name}' after database migration")
        self.rebuild_schema()

    def _handle_model_change(self, sender, **kwargs) -> None:
        """Handles model change signals to update schema when necessary."""
        if sender in self._registered_models:
            logger.info(
                f"Model {sender.__name__} changed, updating schema '{self.schema_name}'"
            )
            self.rebuild_schema()

    def _is_valid_model(self, model: type[models.Model]) -> bool:
        """
        Checks if a model should be included in the schema.

        Args:
            model: Django model class to validate

        Returns:
            bool: True if model should be included in schema
        """
        if model._meta.abstract:
            return False

        app_label = model._meta.app_label
        model_name = model.__name__
        model_label = model._meta.model_name

        if app_label in _SYSTEM_EXCLUDED_APPS:
            logger.debug(
                "Excluding model %s from app %s (system app excluded)",
                model_name,
                app_label,
            )
            return False

        if model_label in _SYSTEM_EXCLUDED_MODEL_NAMES:
            logger.debug("Excluding model %s (system model excluded)", model_name)
            return False

        # Check app exclusions from schema_settings
        excluded_apps = self._get_schema_setting("excluded_apps", [])

        if app_label in excluded_apps:
            logger.debug(
                f"Excluding model {model_name} from app {app_label} (app excluded)"
            )
            return False

        # Check model exclusions from schema_settings
        excluded_models = self._get_schema_setting("excluded_models", [])

        # Check model name exclusions
        if model_name in excluded_models:
            logger.debug(f"Excluding model {model_name} (model name excluded)")
            return False

        # Check app.model exclusions
        full_model_name = f"{app_label}.{model_name}"
        if full_model_name in excluded_models:
            logger.debug(
                f"Excluding model {full_model_name} (full model name excluded)"
            )
            return False

        # Ignore Django Simple History generated models (Historical*).
        try:
            model_module = getattr(model, "__module__", "")
            if (
                model.__name__.startswith("Historical")
                or "simple_history" in model_module
            ):
                logger.debug(
                    f"Excluding historical model {full_model_name} (Simple History)"
                )
                return False
        except Exception:
            pass

        return True

    def _discover_models(self) -> list[type[models.Model]]:
        """
        Discovers all Django models that should be included in the schema.

        Returns:
            List[Type[models.Model]]: List of valid Django models
        """
        # If registry is available and provides explicit models, use registry discovery.
        if self.registry:
            try:
                schema_info = self.registry.get_schema(self.schema_name)
                registry_models = self.registry.get_models_for_schema(self.schema_name)
                if registry_models:
                    registry_models = [
                        model
                        for model in registry_models
                        if self._is_valid_model(model)
                    ]
                    logger.debug(
                        f"Using registry model discovery for schema '{self.schema_name}': "
                        f"{[m.__name__ for m in registry_models]}"
                    )
                    return registry_models
                if schema_info and not schema_info.auto_discover:
                    logger.debug(
                        "Registry returned no models for schema '%s' with auto_discover disabled",
                        self.schema_name,
                    )
                    return []
            except Exception as e:
                logger.warning(
                    f"Failed to get models from registry for schema '{self.schema_name}': {e}"
                )

        # Fallback to default model discovery
        discovered_models = []
        excluded_apps = self._get_schema_setting("excluded_apps", [])

        for app_config in apps.get_app_configs():
            # Skip excluded apps at the app level for efficiency
            if app_config.label in excluded_apps:
                logger.debug(
                    f"Skipping entire app {app_config.label} (excluded in schema_settings)"
                )
                continue

            for model in app_config.get_models():
                if self._is_valid_model(model):
                    discovered_models.append(model)

        return discovered_models

    def get_schema(
        self, model_list: Optional[list[type[models.Model]]] = None
    ) -> graphene.Schema:
        """
        Returns the current GraphQL schema, rebuilding if necessary.

        Args:
            model_list: Optional list of models to include in schema

        Returns:
            graphene.Schema: The current GraphQL schema
        """
        self._refresh_settings_if_needed()
        if model_list is not None:
            valid_models = [
                model for model in model_list if self._is_valid_model(model)
            ]
            original_discover = self._discover_models
            self._discover_models = lambda: valid_models
            try:
                self.rebuild_schema()
            finally:
                self._discover_models = original_discover
            return self._schema

        if self._schema is None:
            self.rebuild_schema()
        return self._schema

    def get_schema_version(self) -> int:
        """
        Returns the current schema version number.

        Returns:
            int: Current schema version
        """
        return self._schema_version

    def get_middleware(self) -> list:
        """
        Returns the middleware list for this schema.

        Returns:
            List: List of middleware instances
        """
        return getattr(self, "_middleware", [])

    def clear_schema(self) -> None:
        """Clears the current schema, forcing a rebuild on next access."""
        with self._lock:
            self._schema = None
            self._query_fields.clear()
            self._mutation_fields.clear()
            self._subscription_fields.clear()
            self._registered_models.clear()
            logger.info(f"Schema '{self.schema_name}' cleared")

    def get_registered_models(self) -> set[type[models.Model]]:
        """
        Returns the set of registered models for this schema.

        Returns:
            Set[Type[models.Model]]: Set of registered Django models
        """
        return self._registered_models.copy()

    def get_query_fields(self) -> dict[str, Union[graphene.Field, graphene.List]]:
        """
        Returns the current query fields for this schema.

        Returns:
            Dict[str, Union[graphene.Field, graphene.List]]: Query fields dictionary
        """
        return self._query_fields.copy()

    def get_mutation_fields(self) -> dict[str, type[graphene.Mutation]]:
        """
        Returns the current mutation fields for this schema.

        Returns:
            Dict[str, Type[graphene.Mutation]]: Mutation fields dictionary
        """
        return self._mutation_fields.copy()

    def get_settings(self) -> Any:
        """
        Returns the schema settings for this schema.

        Returns:
            Any: Schema settings instance
        """
        return self.settings

"""
SchemaRegistry implementation.
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set, Type

from django.apps import apps
from django.conf import settings as django_settings
from django.db import models

from .info import SchemaInfo

logger = logging.getLogger(__name__)


class SchemaRegistry:
    """
    Central registry for managing multiple GraphQL schemas.
    """

    def __init__(self):
        self._schemas: dict[str, SchemaInfo] = {}
        self._schema_builders: dict[str, Any] = {}
        self._schema_instance_cache: dict[str, dict[str, Any]] = {}
        self._discovery_hooks: list[Callable] = []
        self._lock = threading.Lock()
        self._initialized = False
        self._pre_registration_hooks: list[Callable] = []
        self._post_registration_hooks: list[Callable] = []

    def _apply_graphiql_defaults(
        self, schema_name: str, settings_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply debug-gated defaults for the graphiql schema if not explicitly set."""
        if schema_name != "graphiql":
            return settings_payload

        debug_enabled = getattr(django_settings, "DEBUG", False)
        schema_settings = settings_payload.get("schema_settings")
        if isinstance(schema_settings, dict):
            schema_settings = dict(schema_settings)
        else:
            schema_settings = {}

        payload_keys = {str(key).upper() for key in settings_payload}

        if (
            "enable_graphiql" not in schema_settings
            and "enable_graphiql" not in settings_payload
            and "ENABLE_GRAPHIQL" not in payload_keys
        ):
            schema_settings["enable_graphiql"] = debug_enabled
        if (
            "enable_introspection" not in schema_settings
            and "enable_introspection" not in settings_payload
            and "ENABLE_INTROSPECTION" not in payload_keys
        ):
            schema_settings["enable_introspection"] = debug_enabled
        if (
            "authentication_required" not in schema_settings
            and "authentication_required" not in settings_payload
            and "AUTHENTICATION_REQUIRED" not in payload_keys
        ):
            schema_settings["authentication_required"] = not debug_enabled

        settings_payload = dict(settings_payload)
        settings_payload["schema_settings"] = schema_settings
        return settings_payload

    def register_schema(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        apps: Optional[list[str]] = None,
        models: Optional[list[str]] = None,
        exclude_models: Optional[list[str]] = None,
        settings: Optional[dict[str, Any]] = None,
        schema_class: Optional[type] = None,
        auto_discover: bool = True,
        enabled: bool = True,
    ) -> SchemaInfo:
        """Register a new GraphQL schema."""
        kwargs = {
            "description": description,
            "version": version,
            "apps": apps,
            "models": models,
            "exclude_models": exclude_models,
            "settings": settings,
            "schema_class": schema_class,
            "auto_discover": auto_discover,
            "enabled": enabled,
        }
        modified_kwargs = self._run_pre_registration_hooks(name, **kwargs)
        settings_payload = modified_kwargs.get("settings", settings) or {}
        if not isinstance(settings_payload, dict):
            settings_payload = {}
        settings_payload = self._apply_graphiql_defaults(name, settings_payload)
        modified_kwargs["settings"] = settings_payload

        with self._lock:
            if name in self._schemas:
                logger.info("Schema '%s' already registered, updating...", name)

            schema_info = SchemaInfo(
                name=name,
                description=modified_kwargs.get("description", description),
                version=modified_kwargs.get("version", version),
                apps=modified_kwargs.get("apps", apps) or [],
                models=modified_kwargs.get("models", models) or [],
                exclude_models=modified_kwargs.get("exclude_models", exclude_models)
                or [],
                settings=modified_kwargs.get("settings", settings) or {},
                schema_class=modified_kwargs.get("schema_class", schema_class),
                auto_discover=modified_kwargs.get("auto_discover", auto_discover),
                enabled=modified_kwargs.get("enabled", enabled),
            )
            self._schemas[name] = schema_info

            schema_settings = modified_kwargs.get("settings", settings) or {}
            if schema_settings:
                from ...config_proxy import configure_schema_settings
                configure_schema_settings(name, **schema_settings)

            logger.info(f"Registered schema: {name}")
            self._run_post_registration_hooks(schema_info)
            return schema_info

    def unregister_schema(self, name: str) -> bool:
        """Unregister a schema."""
        with self._lock:
            if name in self._schemas:
                del self._schemas[name]
                if name in self._schema_builders:
                    del self._schema_builders[name]
                if name in self._schema_instance_cache:
                    del self._schema_instance_cache[name]
                logger.info(f"Unregistered schema: {name}")
                return True
            return False

    def get_schema(self, name: str) -> Optional[SchemaInfo]:
        """Get schema information by name."""
        return self._schemas.get(name)

    def list_schemas(self, enabled_only: bool = False) -> list[SchemaInfo]:
        """List all registered schemas."""
        schemas = list(self._schemas.values())
        if enabled_only:
            schemas = [s for s in schemas if s.enabled]
        return schemas

    def get_schema_names(self, enabled_only: bool = False) -> list[str]:
        """Get list of schema names."""
        return [s.name for s in self.list_schemas(enabled_only)]

    def enable_schema(self, name: str) -> bool:
        """Enable a schema."""
        schema = self.get_schema(name)
        if schema:
            schema.enabled = True
            logger.info(f"Enabled schema: {name}")
            return True
        return False

    def disable_schema(self, name: str) -> bool:
        """Disable a schema."""
        schema = self.get_schema(name)
        if schema:
            schema.enabled = False
            logger.info(f"Disabled schema: {name}")
            return True
        return False

    def schema_exists(self, name: str) -> bool:
        """Check if a schema exists in the registry."""
        return name in self._schemas

    def clear(self) -> None:
        """Clear all schemas from the registry."""
        with self._lock:
            self._schemas.clear()
            self._schema_builders.clear()
            self._schema_instance_cache.clear()
            self._initialized = False
            logger.info("Cleared all schemas from registry")

    def get_models_for_schema(self, name: str) -> list[type[models.Model]]:
        """Get Django models for a specific schema."""
        schema_info = self.get_schema(name)
        if not schema_info:
            return []

        models_list = []
        for app_name in schema_info.apps:
            try:
                app_models = apps.get_app_config(app_name).get_models()
                models_list.extend(app_models)
            except LookupError:
                logger.warning(f"App '{app_name}' not found for schema '{name}'")

        if schema_info.models:
            model_names = set()
            for model_spec in schema_info.models:
                if "." in model_spec:
                    app_label, model_name = model_spec.split(".", 1)
                    model_names.add(model_name.lower())
                else:
                    model_names.add(model_spec.lower())
            models_list = [m for m in models_list if m._meta.model_name.lower() in model_names]

        if schema_info.exclude_models:
            exclude_names = set()
            for model_spec in schema_info.exclude_models:
                if "." in model_spec:
                    app_label, model_name = model_spec.split(".", 1)
                    exclude_names.add(model_name.lower())
                else:
                    exclude_names.add(model_spec.lower())
            models_list = [m for m in models_list if m._meta.model_name.lower() not in exclude_names]

        return models_list

    def validate_schema(self, name: str) -> dict[str, Any]:
        """Validate a schema configuration."""
        schema_info = self.get_schema(name)
        if not schema_info:
            return {"valid": False, "errors": [f"Schema '{name}' not found"]}

        errors = []
        warnings = []
        for app_name in schema_info.apps:
            try:
                apps.get_app_config(app_name)
            except LookupError:
                errors.append(f"App '{app_name}' not found")

        models_list = self.get_models_for_schema(name)
        if not models_list and schema_info.apps:
            warnings.append(f"No models found for schema '{name}'")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "model_count": len(models_list),
        }

    def _run_pre_registration_hooks(self, name: str, **kwargs) -> dict[str, Any]:
        modified_kwargs = kwargs.copy()
        for hook in self._pre_registration_hooks:
            try:
                result = hook(self, name, **modified_kwargs)
                if isinstance(result, dict):
                    modified_kwargs.update(result)
            except Exception as e:
                logger.error(f"Error in pre-registration hook for schema '{name}': {e}")
        return modified_kwargs

    def _run_post_registration_hooks(self, schema_info: SchemaInfo) -> None:
        for hook in self._post_registration_hooks:
            try:
                hook(self, schema_info)
            except Exception as e:
                logger.error(f"Error in post-registration hook for schema '{schema_info.name}': {e}")

    def add_pre_registration_hook(self, hook: Callable) -> None:
        self._pre_registration_hooks.append(hook)

    def add_post_registration_hook(self, hook: Callable) -> None:
        self._post_registration_hooks.append(hook)

    def discover_schemas(self) -> None:
        from .discovery import discover_schemas
        return discover_schemas(self)

    def auto_discover_schemas(self) -> int:
        from .discovery import auto_discover_schemas
        return auto_discover_schemas(self)

    def get_schema_builder(self, name: str):
        from .builders import get_schema_builder
        return get_schema_builder(self, name)

    def get_schema_instance(self, name: str):
        from .builders import get_schema_instance
        return get_schema_instance(self, name)

    def add_discovery_hook(self, hook: Callable) -> None:
        self._discovery_hooks.append(hook)

    def remove_discovery_hook(self, hook: Callable) -> bool:
        try:
            self._discovery_hooks.remove(hook)
            return True
        except ValueError:
            return False

"""
Discovery logic for SchemaRegistry.
"""

import logging
from typing import Any, Callable, Optional

from django.apps import apps
from django.conf import settings as django_settings
from django.db.utils import OperationalError, ProgrammingError
from django.utils.module_loading import import_string

from .registry import SchemaRegistry

logger = logging.getLogger(__name__)


def discover_schemas(registry: SchemaRegistry) -> None:
    """Automatically discover schemas from Django apps."""
    if registry._initialized:
        return

    logger.info("Starting schema discovery...")
    for app_config in apps.get_app_configs():
        _discover_app_schemas(registry, app_config)

    for hook in registry._discovery_hooks:
        try:
            hook(registry)
        except Exception as e:
            logger.error(f"Error running discovery hook: {e}")

    _register_schemas_from_settings(registry)
    _register_schemas_from_database(registry)

    registry._initialized = True
    logger.info(f"Schema discovery completed. Found {len(registry._schemas)} schemas.")


def auto_discover_schemas(registry: SchemaRegistry) -> int:
    """Automatically discover and register schemas from Django apps."""
    initial_count = len(registry._schemas)
    logger.info("Starting automatic schema discovery...")
    for app_config in apps.get_app_configs():
        _discover_app_schemas(registry, app_config)
    discovered_count = len(registry._schemas) - initial_count
    logger.info(f"Auto-discovery completed. Discovered {discovered_count} new schemas.")
    return discovered_count


def _discover_app_schemas(registry: SchemaRegistry, app_config) -> None:
    app_name = app_config.name
    schema_modules = [
        f"{app_name}.schemas",
        f"{app_name}.graphql_schema",
        f"{app_name}.schema",
        f"{app_name}.graphql.schema",
    ]
    for module_path in schema_modules:
        try:
            module = import_string(module_path)
            if hasattr(module, "SCHEMA_CONFIG"):
                _register_from_config(registry, app_name, module.SCHEMA_CONFIG)
            if hasattr(module, "register_schema"):
                module.register_schema(registry)
            logger.debug(f"Discovered schema configuration in {module_path}")
            break
        except (ImportError, AttributeError):
            continue


def _register_from_config(registry: SchemaRegistry, app_name: str, config: dict[str, Any]) -> None:
    schema_name = config.get("name", f"{app_name}_schema")
    registry.register_schema(
        name=schema_name,
        description=config.get("description", f"Auto-discovered schema for {app_name}"),
        version=config.get("version", "1.0.0"),
        apps=config.get("apps", [app_name]),
        models=config.get("models", []),
        exclude_models=config.get("exclude_models", []),
        settings=config.get("settings", {}),
        auto_discover=config.get("auto_discover", True),
        enabled=config.get("enabled", True),
    )


def _register_schemas_from_database(registry: SchemaRegistry) -> int:
    try:
        schema_model = apps.get_model("rail_django", "SchemaRegistryModel")
    except LookupError:
        return 0
    try:
        entries = schema_model.objects.all()
    except (OperationalError, ProgrammingError) as exc:
        logger.debug("Skipping database schema registry: %s", exc)
        return 0
    registered = 0
    for entry in entries:
        try:
            config = entry.to_registry_kwargs()
            if not config.get("name"):
                continue
            schema_info = registry.register_schema(**config)
            if schema_info:
                schema_info.created_at = (entry.created_at.isoformat() if entry.created_at else None)
                schema_info.updated_at = (entry.updated_at.isoformat() if entry.updated_at else None)
            registered += 1
        except Exception as exc:
            logger.warning("Failed to register schema '%s' from database: %s", getattr(entry, "name", "<unknown>"), exc)
    return registered


def _register_schemas_from_settings(registry: SchemaRegistry) -> int:
    schema_configs = getattr(django_settings, "RAIL_DJANGO_GRAPHQL_SCHEMAS", None)
    if not isinstance(schema_configs, dict):
        return 0
    registered = 0
    for schema_name, config in schema_configs.items():
        if not isinstance(schema_name, str) or not schema_name:
            continue
        if registry.schema_exists(schema_name):
            continue
        config_dict = config if isinstance(config, dict) else {}
        try:
            registry.register_schema(
                name=schema_name,
                description=config_dict.get("description", f"{schema_name} schema"),
                version=config_dict.get("version", "1.0.0"),
                apps=config_dict.get("apps"),
                models=config_dict.get("models"),
                exclude_models=config_dict.get("exclude_models"),
                settings=config_dict,
                schema_class=config_dict.get("schema_class"),
                auto_discover=config_dict.get("auto_discover", True),
                enabled=config_dict.get("enabled", True),
            )
            registered += 1
        except Exception as e:
            logger.warning(f"Failed to register schema '{schema_name}' from settings: {e}")
    return registered


def add_discovery_hook(registry: SchemaRegistry, hook: Callable) -> None:
    registry._discovery_hooks.append(hook)


def remove_discovery_hook(registry: SchemaRegistry, hook: Callable) -> bool:
    try:
        registry._discovery_hooks.remove(hook)
        return True
    except ValueError:
        return False

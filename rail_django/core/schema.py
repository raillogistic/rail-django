"""
Schema Builder System for rail-django library

This module provides the SchemaBuilder class, which is responsible for assembling
the unified GraphQL schema from all registered Django apps and models.
"""

import importlib
import inspect
import itertools
import logging
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Type, Union

import graphene
from django.apps import apps
from django.db import models
from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver
from graphene_django.debug import DjangoDebug

logger = logging.getLogger(__name__)

_GRAPHQL_NAME_INVALID_RE = re.compile(r"[^_0-9A-Za-z]")


class SchemaBuilder:
    """
    Builds and manages the unified GraphQL schema, combining queries and mutations
    from all registered Django apps and models.

    This class supports:
    - Multiple schema configurations
    - Schema-specific settings
    - Automatic model discovery
    - Dynamic schema rebuilding
    - Integration with the schema registry
    """

    _instances: Dict[str, "SchemaBuilder"] = {}
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
                from ..config_proxy import get_core_schema_settings
                from .settings import SchemaSettings

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
                from .settings import SchemaSettings

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

        # Schema state
        self._schema = None
        self._query_fields: Dict[str, Union[graphene.Field, graphene.List]] = {}
        self._mutation_fields: Dict[str, Type[graphene.Mutation]] = {}
        self._registered_models: Set[Type[models.Model]] = set()
        self._schema_version = 0

        self._initialized = True
        self._connect_signals()

    def _refresh_settings_if_needed(self) -> None:
        if self._settings_locked:
            return
        try:
            from ..config_proxy import get_core_schema_settings
            from .settings import SchemaSettings

            settings_dict = get_core_schema_settings(self.schema_name) or {}
        except ImportError:
            return

        if settings_dict != (self._raw_settings or {}):
            self.settings = SchemaSettings(**settings_dict) if settings_dict else SchemaSettings()
            self._raw_settings = settings_dict or {}
            self._schema = None

    @property
    def type_generator(self):
        """Lazy-loaded type generator."""
        if self._type_generator is None:
            from ..generators.types import TypeGenerator

            self._type_generator = TypeGenerator(schema_name=self.schema_name)
        return self._type_generator

    @property
    def query_generator(self):
        """Lazy-loaded query generator."""
        if self._query_generator is None:
            from ..generators.queries import QueryGenerator

            self._query_generator = QueryGenerator(
                self.type_generator,
                schema_name=self.schema_name,
            )
        return self._query_generator

    @property
    def mutation_generator(self):
        """Lazy-loaded mutation generator."""
        if self._mutation_generator is None:
            from ..config_proxy import get_mutation_generator_settings
            from ..generators.mutations import MutationGenerator

            mutation_settings = get_mutation_generator_settings(self.schema_name)
            self._mutation_generator = MutationGenerator(
                self.type_generator,
                settings=mutation_settings,
                schema_name=self.schema_name,
            )
        return self._mutation_generator

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

    def _get_list_alias(self, model: Type[models.Model]) -> Optional[str]:
        plural = getattr(model._meta, "verbose_name_plural", None)
        if not plural:
            return None
        alias = str(plural).strip()
        if not alias:
            return None
        alias = unicodedata.normalize("NFKD", alias)
        alias = alias.encode("ascii", "ignore").decode("ascii")
        alias = alias.replace(" ", "_").replace("-", "_")
        alias = _GRAPHQL_NAME_INVALID_RE.sub("", alias).strip("_").lower()
        if not alias:
            return None
        return f"all_{alias}"

    def _connect_signals(self) -> None:
        """
        Connects Django signals for automatic schema rebuilding.
        """
        # Only rebuild after migrations if enabled in schema settings
        if self._get_schema_setting("auto_refresh_on_migration", True):
            post_migrate.connect(self._handle_post_migrate)
        if self._get_schema_setting("auto_refresh_on_model_change", False):
            post_save.connect(self._handle_model_change)
            post_delete.connect(self._handle_model_change)

    def _handle_post_migrate(self, sender, **kwargs) -> None:
        """
        Handles post-migrate signal to rebuild schema after migrations.
        """
        logger.info(f"Rebuilding schema '{self.schema_name}' after database migration")
        self.rebuild_schema()

    def _handle_model_change(self, sender, **kwargs) -> None:
        """
        Handles model change signals to update schema when necessary.
        """
        if sender in self._registered_models:
            logger.info(
                f"Model {sender.__name__} changed, updating schema '{self.schema_name}'"
            )
            self.rebuild_schema()

    def _is_valid_model(self, model: Type[models.Model]) -> bool:
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
        # These models are used for audit/history tracking and should not be exposed in the API.
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
            # Fail-safe: if any attribute access fails, do not exclude based on history
            pass

        return True

    def _discover_models(self) -> List[Type[models.Model]]:
        """
        Discovers all Django models that should be included in the schema.

        Returns:
            List[Type[models.Model]]: List of valid Django models
        """
        # If registry is available and schema is registered, use registry's model discovery
        if self.registry and self.schema_name != "default":
            try:
                registry_models = self.registry.get_models_for_schema(self.schema_name)
                if registry_models:
                    logger.debug(
                        f"Using registry model discovery for schema '{self.schema_name}': {[m.__name__ for m in registry_models]}"
                    )
                    return registry_models
            except Exception as e:
                logger.warning(
                    f"Failed to get models from registry for schema '{self.schema_name}': {e}"
                )

        # Fallback to default model discovery
        models = []
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
                    models.append(model)

        return models

    def _generate_query_fields(self, models: List[Type[models.Model]]) -> None:
        """
        Generates query fields for all discovered models.
        Now supports multiple managers per model with custom naming conventions.

        Args:
            models: List of Django models to generate queries for
        """
        self._query_fields = {
            "dummy": graphene.String(
                description="Dummy query field to ensure schema validity"
            )
        }

        for model in models:
            model_name = model.__name__.lower()
            # skip HistoricalModel
            # if model_name.startswith("historical"):
            #     continue
            # Get model managers using introspector
            from ..generators.introspector import ModelIntrospector

            introspector = ModelIntrospector(model)
            managers = introspector.get_model_managers()

            # Generate queries for each manager
            for manager_name, manager_info in managers.items():
                is_history_manager = self.query_generator.is_history_related_manager(
                    model, manager_name
                )
                history_result_model = None
                if is_history_manager:
                    history_result_model = (
                        self.query_generator.get_manager_queryset_model(
                            model, manager_name
                        )
                        or model
                    )

                if is_history_manager and not self.settings.enable_pagination:
                    logger.debug(
                        "Skipping manager %s for %s because pagination is disabled",
                        manager_name,
                        model.__name__,
                    )
                    continue

                if manager_info.is_default:
                    # Default manager keeps standard naming
                    # Single and list queries are not exposed for history managers
                    if not is_history_manager:
                        # Single object query
                        single_query = self.query_generator.generate_single_query(
                            model, manager_name
                        )

                        self._query_fields[model_name] = single_query

                        # List query
                        list_query = self.query_generator.generate_list_query(
                            model, manager_name
                        )
                        self._query_fields[f"{model_name}s"] = list_query
                        alias_name = self._get_list_alias(model)
                        if alias_name and alias_name not in self._query_fields:
                            self._query_fields[alias_name] = list_query

                        grouping_query = self.query_generator.generate_grouping_query(
                            model, manager_name
                        )
                        self._query_fields[f"{model_name}s_groups"] = grouping_query

                    # Paginated query
                    if self.settings.enable_pagination:
                        paginated_query = self.query_generator.generate_paginated_query(
                            model,
                            manager_name,
                            result_model=history_result_model,
                            operation_name="history"
                            if is_history_manager
                            else "paginated",
                        )
                        self._query_fields[f"{model_name}s_pages"] = paginated_query
                else:
                    # Custom managers use new naming convention
                    # Single object query: modelname__custommanager
                    if not is_history_manager:
                        single_query = self.query_generator.generate_single_query(
                            model, manager_name
                        )
                        self._query_fields[f"{model_name}__{manager_name}"] = (
                            single_query
                        )

                        # List query: modelname__custommanager (plural form)
                        list_query = self.query_generator.generate_list_query(
                            model, manager_name
                        )
                        self._query_fields[f"{model_name}s__{manager_name}"] = (
                            list_query
                        )
                        grouping_query = self.query_generator.generate_grouping_query(
                            model, manager_name
                        )
                        self._query_fields[f"{model_name}s_groups_{manager_name}"] = (
                            grouping_query
                        )

                    # Paginated query: modelname_pages_custommanager
                    if self.settings.enable_pagination:
                        paginated_query = self.query_generator.generate_paginated_query(
                            model,
                            manager_name,
                            result_model=history_result_model,
                            operation_name="history"
                            if is_history_manager
                            else "paginated",
                        )
                        self._query_fields[f"{model_name}s_pages_{manager_name}"] = (
                            paginated_query
                        )

    def _generate_mutation_fields(self, models: List[Type[models.Model]]) -> None:
        """
        Generates mutation fields for all discovered models.

        Args:
            models: List of Django models to generate mutations for
        """
        self._mutation_fields = {}

        for model in models:
            mutations = self.mutation_generator.generate_all_mutations(model)
            logger.debug(
                f"Generated {len(mutations)} mutations for model {model.__name__}: {list(mutations.keys())}"
            )
            self._mutation_fields.update(mutations)

        logger.info(
            f"Total mutations generated for schema '{self.schema_name}': {len(self._mutation_fields)}"
        )
        logger.debug(f"Mutation fields: {list(self._mutation_fields.keys())}")

    def _load_query_extensions(self) -> List[Type[graphene.ObjectType]]:
        """
        Load custom query extensions defined in schema settings.
        """
        extension_paths = self._get_schema_setting("query_extensions", [])
        loaded = []
        for path in extension_paths or []:
            if not isinstance(path, str) or not path.strip():
                continue
            try:
                module_path, class_name = path.rsplit(".", 1)
            except ValueError:
                logger.warning(
                    f"Invalid query extension path '{path}' configured for schema '{self.schema_name}'"
                )
                continue
            try:
                module = importlib.import_module(module_path)
                query_class = getattr(module, class_name)
                loaded.append(query_class)
            except Exception as e:
                logger.warning(
                    f"Could not import query extension '{path}' for schema '{self.schema_name}': {e}"
                )
        return loaded

    def _attach_query_class_fields(
        self, query_attrs: Dict[str, Any], query_class: Type[graphene.ObjectType]
    ) -> None:
        """
        Merge fields from a custom query class into the root query attributes.
        """
        query_instance = query_class()

        for field_name, field in query_class._meta.fields.items():
            resolver_method_name = f"resolve_{field_name}"
            if hasattr(query_instance, resolver_method_name):
                resolver_method = getattr(query_instance, resolver_method_name)

                def create_resolver_wrapper(method):
                    def wrapper(root, info, **kwargs):
                        return method(info, **kwargs)

                    return wrapper

                query_attrs[field_name] = graphene.Field(
                    field.type,
                    description=field.description,
                    resolver=create_resolver_wrapper(resolver_method),
                    args=getattr(field, "args", None),
                )
            else:
                query_attrs[field_name] = field

    def _apply_field_allowlist(
        self, fields: Dict[str, Any], allowlist: Optional[List[str]]
    ) -> Dict[str, Any]:
        """Filter root fields using an allowlist when configured."""
        if allowlist is None:
            return fields

        if isinstance(allowlist, (list, tuple, set)):
            allowed = {str(name).strip() for name in allowlist if str(name).strip()}
        else:
            allowed = {str(allowlist).strip()} if allowlist else set()

        if not allowed:
            return {}

        filtered = {}
        for key, field in fields.items():
            field_names = {key}
            alias = getattr(field, "name", None)
            if alias:
                field_names.add(alias)
            if field_names & allowed:
                filtered[key] = field
        return filtered

    def rebuild_schema(self) -> None:
        """
        Rebuilds the entire GraphQL schema.

        This method:
        1. Discovers all valid Django models
        2. Generates query and mutation fields
        3. Integrates security extensions
        4. Creates the final GraphQL schema
        5. Registers the schema in the registry
        """
        with self._lock:
            try:
                # Clear existing schema
                self._schema = None
                self._query_fields = {}
                self._mutation_fields = {}

                # Discover models
                models = self._discover_models()
                self._registered_models = set(models)
                logger.info(
                    f"Discovered {len(models)} models for schema '{self.schema_name}': {[m.__name__ for m in models]}"
                )

                # Generate queries
                self._generate_query_fields(models)

                # Generate mutations
                self._generate_mutation_fields(models)

                logger.info(
                    f"Schema '{self.schema_name}' generation - Query fields: {len(self._query_fields)}, Mutation fields: {len(self._mutation_fields)}"
                )

                # Create Query type with security extensions
                query_attrs = {"debug": graphene.Field(DjangoDebug, name="_debug")}
                query_attrs.update(self._query_fields)

                custom_query_classes = self._load_query_extensions()
                for query_class in custom_query_classes:
                    self._attach_query_class_fields(query_attrs, query_class)
                if custom_query_classes:
                    logger.info(
                        f"Custom query extensions integrated into schema '{self.schema_name}': {[cls.__name__ for cls in custom_query_classes]}"
                    )

                # Add security-related queries with proper resolver binding
                # Import each extension class individually to avoid a single missing module
                # preventing all security queries from being integrated.
                security_query_classes = []
                try:
                    from ..extensions.auth import MeQuery

                    security_query_classes.append(MeQuery)
                except ImportError as e:
                    logger.warning(
                        f"Could not import MeQuery for schema '{self.schema_name}': {e}"
                    )

                try:
                    from ..extensions.permissions import PermissionQuery

                    security_query_classes.append(PermissionQuery)
                except ImportError as e:
                    logger.warning(
                        f"Could not import PermissionQuery for schema '{self.schema_name}': {e}"
                    )

                try:
                    from ..extensions.validation import ValidationQuery

                    security_query_classes.append(ValidationQuery)
                except ImportError as e:
                    logger.warning(
                        f"Could not import ValidationQuery for schema '{self.schema_name}': {e}"
                    )

                # rate_limiting is optional; include if present
                try:
                    from ..extensions.rate_limiting import SecurityQuery

                    security_query_classes.append(SecurityQuery)
                except ImportError as e:
                    logger.info(
                        f"Rate limiting SecurityQuery not available for schema '{self.schema_name}': {e}"
                    )

                # Merge security queries and bind their resolvers to the root Query
                for query_class in security_query_classes:
                    # Create an instance to access bound resolver methods
                    query_instance = query_class()

                    for field_name, field in query_class._meta.fields.items():
                        resolver_method_name = f"resolve_{field_name}"
                        if hasattr(query_instance, resolver_method_name):
                            resolver_method = getattr(
                                query_instance, resolver_method_name
                            )

                            # Create a wrapper that adapts (root, info, **kwargs) to (info, **kwargs)
                            def create_resolver_wrapper(method):
                                def wrapper(root, info, **kwargs):
                                    return method(info, **kwargs)

                                return wrapper

                            # Recreate the field on the root Query with the bound resolver
                            query_attrs[field_name] = graphene.Field(
                                field.type,
                                description=field.description,
                                resolver=create_resolver_wrapper(resolver_method),
                                args=getattr(field, "args", None),
                            )
                        else:
                            # Fallback: copy field if no resolver method is defined
                            query_attrs[field_name] = field

                if security_query_classes:
                    logger.info(
                        f"Security extensions integrated into schema '{self.schema_name}' with resolver binding"
                    )

                # Add health monitoring queries
                try:
                    from ..extensions.health import HealthQuery

                    # Create an instance of HealthQuery to get bound methods
                    health_query_instance = HealthQuery()

                    # Merge health queries with proper resolver binding
                    for field_name, field in HealthQuery._meta.fields.items():
                        # Get the resolver method from the instance
                        resolver_method_name = f"resolve_{field_name}"
                        if hasattr(health_query_instance, resolver_method_name):
                            resolver_method = getattr(
                                health_query_instance, resolver_method_name
                            )

                            # Create a wrapper that handles the root parameter
                            def create_resolver_wrapper(method):
                                def wrapper(root, info, **kwargs):
                                    return method(info, **kwargs)

                                return wrapper

                            # Create a new field with the wrapped resolver
                            query_attrs[field_name] = graphene.Field(
                                field.type,
                                description=field.description,
                                resolver=create_resolver_wrapper(resolver_method),
                                args=getattr(field, "args", None),
                            )
                        else:
                            query_attrs[field_name] = field

                    logger.info(
                        f"Health monitoring queries integrated into schema '{self.schema_name}'"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Could not import health queries for schema '{self.schema_name}': {e}"
                    )

                # Add model metadata queries
                if self.settings.show_metadata:
                    try:
                        from ..extensions.metadata import ModelMetadataQuery

                        # Create an instance of ModelMetadataQuery to get bound methods
                        metadata_query_instance = ModelMetadataQuery()
                        # Merge metadata queries with proper resolver binding
                        for (
                            field_name,
                            field,
                        ) in ModelMetadataQuery._meta.fields.items():
                            # Get the resolver method from the instance
                            resolver_method_name = f"resolve_{field_name}"
                            if hasattr(metadata_query_instance, resolver_method_name):
                                resolver_method = getattr(
                                    metadata_query_instance, resolver_method_name
                                )

                                # Create a wrapper that handles the root parameter
                                def create_resolver_wrapper(method):
                                    def wrapper(root, info, **kwargs):
                                        return method(info, **kwargs)

                                    return wrapper

                                # Create a new field with the wrapped resolver
                                query_attrs[field_name] = graphene.Field(
                                    field.type,
                                    description=field.description,
                                    resolver=create_resolver_wrapper(resolver_method),
                                    args=getattr(field, "args", None),
                                )
                            else:
                                query_attrs[field_name] = field

                        logger.info(
                            f"Model metadata queries integrated into schema '{self.schema_name}'"
                        )
                    except ImportError as e:
                        logger.warning(
                            f"Could not import metadata queries for schema '{self.schema_name}': {e}"
                        )

                query_allowlist = self._get_schema_setting(
                    "query_field_allowlist", None
                )
                if query_allowlist is not None:
                    query_attrs = self._apply_field_allowlist(
                        query_attrs, query_allowlist
                    )
                    if not query_attrs:
                        query_attrs = {
                            "dummy": graphene.String(
                                description="Dummy query field to ensure schema validity"
                            )
                        }

                query_type = type("Query", (graphene.ObjectType,), query_attrs)

                # Create Mutation type if there are mutations
                mutation_type = None
                logger.info(
                    f"Checking mutation fields for schema '{self.schema_name}': {len(self._mutation_fields)} mutations found"
                )
                #
                # Add security-related mutations
                security_mutations = {}
                try:
                    # Use hierarchical settings system to get disable_security_mutations
                    from ..config_proxy import get_setting
                    from ..extensions.auth import (
                        LoginMutation,
                        LogoutMutation,
                        RefreshTokenMutation,
                        RegisterMutation,
                        UpdateMySettingsMutation,
                    )

                    disable_security = self.settings.disable_security_mutations
                    # get_setting(
                    # "disable_security_mutations", False, self.schema_name
                    # )

                    if not disable_security:
                        security_mutations.update(
                            {
                                "login": LoginMutation.Field(),
                                "register": RegisterMutation.Field(),
                                "refresh_token": RefreshTokenMutation.Field(),
                                "logout": LogoutMutation.Field(),
                                "update_my_settings": UpdateMySettingsMutation.Field(),
                            }
                        )
                        logger.info(
                            f"Security mutations integrated into schema '{self.schema_name}'"
                        )
                except ImportError as e:
                    logger.warning(
                        f"Could not import security mutations for schema '{self.schema_name}': {e}"
                    )

                # Add health/maintenance mutations
                extension_mutations: Dict[str, Any] = {}
                if self._get_schema_setting("enable_extension_mutations", True):
                    try:
                        from ..extensions.health import RefreshSchemaMutation
                        from ..extensions.audit import LogFrontendAuditMutation

                        extension_mutations.update(
                            {
                                "refresh_schema": RefreshSchemaMutation.Field(),
                                "log_frontend_audit": LogFrontendAuditMutation.Field(),
                            }
                        )
                        logger.info(
                            f"Health extension mutations integrated into schema '{self.schema_name}'"
                        )
                    except ImportError as e:
                        logger.warning(
                            f"Could not import health extension mutations for schema '{self.schema_name}': {e}"
                        )

                # Load custom mutation extensions from settings
                mutation_extensions_path = self._get_schema_setting(
                    "mutation_extensions", []
                )
                for path in mutation_extensions_path or []:
                    if not isinstance(path, str) or not path.strip():
                        continue
                    try:
                        module_path, class_name = path.rsplit(".", 1)
                        module = importlib.import_module(module_path)
                        mutation_class = getattr(module, class_name)

                        # Iterate over fields of the ObjectType and add them to extension_mutations
                        for field_name, field in mutation_class._meta.fields.items():
                            extension_mutations[field_name] = field

                        logger.info(f"Loaded mutation extension: {path}")
                    except Exception as e:
                        logger.warning(
                            f"Could not import mutation extension '{path}' for schema '{self.schema_name}': {e}"
                        )

                # Combine all mutations
                all_mutations = {
                    **self._mutation_fields,
                    **security_mutations,
                    **extension_mutations,
                }

                mutation_allowlist = self._get_schema_setting(
                    "mutation_field_allowlist", None
                )
                if mutation_allowlist is not None:
                    all_mutations = self._apply_field_allowlist(
                        all_mutations, mutation_allowlist
                    )

                if all_mutations:
                    # logger.info(
                    #     f"Creating Mutation type for schema '{self.schema_name}' with fields: {list(all_mutations.keys())}"
                    # )
                    mutation_type = type(
                        "Mutation", (graphene.ObjectType,), all_mutations
                    )
                else:
                    if mutation_allowlist is not None:
                        logger.info(
                            f"No allowed mutations for schema '{self.schema_name}', skipping mutation type"
                        )
                        mutation_type = None
                    else:
                        logger.info(
                            f"No mutations found for schema '{self.schema_name}', creating dummy mutation"
                        )

                        # Create dummy mutation to avoid GraphQL error
                        class DummyMutation(graphene.Mutation):
                            class Arguments:
                                pass

                            success = graphene.Boolean()

                            def mutate(self, info):
                                return DummyMutation(success=True)

                        mutation_attrs = {
                            "dummy": DummyMutation.Field(
                                description="Placeholder mutation field"
                            )
                        }
                        mutation_type = type(
                            "Mutation", (graphene.ObjectType,), mutation_attrs
                        )

                # Create Schema with security middleware
                middleware = []
                try:
                    from ..extensions.rate_limiting import GraphQLSecurityMiddleware

                    middleware.append(GraphQLSecurityMiddleware())
                    logger.info(
                        f"Security middleware integrated into schema '{self.schema_name}'"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Could not import security middleware for schema '{self.schema_name}': {e}"
                    )

                # Note: Graphene Schema doesn't support middleware parameter directly
                # Middleware should be applied at the GraphQL execution level

                self._schema = graphene.Schema(
                    query=query_type,
                    mutation=mutation_type,
                    auto_camelcase=self.settings.auto_camelcase,
                )

                # Store middleware for later use in execution
                self._middleware = middleware

                # Increment schema version
                self._schema_version += 1

                # Register schema in the registry
                try:
                    from .registry import register_schema

                    register_schema(
                        name=self.schema_name,
                        description=f"Auto-generated GraphQL schema for {self.schema_name}",
                        version=str(self._schema_version),
                        models=list(self._registered_models),
                    )
                    logger.info(
                        f"Schema '{self.schema_name}' registered in schema registry"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Could not register schema '{self.schema_name}' in registry: {e}"
                    )

                logger.info(
                    f"Schema '{self.schema_name}' rebuilt successfully (version {self._schema_version})"
                    f"\n - Models: {len(models)}"
                    f"\n - Queries: {len(self._query_fields)}"
                    f"\n - Mutations: {len(self._mutation_fields)}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to rebuild schema '{self.schema_name}': {str(e)}",
                    exc_info=True,
                )
                raise

    def get_schema(
        self, model_list: Optional[List[Type[models.Model]]] = None
    ) -> graphene.Schema:
        """
        Returns the current GraphQL schema, rebuilding if necessary.

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

    def get_middleware(self) -> List:
        """
        Returns the middleware list for this schema.

        Returns:
            List: List of middleware instances
        """
        return getattr(self, "_middleware", [])

    def clear_schema(self) -> None:
        """
        Clears the current schema, forcing a rebuild on next access.
        """
        with self._lock:
            self._schema = None
            self._query_fields.clear()
            self._mutation_fields.clear()
            self._registered_models.clear()
            logger.info(f"Schema '{self.schema_name}' cleared")

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
                f"App '{app_label}' registered for schema '{self.schema_name}' generation"
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
                f"App '{app_label}' unregistered from schema '{self.schema_name}' generation"
            )

    def register_model(self, model: Union[Type[models.Model], str]) -> None:
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
                f"Model '{model_identifier}' registered for schema '{self.schema_name}' generation"
            )

    def unregister_model(self, model: Union[Type[models.Model], str]) -> None:
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
                f"Model '{model_identifier}' unregistered from schema '{self.schema_name}' generation"
            )

    def reload_app_schema(self, app_label: str) -> None:
        """
        Reloads schema for a specific app.

        Args:
            app_label: Django app label to reload
        """
        try:
            app_config = apps.get_app_config(app_label)
            models = [
                model
                for model in app_config.get_models()
                if self._is_valid_model(model)
            ]

            with self._lock:
                # Remove existing app-related fields
                for model in models:
                    model_name = model.__name__.lower()
                    # Remove queries
                    self._query_fields.pop(model_name, None)
                    self._query_fields.pop(f"{model_name}s", None)
                    self._query_fields.pop(f"{model_name}_pages", None)

                    # Remove mutations
                    mutations = self.mutation_generator.generate_all_mutations(model)
                    for mutation_name in mutations:
                        self._mutation_fields.pop(mutation_name, None)

                # Regenerate app schema
                self._generate_query_fields(models)
                self._generate_mutation_fields(models)

                # Update registered models
                self._registered_models.update(models)

                # Rebuild schema
                self.rebuild_schema()

            logger.info(
                f"Schema reloaded for app '{app_label}' in schema '{self.schema_name}'"
            )

        except Exception as e:
            logger.error(
                f"Failed to reload schema for app '{app_label}' in schema '{self.schema_name}': {str(e)}",
                exc_info=True,
            )
            raise

    def get_registered_models(self) -> Set[Type[models.Model]]:
        """
        Returns the set of registered models for this schema.

        Returns:
            Set[Type[models.Model]]: Set of registered Django models
        """
        return self._registered_models.copy()

    def get_query_fields(self) -> Dict[str, Union[graphene.Field, graphene.List]]:
        """
        Returns the current query fields for this schema.

        Returns:
            Dict[str, Union[graphene.Field, graphene.List]]: Query fields dictionary
        """
        return self._query_fields.copy()

    def get_mutation_fields(self) -> Dict[str, Type[graphene.Mutation]]:
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


class AutoSchemaGenerator:
    """Builds schemas from explicit model lists with basic caching."""

    _counter = itertools.count()

    def __init__(
        self,
        settings: Optional[Any] = None,
        schema_name: Optional[str] = None,
        registry=None,
    ) -> None:
        if schema_name is None:
            schema_name = f"auto_{next(self._counter)}"
        self._base_schema_name = schema_name
        self._settings = settings
        self._registry = registry
        self._registered_models: Set[Type[models.Model]] = set()
        self._query_extensions: List[Type[graphene.ObjectType]] = []
        self._schema_cache: Dict[Tuple[str, ...], graphene.Schema] = {}
        self._builders: Dict[Tuple[str, ...], SchemaBuilder] = {}
        self._lock = threading.Lock()

    def register_model(self, model: Type[models.Model]) -> None:
        self._registered_models.add(model)
        self._invalidate_cache()

    def register_models(self, models_list: List[Type[models.Model]]) -> None:
        for model in models_list:
            self._registered_models.add(model)
        self._invalidate_cache()

    def add_query_extension(self, extension: Type[graphene.ObjectType]) -> None:
        if extension not in self._query_extensions:
            self._query_extensions.append(extension)
            self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        self._schema_cache.clear()
        for builder in self._builders.values():
            builder.clear_schema()

    def _cache_key(
        self, models_list: Optional[List[Type[models.Model]]]
    ) -> Tuple[str, ...]:
        if models_list is None:
            return ("__all__",)
        if not models_list:
            return ("__none__",)
        return tuple(sorted({model._meta.label_lower for model in models_list}))

    def _get_builder(self, cache_key: Tuple[str, ...]) -> SchemaBuilder:
        builder = self._builders.get(cache_key)
        if builder is None:
            schema_name = f"{self._base_schema_name}_{len(self._builders)}"
            builder = SchemaBuilder(
                settings=self._settings,
                schema_name=schema_name,
                registry=self._registry,
            )
            self._builders[cache_key] = builder
        return builder

    def get_schema(
        self, model_list: Optional[List[Type[models.Model]]] = None
    ) -> graphene.Schema:
        if model_list is None and self._registered_models:
            models_list = list(self._registered_models)
        else:
            models_list = list(model_list) if model_list is not None else None

        cache_key = self._cache_key(models_list)
        with self._lock:
            cached = self._schema_cache.get(cache_key)
            if cached is not None:
                return cached

            builder = self._get_builder(cache_key)

            if models_list is not None:
                valid_models = [
                    model for model in models_list if builder._is_valid_model(model)
                ]

                def _discover_models_override() -> List[Type[models.Model]]:
                    return valid_models

                builder._discover_models = _discover_models_override

            if self._query_extensions:
                original_load = getattr(
                    builder, "_auto_schema_original_load_query_extensions", None
                )
                if original_load is None:
                    original_load = builder._load_query_extensions
                    builder._auto_schema_original_load_query_extensions = original_load

                def _load_query_extensions_override() -> List[Type[graphene.ObjectType]]:
                    loaded = list(original_load())
                    for extension in self._query_extensions:
                        if extension not in loaded:
                            loaded.append(extension)
                    return loaded

                builder._load_query_extensions = _load_query_extensions_override

            schema = builder.get_schema()
            self._schema_cache[cache_key] = schema
            return schema


# Global schema management functions
def get_schema_builder(schema_name: str = "default") -> SchemaBuilder:
    """
    Get or create a schema builder instance for the given schema name.

    Args:
        schema_name: Name of the schema (defaults to "default")

    Returns:
        SchemaBuilder: Schema builder instance
    """
    from .registry import schema_registry

    schema_registry.discover_schemas()
    return SchemaBuilder(schema_name=schema_name, registry=schema_registry)


def get_schema(schema_name: str = "default") -> graphene.Schema:
    """
    Get the GraphQL schema for the given schema name.

    Args:
        schema_name: Name of the schema (defaults to "default")

    Returns:
        graphene.Schema: The GraphQL schema
    """
    return get_schema_builder(schema_name).get_schema()


def clear_all_schemas() -> None:
    """
    Clear all schema builder instances.
    """
    with SchemaBuilder._lock:
        for schema_name, builder in SchemaBuilder._instances.items():
            builder.clear_schema()
        SchemaBuilder._instances.clear()
        logger.info("All schemas cleared")


def get_all_schema_names() -> List[str]:
    """
    Get all registered schema names.

    Returns:
        List[str]: List of schema names
    """
    return list(SchemaBuilder._instances.keys())

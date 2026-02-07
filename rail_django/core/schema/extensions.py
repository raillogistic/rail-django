"""
Extensions Mixin - Extension integration and schema rebuilding.

This module provides the ExtensionsMixin class with methods for integrating
security extensions, health queries, metadata queries, and the main
rebuild_schema method.
"""

import importlib
import logging
from typing import Any, Dict, List, Optional, Type

import graphene
from django.conf import settings as django_settings
from django.db import models
from graphene_django.debug import DjangoDebug

logger = logging.getLogger(__name__)


class ExtensionsMixin:
    """
    Mixin providing extension integration and schema rebuilding.

    This mixin is designed to be used with SchemaBuilderCore to provide
    methods for integrating extensions and building the final schema.
    """

    def _load_query_extensions(self) -> list[type[graphene.ObjectType]]:
        """Load custom query extensions defined in schema settings."""
        extension_paths = self._get_schema_setting("query_extensions", [])
        loaded = []
        for path in extension_paths or []:
            if not isinstance(path, str) or not path.strip():
                continue
            try:
                module_path, class_name = path.rsplit(".", 1)
            except ValueError:
                logger.warning(
                    f"Invalid query extension path '{path}' configured for "
                    f"schema '{self.schema_name}'"
                )
                continue
            try:
                module = importlib.import_module(module_path)
                query_class = getattr(module, class_name)
                loaded.append(query_class)
            except Exception as e:
                logger.warning(
                    f"Could not import query extension '{path}' for "
                    f"schema '{self.schema_name}': {e}"
                )
        return loaded

    def _attach_query_class_fields(
        self, query_attrs: dict[str, Any], query_class: type[graphene.ObjectType]
    ) -> None:
        """Merge fields from a custom query class into the root query attributes."""
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
        self, fields: dict[str, Any], allowlist: Optional[list[str]]
    ) -> dict[str, Any]:
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

    def _camelcase_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Convert dictionary keys to camelCase if auto_camelcase is enabled."""
        from graphene.utils.str_converters import to_camel_case

        if not self.settings.auto_camelcase:
            return fields

        return {to_camel_case(k): v for k, v in fields.items()}

    def _build_security_mutations(self) -> dict[str, Any]:
        """Build security-related mutations."""
        security_mutations = {}
        try:
            from ...extensions.auth import (
                LoginMutation,
                LogoutMutation,
                RefreshTokenMutation,
                RegisterMutation,
                UpdateMySettingsMutation,
                VerifyMFALoginMutation,
                RevokeSessionMutation,
                RevokeAllSessionsMutation,
            )

            disable_security = self.settings.disable_security_mutations
            if not disable_security:
                mutations_to_add = {
                    "login": LoginMutation.Field(),
                    "register": RegisterMutation.Field(),
                    "refresh_token": RefreshTokenMutation.Field(),
                    "logout": LogoutMutation.Field(),
                    "update_my_settings": UpdateMySettingsMutation.Field(),
                    "verify_mfa_login": VerifyMFALoginMutation.Field(),
                    "revoke_session": RevokeSessionMutation.Field(),
                    "revoke_all_sessions": RevokeAllSessionsMutation.Field(),
                }

                # Integrate MFA mutations
                try:
                    from ...extensions.mfa.mutations import MFAMutations

                    # Check if MFA is enabled in settings, defaulting to True for backward compatibility
                    # or checking app availability. Assuming always available if import succeeds.
                    # We can use the MFAMutations fields directly.
                    for field_name, field in MFAMutations._meta.fields.items():
                        mutations_to_add[field_name] = field
                    logger.info(
                        f"MFA mutations integrated into schema '{self.schema_name}'"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Could not import MFA mutations for schema '{self.schema_name}': {e}"
                    )

                security_mutations.update(mutations_to_add)

                logger.info(
                    f"Security mutations integrated into schema '{self.schema_name}'"
                )
        except ImportError as e:
            logger.warning(
                f"Could not import security mutations for "
                f"schema '{self.schema_name}': {e}"
            )

        return security_mutations

    def _build_extension_mutations(self) -> dict[str, Any]:
        """Build health/maintenance extension mutations."""
        extension_mutations: dict[str, Any] = {}

        if self._get_schema_setting("enable_extension_mutations", True):
            try:
                from ...extensions.audit import LogFrontendAuditMutation
                from ...extensions.health import RefreshSchemaMutation

                extension_mutations.update(
                    {
                        "refresh_schema": RefreshSchemaMutation.Field(),
                        "log_frontend_audit": LogFrontendAuditMutation.Field(),
                    }
                )
                logger.info(
                    f"Health extension mutations integrated into "
                    f"schema '{self.schema_name}'"
                )
            except ImportError as e:
                logger.warning(
                    f"Could not import health extension mutations for "
                    f"schema '{self.schema_name}': {e}"
                )

        return extension_mutations

    def _build_table_mutations(self) -> dict[str, Any]:
        """Build Table v3 mutations."""
        table_mutations: dict[str, Any] = {}
        try:
            from ...extensions.table import TableMutations

            for field_name, field in TableMutations._meta.fields.items():
                table_mutations[field_name] = field
        except ImportError as e:
            logger.warning(
                "Could not import table mutations for schema '%s': %s",
                self.schema_name,
                e,
            )
        return table_mutations

    def _integrate_table_subscriptions(self) -> None:
        """Integrate Table v3 subscriptions."""
        try:
            from ...extensions.table import TableSubscriptions

            self._subscription_fields.update(TableSubscriptions._meta.fields)
        except ImportError as e:
            logger.warning(
                "Could not import table subscriptions for schema '%s': %s",
                self.schema_name,
                e,
            )

    def _load_mutation_extensions(self) -> dict[str, Any]:
        """Load custom mutation extensions from settings."""
        extension_mutations: dict[str, Any] = {}
        mutation_extensions_path = self._get_schema_setting("mutation_extensions", [])

        for path in mutation_extensions_path or []:
            if not isinstance(path, str) or not path.strip():
                continue
            try:
                module_path, class_name = path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                mutation_class = getattr(module, class_name)

                for field_name, field in mutation_class._meta.fields.items():
                    extension_mutations[field_name] = field

                logger.info(f"Loaded mutation extension: {path}")
            except Exception as e:
                logger.warning(
                    f"Could not import mutation extension '{path}' for "
                    f"schema '{self.schema_name}': {e}"
                )

        return extension_mutations

    def _create_query_type(
        self, query_attrs: dict[str, Any]
    ) -> type[graphene.ObjectType]:
        """Create the Query type from query attributes."""
        query_allowlist = self._get_schema_setting("query_field_allowlist", None)
        if query_allowlist is not None:
            query_attrs = self._apply_field_allowlist(query_attrs, query_allowlist)
            if not query_attrs:
                query_attrs = {
                    "dummy": graphene.String(
                        description="Dummy query field to ensure schema validity"
                    )
                }

        query_attrs = self._camelcase_fields(query_attrs)
        return type("Query", (graphene.ObjectType,), query_attrs)

    def _create_mutation_type(
        self, all_mutations: dict[str, Any]
    ) -> Optional[type[graphene.ObjectType]]:
        """Create the Mutation type from mutation fields."""
        mutation_allowlist = self._get_schema_setting("mutation_field_allowlist", None)
        if mutation_allowlist is not None:
            all_mutations = self._apply_field_allowlist(
                all_mutations, mutation_allowlist
            )

        if all_mutations:
            all_mutations = self._camelcase_fields(all_mutations)
            return type("Mutation", (graphene.ObjectType,), all_mutations)
        else:
            if mutation_allowlist is not None:
                logger.info(
                    f"No allowed mutations for schema '{self.schema_name}', "
                    "skipping mutation type"
                )
                return None
            else:
                logger.info(
                    f"No mutations found for schema '{self.schema_name}', "
                    "creating dummy mutation"
                )

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
                return type("Mutation", (graphene.ObjectType,), mutation_attrs)

    def _create_subscription_type(self) -> Optional[type[graphene.ObjectType]]:
        """Create the Subscription type from subscription fields."""
        subscription_fields = dict(self._subscription_fields)
        subscription_allowlist = self._get_schema_setting(
            "subscription_field_allowlist", None
        )
        if subscription_allowlist is not None:
            subscription_fields = self._apply_field_allowlist(
                subscription_fields, subscription_allowlist
            )

        if subscription_fields:
            subscription_fields = self._camelcase_fields(subscription_fields)
            return type("Subscription", (graphene.ObjectType,), subscription_fields)

        return None

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
                self._subscription_fields = {}
                build_context = {
                    "schema_name": self.schema_name,
                    "builder": self,
                }

                # Run pre-build hooks
                try:
                    from ...plugins.base import plugin_manager
                    from ...plugins.hooks import hook_registry

                    build_context = plugin_manager.run_pre_schema_build(
                        self.schema_name, self, build_context
                    )
                    build_context = hook_registry.execute_hooks_with_modification(
                        "schema_pre_build", build_context, self
                    )
                except Exception:
                    pass

                # Discover models
                discovered_models = self._discover_models()
                self._registered_models = set(discovered_models)
                logger.info(
                    f"Discovered {len(discovered_models)} models for "
                    f"schema '{self.schema_name}': "
                    f"{[m.__name__ for m in discovered_models]}"
                )

                # Generate queries, mutations, and subscriptions
                self._generate_query_fields(discovered_models)
                self._generate_mutation_fields(discovered_models)
                self._generate_subscription_fields(discovered_models)

                logger.info(
                    f"Schema '{self.schema_name}' generation - "
                    f"Query fields: {len(self._query_fields)}, "
                    f"Mutation fields: {len(self._mutation_fields)}, "
                    f"Subscription fields: {len(self._subscription_fields)}"
                )

                # Build query attributes
                query_attrs: dict[str, Any] = {}
                if getattr(django_settings, "DEBUG", False):
                    query_attrs["debug"] = graphene.Field(DjangoDebug, name="_debug")
                query_attrs.update(self._query_fields)

                # Add introspection queries
                if hasattr(self.query_generator, "generate_introspection_queries"):
                    query_attrs.update(
                        self.query_generator.generate_introspection_queries()
                    )

                # Load and attach custom query extensions
                custom_query_classes = self._load_query_extensions()
                for query_class in custom_query_classes:
                    self._attach_query_class_fields(query_attrs, query_class)
                if custom_query_classes:
                    logger.info(
                        f"Custom query extensions integrated into "
                        f"schema '{self.schema_name}': "
                        f"{[cls.__name__ for cls in custom_query_classes]}"
                    )

                # Integrate security, health, task, and form queries
                self._integrate_security_queries(query_attrs)
                self._integrate_health_queries(query_attrs)
                self._integrate_task_queries(query_attrs)
                self._integrate_metadata_queries(query_attrs)
                self._integrate_form_queries(query_attrs)
                self._integrate_table_queries(query_attrs)

                # Create Query type
                query_type = self._create_query_type(query_attrs)

                # Build mutations
                logger.info(
                    f"Checking mutation fields for schema '{self.schema_name}': "
                    f"{len(self._mutation_fields)} mutations found"
                )

                security_mutations = self._build_security_mutations()
                extension_mutations = self._build_extension_mutations()
                custom_mutations = self._load_mutation_extensions()
                table_mutations = self._build_table_mutations()

                all_mutations = {
                    **self._mutation_fields,
                    **security_mutations,
                    **extension_mutations,
                    **table_mutations,
                    **custom_mutations,
                }

                # Create Mutation and Subscription types
                self._integrate_table_subscriptions()
                mutation_type = self._create_mutation_type(all_mutations)
                subscription_type = self._create_subscription_type()

                # Setup security middleware
                middleware = []
                try:
                    from ...extensions.rate_limiting import GraphQLSecurityMiddleware

                    middleware.append(GraphQLSecurityMiddleware())
                    logger.info(
                        f"Security middleware integrated into "
                        f"schema '{self.schema_name}'"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Could not import security middleware for "
                        f"schema '{self.schema_name}': {e}"
                    )

                # Create the schema
                self._schema = graphene.Schema(
                    query=query_type,
                    mutation=mutation_type,
                    subscription=subscription_type,
                    auto_camelcase=self.settings.auto_camelcase,
                )

                # Store middleware for later use in execution
                self._middleware = middleware

                # Increment schema version
                self._schema_version += 1

                # Record schema snapshot
                try:
                    from ..schema_snapshots import record_schema_snapshot

                    record_schema_snapshot(
                        self.schema_name,
                        self._schema,
                        version=str(self._schema_version),
                        description=f"Schema snapshot for {self.schema_name}",
                    )
                except Exception:
                    pass

                # Run post-build hooks
                try:
                    from ...plugins.base import plugin_manager
                    from ...plugins.hooks import hook_registry

                    plugin_manager.run_post_schema_build(
                        self.schema_name, self, self._schema, build_context
                    )
                    hook_registry.execute_hooks(
                        "schema_post_build", build_context, self, self._schema
                    )
                except Exception:
                    pass

                # Register schema in the registry
                self._register_schema_in_registry(discovered_models)

                logger.info(
                    f"Schema '{self.schema_name}' rebuilt successfully "
                    f"(version {self._schema_version})"
                    f"\n - Models: {len(discovered_models)}"
                    f"\n - Queries: {len(self._query_fields)}"
                    f"\n - Mutations: {len(self._mutation_fields)}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to rebuild schema '{self.schema_name}': {str(e)}",
                    exc_info=True,
                )
                raise

"""
Query Integration Mixin - Integration of extension queries.

This module provides the QueryIntegrationMixin class with methods for
integrating security, health, task, and metadata queries into the schema.
"""

import logging
from typing import Any, Dict, List, Type

import graphene

logger = logging.getLogger(__name__)


class QueryIntegrationMixin:
    """
    Mixin providing query integration methods for extensions.

    This mixin is designed to be used with SchemaBuilder to provide
    methods for integrating various extension queries into the schema.
    """

    def _integrate_security_queries(
        self, query_attrs: dict[str, Any]
    ) -> list[type[graphene.ObjectType]]:
        """
        Integrate security-related queries into query attributes.

        Returns list of loaded security query classes.
        """
        security_query_classes = []

        try:
            from ...extensions.auth import MeQuery

            security_query_classes.append(MeQuery)
        except ImportError as e:
            logger.warning(
                f"Could not import MeQuery for schema '{self.schema_name}': {e}"
            )

        try:
            from ...extensions.permissions import PermissionQuery

            security_query_classes.append(PermissionQuery)
        except ImportError as e:
            logger.warning(
                f"Could not import PermissionQuery for schema '{self.schema_name}': {e}"
            )

        try:
            from ...extensions.validation import ValidationQuery

            security_query_classes.append(ValidationQuery)
        except ImportError as e:
            logger.warning(
                f"Could not import ValidationQuery for schema '{self.schema_name}': {e}"
            )

        try:
            from ...extensions.rate_limiting import SecurityQuery

            security_query_classes.append(SecurityQuery)
        except ImportError as e:
            logger.info(
                f"Rate limiting SecurityQuery not available for "
                f"schema '{self.schema_name}': {e}"
            )

        # Merge security queries and bind their resolvers to the root Query
        for query_class in security_query_classes:
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

        if security_query_classes:
            logger.info(
                f"Security extensions integrated into schema '{self.schema_name}' "
                "with resolver binding"
            )

        return security_query_classes

    def _integrate_health_queries(self, query_attrs: dict[str, Any]) -> None:
        """Integrate health monitoring queries into query attributes."""
        try:
            from ...extensions.health import HealthQuery

            health_query_instance = HealthQuery()

            for field_name, field in HealthQuery._meta.fields.items():
                resolver_method_name = f"resolve_{field_name}"
                if hasattr(health_query_instance, resolver_method_name):
                    resolver_method = getattr(
                        health_query_instance, resolver_method_name
                    )

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

            logger.info(
                f"Health monitoring queries integrated into schema '{self.schema_name}'"
            )
        except ImportError as e:
            logger.warning(
                f"Could not import health queries for schema '{self.schema_name}': {e}"
            )

    def _integrate_task_queries(self, query_attrs: dict[str, Any]) -> None:
        """Integrate task orchestration queries into query attributes."""
        try:
            from ...extensions.tasks import TaskQuery, tasks_enabled

            if tasks_enabled(self.schema_name):
                task_query_instance = TaskQuery()

                for field_name, field in TaskQuery._meta.fields.items():
                    resolver_method_name = f"resolve_{field_name}"
                    if hasattr(task_query_instance, resolver_method_name):
                        resolver_method = getattr(
                            task_query_instance, resolver_method_name
                        )

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

                logger.info(
                    "Task queries integrated into schema '%s'",
                    self.schema_name,
                )
        except ImportError as e:
            logger.warning(
                "Could not import task queries for schema '%s': %s",
                self.schema_name,
                e,
            )

    def _integrate_metadata_queries(self, query_attrs: dict[str, Any]) -> None:
        """Integrate Model Schema V2 queries (Metadata) into query attributes."""
        if not self.settings.show_metadata:
            return

        try:
            from ...extensions.metadata import ModelSchemaQuery
            from graphene.utils.str_converters import to_camel_case

            schema_query_v2_instance = ModelSchemaQuery()
            existing_field_names = set(query_attrs.keys())
            if self.settings.auto_camelcase:
                existing_field_names.update(to_camel_case(name) for name in query_attrs)

            for field_name, field in ModelSchemaQuery._meta.fields.items():
                normalized_name = (
                    to_camel_case(field_name) if self.settings.auto_camelcase else field_name
                )
                if field_name in existing_field_names or normalized_name in existing_field_names:
                    logger.debug(
                        "Skipping metadata query field '%s' for schema '%s' because a field "
                        "with the same public name already exists",
                        field_name,
                        self.schema_name,
                    )
                    continue

                resolver_method_name = f"resolve_{field_name}"
                if hasattr(schema_query_v2_instance, resolver_method_name):
                    resolver_method = getattr(
                        schema_query_v2_instance, resolver_method_name
                    )

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

                existing_field_names.add(field_name)
                if self.settings.auto_camelcase:
                    existing_field_names.add(to_camel_case(field_name))

            logger.info(
                f"Model schema queries integrated into schema '{self.schema_name}'"
            )
        except ImportError as e:
            logger.warning(
                f"Could not import metadata queries for "
                f"schema '{self.schema_name}': {e}"
            )

    def _integrate_form_queries(self, query_attrs: dict[str, Any]) -> None:
        """Integrate Form API queries into query attributes."""
        if not getattr(self.settings, "show_form", True):
            return

        try:
            from ...extensions.form import FormQuery

            form_query_instance = FormQuery()
            for field_name, field in FormQuery._meta.fields.items():
                resolver_method_name = f"resolve_{field_name}"
                if hasattr(form_query_instance, resolver_method_name):
                    resolver_method = getattr(form_query_instance, resolver_method_name)

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

            logger.info(
                f"Form API queries integrated into schema '{self.schema_name}'"
            )
        except ImportError as e:
            logger.warning(
                f"Could not import form queries for "
                f"schema '{self.schema_name}': {e}"
            )

    def _integrate_table_queries(self, query_attrs: dict[str, Any]) -> None:
        """Integrate Table v3 queries into query attributes."""
        try:
            from ...extensions.table import TableQuery

            table_query_instance = TableQuery()
            for field_name, field in TableQuery._meta.fields.items():
                resolver_method_name = f"resolve_{field_name}"
                if hasattr(table_query_instance, resolver_method_name):
                    resolver_method = getattr(table_query_instance, resolver_method_name)

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

            logger.info(
                "Table queries integrated into schema '%s'",
                self.schema_name,
            )
        except ImportError as e:
            logger.warning(
                "Could not import table queries for schema '%s': %s",
                self.schema_name,
                e,
            )

    def _integrate_importing_queries(self, query_attrs: dict[str, Any]) -> None:
        """Integrate import workflow queries into query attributes."""
        try:
            from ...extensions.importing import ImportQuery

            import_query_instance = ImportQuery()
            for field_name, field in ImportQuery._meta.fields.items():
                resolver_method_name = f"resolve_{field_name}"
                if hasattr(import_query_instance, resolver_method_name):
                    resolver_method = getattr(import_query_instance, resolver_method_name)

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

            logger.info(
                "Importing queries integrated into schema '%s'",
                self.schema_name,
            )
        except ImportError as e:
            logger.warning(
                "Could not import importing queries for schema '%s': %s",
                self.schema_name,
                e,
            )

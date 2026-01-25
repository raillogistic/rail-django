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
        """Integrate model metadata queries into query attributes."""
        if not self.settings.show_metadata:
            return

        try:
            from ...extensions.metadata import ModelMetadataQuery

            metadata_query_instance = ModelMetadataQuery()

            for field_name, field in ModelMetadataQuery._meta.fields.items():
                resolver_method_name = f"resolve_{field_name}"
                if hasattr(metadata_query_instance, resolver_method_name):
                    resolver_method = getattr(
                        metadata_query_instance, resolver_method_name
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
                f"Model metadata queries integrated into schema '{self.schema_name}'"
            )
        except ImportError as e:
            logger.warning(
                f"Could not import metadata queries for schema '{self.schema_name}': {e}"
            )

    def _integrate_metadata_v2_queries(self, query_attrs: dict[str, Any]) -> None:
        """Integrate Model Schema V2 queries (Metadata V2) into query attributes."""
        if not self.settings.show_metadata:
            return

        try:
            from ...extensions.metadata_v2 import ModelSchemaQueryV2

            schema_query_v2_instance = ModelSchemaQueryV2()
            for field_name, field in ModelSchemaQueryV2._meta.fields.items():
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

            logger.info(
                f"Model schema V2 queries integrated into schema '{self.schema_name}'"
            )
        except ImportError as e:
            logger.warning(
                f"Could not import metadata v2 queries for "
                f"schema '{self.schema_name}': {e}"
            )

"""
Query Builder Mixin - Query, Mutation, and Subscription generation.

This module provides the QueryBuilderMixin class with methods for generating
GraphQL query, mutation, and subscription fields from Django models.
"""

import logging
import re
import unicodedata
from typing import Optional

import graphene
from graphene.utils.str_converters import to_camel_case, to_snake_case
from django.db import models

logger = logging.getLogger(__name__)

_GRAPHQL_NAME_INVALID_RE = re.compile(r"[^_0-9A-Za-z]")


class QueryBuilderMixin:
    """
    Mixin providing query, mutation, and subscription field generation.

    This mixin is designed to be used with SchemaBuilderCore to provide
    methods for generating GraphQL fields from Django models.
    """

    def _pluralize_name(self, name: str) -> str:
        """
        Pluralize a name for list queries.
        Uses a simple suffix-only rule (always append "s").

        Args:
            name: The singular name to pluralize

        Returns:
            str: The pluralized name
        """
        value = str(name or "").strip()
        if not value:
            return value
        return f"{value}s"

    def _get_list_alias(self, model: type[models.Model]) -> Optional[str]:
        """
        Get a list alias for a model based on verbose_name_plural.

        Args:
            model: Django model class

        Returns:
            Optional[str]: The camelCase alias or None
        """
        original_attrs = getattr(model._meta, "original_attrs", {}) or {}
        if "verbose_name_plural" not in original_attrs:
            return None
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
        return to_camel_case(alias)

    def _to_pascal_case(self, value: str) -> str:
        """Convert a string value to PascalCase."""
        camel = to_camel_case(to_snake_case(value))
        if not camel:
            return ""
        return camel[0].upper() + camel[1:]

    def _manager_suffix(self, manager_name: str, is_default: bool) -> str:
        """Return the manager contract suffix (empty for default manager)."""
        if is_default:
            return ""
        manager_token = self._to_pascal_case(manager_name)
        return f"By{manager_token}" if manager_token else ""

    def _generate_query_fields(self, models_list: list[type[models.Model]]) -> None:
        """
        Generates query fields for all discovered models.
        Supports multiple managers per model with custom naming conventions.

        Args:
            models_list: List of Django models to generate queries for
        """
        self._query_fields = {
            "dummy": graphene.String(
                description="Dummy query field to ensure schema validity"
            )
        }

        for model in models_list:
            # Canonical model token: camelCase model class name.
            model_name = to_camel_case(to_snake_case(model.__name__))

            # Get model managers using introspector
            from ...generators.introspector import ModelIntrospector

            introspector = ModelIntrospector.for_model(model)
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

                manager_suffix = self._manager_suffix(
                    manager_name, manager_info.is_default
                )

                # Single/list/group queries are not exposed for history managers.
                if not is_history_manager:
                    single_query = self.query_generator.generate_single_query(
                        model, manager_name
                    )
                    self._query_fields[f"{model_name}{manager_suffix}"] = single_query

                    list_query = self.query_generator.generate_list_query(
                        model, manager_name
                    )
                    self._query_fields[f"{model_name}List{manager_suffix}"] = list_query

                    grouping_query = self.query_generator.generate_grouping_query(
                        model, manager_name
                    )
                    self._query_fields[f"{model_name}Group{manager_suffix}"] = (
                        grouping_query
                    )

                if self.settings.enable_pagination:
                    paginated_query = self.query_generator.generate_paginated_query(
                        model,
                        manager_name,
                        result_model=history_result_model,
                        operation_name=("history" if is_history_manager else "paginated"),
                    )
                    self._query_fields[f"{model_name}Page{manager_suffix}"] = (
                        paginated_query
                    )

    def _generate_mutation_fields(self, models_list: list[type[models.Model]]) -> None:
        """
        Generates mutation fields for all discovered models.

        Args:
            models_list: List of Django models to generate mutations for
        """
        self._mutation_fields = {}

        for model in models_list:
            mutations = self.mutation_generator.generate_all_mutations(model)
            logger.debug(
                f"Generated {len(mutations)} mutations for model {model.__name__}: "
                f"{list(mutations.keys())}"
            )
            self._mutation_fields.update(mutations)

        logger.info(
            f"Total mutations generated for schema '{self.schema_name}': "
            f"{len(self._mutation_fields)}"
        )
        logger.debug(f"Mutation fields: {list(self._mutation_fields.keys())}")

    def _generate_subscription_fields(
        self, models_list: list[type[models.Model]]
    ) -> None:
        """
        Generates subscription fields for all discovered models.

        Args:
            models_list: List of Django models to generate subscriptions for
        """
        self._subscription_fields = {}
        try:
            from ...extensions.subscriptions.registry import clear_subscription_registry
            clear_subscription_registry(self.schema_name)
        except ImportError:
            logger.warning(f"Subscriptions disabled for schema '{self.schema_name}': No module named 'rail_django.extensions.subscriptions'")
            return
        try:
            subscriptions = self.subscription_generator.generate_all_subscriptions(
                models_list
            )
        except ImportError as exc:
            logger.warning(
                "Subscriptions disabled for schema '%s': %s",
                self.schema_name,
                exc,
            )
            return

        if subscriptions:
            self._subscription_fields.update(subscriptions)
            logger.info(
                "Total subscriptions generated for schema '%s': %s",
                self.schema_name,
                len(self._subscription_fields),
            )
            logger.debug(
                "Subscription fields: %s", list(self._subscription_fields.keys())
            )

        try:
            from ...extensions.tasks import get_task_subscription_field, tasks_enabled

            if tasks_enabled(self.schema_name):
                task_field = get_task_subscription_field(self.schema_name)
                if task_field is not None:
                    self._subscription_fields["task_updated"] = task_field
        except Exception as exc:
            logger.warning(
                "Could not import task subscriptions for schema '%s': %s",
                self.schema_name,
                exc,
            )



"""
Single and list query builders.

This module provides query generation for single object retrieval and
list queries with filtering, ordering, and pagination support.
"""

import logging
from typing import Any, List, Optional, Type, Union

import graphene
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models

try:
    from graphene_django.filter import DjangoFilterConnectionField  # type: ignore
except ImportError:
    DjangoFilterConnectionField = None

from ..core.meta import get_model_graphql_meta
from ..extensions.optimization import optimize_query
from .queries_base import (
    RESERVED_QUERY_ARGS,
    QueryContext,
    QueryFilterPipeline,
    QueryOrderingHelper,
    build_query_arguments,
    create_default_ordering_config,
    map_filter_to_graphql_type,
)
from .queries_ordering import get_default_ordering

logger = logging.getLogger(__name__)


def _get_nested_filter_generator(schema_name: str):
    """Lazy import to avoid circular dependencies. Returns singleton instance."""
    from .filters import get_nested_filter_generator

    return get_nested_filter_generator(schema_name)


def _get_nested_filter_applicator(schema_name: str):
    """Lazy import to avoid circular dependencies. Returns singleton instance."""
    from .filters import get_nested_filter_applicator

    return get_nested_filter_applicator(schema_name)


def generate_single_query(
    self, model: Type[models.Model], manager_name: str = "objects"
) -> graphene.Field:
    """
    Generate a single object query for a model using the specified manager.

    For polymorphic models, uses the base model type with polymorphic_type field
    to identify the specific subclass instead of union types.

    Args:
        model: Django model class
        manager_name: Name of the manager to use (default: "objects")

    Returns:
        graphene.Field for single object retrieval
    """
    model_type = self.type_generator.generate_object_type(model)
    graphql_meta = get_model_graphql_meta(model)

    def resolve_single(root, info, id):
        """Resolver for single object queries."""
        try:
            self._enforce_model_permission(info, model, "retrieve", graphql_meta)
            manager = getattr(model, manager_name)
            queryset = self._apply_tenant_scope(
                manager.all(), info, model, operation="retrieve"
            )
            instance = queryset.get(pk=id)
            self._enforce_tenant_access(
                instance, info, model, operation="retrieve"
            )
            graphql_meta.ensure_operation_access(
                "retrieve", info=info, instance=instance
            )
            return self._apply_field_masks(instance, info, model)
        except model.DoesNotExist:
            return None

    return graphene.Field(
        model_type,
        id=graphene.ID(required=True),
        resolver=resolve_single,
        description=f"Retrieve a single {model.__name__} by ID using {manager_name} manager",
    )


def generate_list_query(
    self, model: Type[models.Model], manager_name: str = "objects"
) -> Union[graphene.List, "DjangoFilterConnectionField"]:
    """
    Generate a list query for retrieving model instances.

    Supports:
    - Nested Prisma/Hasura-style filtering with typed inputs
    - Filter presets and saved filters
    - Ordering with count annotations and property-based sorting
    - DISTINCT ON support (PostgreSQL)
    - Offset/limit pagination

    Args:
        model: Django model class
        manager_name: Name of the manager to use (default: "objects")

    Returns:
        graphene.List or DjangoFilterConnectionField for list retrieval
    """
    model_type = self.type_generator.generate_object_type(model)
    model_name = model.__name__.lower()
    graphql_meta = get_model_graphql_meta(model)
    ordering_config = getattr(graphql_meta, "ordering_config", None)
    if ordering_config is None:
        ordering_config = create_default_ordering_config()

    # Generate filter classes before resolver definition
    filter_class = self.filter_generator.generate_filter_set(model)
    nested_where_input = None
    nested_filter_applicator = None

    try:
        nested_generator = _get_nested_filter_generator(self.schema_name)
        nested_where_input = nested_generator.generate_where_input(model)
        nested_filter_applicator = _get_nested_filter_applicator(self.schema_name)
    except (FieldDoesNotExist, ImproperlyConfigured, AttributeError) as e:
        # Expected errors during filter generation (missing fields, bad config)
        logger.warning(
            f"Could not generate nested filter for {model.__name__}: {e}",
            extra={"model": model.__name__, "schema": self.schema_name},
        )
    except RecursionError:
        # Circular reference in model relationships
        logger.error(
            f"Circular reference detected generating filter for {model.__name__}",
            extra={"model": model.__name__},
        )
    except Exception as e:
        # Unexpected error - log with traceback for debugging
        logger.exception(
            f"Unexpected error generating nested filter for {model.__name__}",
            extra={"model": model.__name__, "schema": self.schema_name},
        )

    # Relay connection mode
    if self.settings.use_relay and DjangoFilterConnectionField is not None:

        @optimize_query()
        def relay_resolver(root: Any, info: graphene.ResolveInfo, **kwargs):
            self._enforce_model_permission(info, model, "list", graphql_meta)
            graphql_meta.ensure_operation_access("list", info=info)
            manager = getattr(model, manager_name)
            queryset = manager.all()
            queryset = self._apply_tenant_scope(
                queryset, info, model, operation="list"
            )
            queryset = self.optimizer.optimize_queryset(queryset, info, model)
            return queryset

        return DjangoFilterConnectionField(
            model_type,
            filterset_class=filter_class,
            resolver=relay_resolver,
            description=f"Retrieve a list of {model_name} instances with pagination using {manager_name} manager",
        )

    # Standard list query with offset/limit pagination
    @optimize_query()
    def resolver(
        root: Any, info: graphene.ResolveInfo, **kwargs
    ) -> List[models.Model]:
        # Permission checks
        self._enforce_model_permission(info, model, "list", graphql_meta)
        graphql_meta.ensure_operation_access("list", info=info)

        # Get base queryset
        manager = getattr(model, manager_name)
        queryset = manager.all()
        queryset = self._apply_tenant_scope(
            queryset, info, model, operation="list"
        )

        # Apply query optimization
        queryset = self.optimizer.optimize_queryset(queryset, info, model)

        # Apply filters using pipeline
        context = QueryContext(
            model=model,
            queryset=queryset,
            info=info,
            kwargs=kwargs,
            graphql_meta=graphql_meta,
            filter_applicator=nested_filter_applicator,
            filter_class=filter_class,
            ordering_config=ordering_config,
            settings=self.settings,
            schema_name=self.schema_name,
        )

        pipeline = QueryFilterPipeline(context)
        queryset = pipeline.apply_all()

        # Check if filter pipeline returned empty due to invalid filters
        if not queryset.query.can_filter():
            # Queryset was set to none() due to invalid filters
            pass

        # Apply ordering using helper
        ordering_helper = QueryOrderingHelper(
            self, model, ordering_config, self.settings
        )
        queryset, items, has_prop_ordering, _ = ordering_helper.apply(
            queryset,
            kwargs.get("order_by"),
            kwargs.get("distinct_on"),
        )

        # Apply pagination
        if self.settings.enable_pagination:
            offset = kwargs.get("offset") or 0
            limit = kwargs.get("limit") or self.settings.default_page_size

            if items is not None:
                items = items[offset:offset + limit]
            else:
                queryset = queryset[offset:offset + limit]
                items = list(queryset)
        elif items is None:
            items = list(queryset)

        return self._apply_field_masks(items, info, model)

    # Build arguments
    arguments = build_query_arguments(
        settings=self.settings,
        ordering_config=ordering_config,
        nested_where_input=nested_where_input,
        filter_class=filter_class,
        include_pagination=self.settings.enable_pagination,
        use_page_based=False,
    )

    # Add quick filter if available in filter class
    if filter_class and "quick" in getattr(filter_class, "base_filters", {}):
        field = filter_class.base_filters["quick"]
        arguments["quick"] = graphene.Argument(
            graphene.String,
            description=getattr(field, "help_text", "Quick search across text fields"),
        )

    return graphene.List(
        model_type,
        args=arguments,
        resolver=resolver,
        description=f"Retrieve a list of {model_name} instances using {manager_name} manager",
    )

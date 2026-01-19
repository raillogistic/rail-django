"""
Paginated query builder helpers.

This module provides query generation for paginated queries with
page-based pagination, filtering, ordering, and pagination metadata.
"""

import logging
from typing import Any, List, Optional, Type

import graphene
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models

from ..core.meta import get_model_graphql_meta
from ..extensions.optimization import optimize_query
from .queries_base import (
    RESERVED_QUERY_ARGS,
    QueryContext,
    QueryFilterPipeline,
    QueryOrderingHelper,
    build_query_arguments,
    create_default_ordering_config,
)
from .queries_ordering import get_default_ordering

logger = logging.getLogger(__name__)


def _get_nested_filter_generator(schema_name: str):
    """Lazy import to avoid circular dependencies. Returns singleton instance."""
    from .filter_inputs import get_nested_filter_generator

    return get_nested_filter_generator(schema_name)


def _get_nested_filter_applicator(schema_name: str):
    """Lazy import to avoid circular dependencies. Returns singleton instance."""
    from .filter_inputs import get_nested_filter_applicator

    return get_nested_filter_applicator(schema_name)


class PaginationInfo(graphene.ObjectType):
    """Pagination metadata for paginated queries."""

    total_count = graphene.Int(description="Total number of records")
    page_count = graphene.Int(description="Total number of pages")
    current_page = graphene.Int(description="Current page number")
    per_page = graphene.Int(description="Number of records per page")
    has_next_page = graphene.Boolean(description="Whether there is a next page")
    has_previous_page = graphene.Boolean(description="Whether there is a previous page")


class PaginatedResult:
    """Container for paginated results."""

    def __init__(self, items: List[Any], page_info: PaginationInfo):
        """
        Initialize paginated result.

        Args:
            items: List of items for current page
            page_info: Pagination metadata
        """
        self.items = items
        self.page_info = page_info


class EmptyPaginatedResult:
    """Empty paginated result for invalid filter scenarios."""

    def __init__(self, per_page: int = 25):
        """
        Initialize empty result.

        Args:
            per_page: Page size to report
        """
        self.items = []
        self.page_info = type(
            "EmptyPaginationInfo",
            (),
            {
                "total_count": 0,
                "page_count": 0,
                "current_page": 1,
                "per_page": per_page,
                "has_next_page": False,
                "has_previous_page": False,
            },
        )()


def generate_paginated_query(
    self,
    model: Type[models.Model],
    manager_name: str = "objects",
    result_model: Optional[Type[models.Model]] = None,
    operation_name: str = "paginated",
) -> graphene.Field:
    """
    Generate a paginated query with page/per_page pagination.

    Returns both paginated results and pagination metadata (total_count,
    page_count, has_next_page, etc.).

    Args:
        model: Django model class for permissions and tenant scoping
        manager_name: Name of the manager to use (default: "objects")
        result_model: Model to use for result type (for historical queries)
        operation_name: Operation name for permission checks

    Returns:
        graphene.Field for paginated query
    """
    result_model = result_model or model
    filter_model = result_model or model
    model_type = self.type_generator.generate_object_type(result_model)
    model_name = result_model.__name__.lower()

    # Create dynamic connection type
    connection_name = f"{result_model.__name__}PaginatedConnection"
    PaginatedConnection = type(
        connection_name,
        (graphene.ObjectType,),
        {
            "items": graphene.List(
                model_type, description=f"List of {model_name} instances"
            ),
            "page_info": graphene.Field(
                PaginationInfo, description="Pagination metadata"
            ),
        },
    )

    graphql_meta = get_model_graphql_meta(model)
    ordering_config = getattr(graphql_meta, "ordering_config", None)
    if ordering_config is None:
        ordering_config = create_default_ordering_config()

    # Generate filter class and nested filter components BEFORE resolver
    filter_class = self.filter_generator.generate_filter_set(filter_model)

    nested_where_input = None
    nested_filter_applicator = None
    try:
        nested_generator = _get_nested_filter_generator(self.schema_name)
        nested_where_input = nested_generator.generate_where_input(filter_model)
        nested_filter_applicator = _get_nested_filter_applicator(self.schema_name)
    except (FieldDoesNotExist, ImproperlyConfigured, AttributeError) as e:
        # Expected errors during filter generation (missing fields, bad config)
        logger.warning(
            f"Could not generate nested filter for {filter_model.__name__}: {e}",
            extra={"model": filter_model.__name__, "schema": self.schema_name},
        )
    except RecursionError:
        # Circular reference in model relationships
        logger.error(
            f"Circular reference detected generating filter for {filter_model.__name__}",
            extra={"model": filter_model.__name__},
        )
    except Exception as e:
        # Unexpected error - log with traceback for debugging
        logger.exception(
            f"Unexpected error generating nested filter for {filter_model.__name__}",
            extra={"model": filter_model.__name__, "schema": self.schema_name},
        )

    @optimize_query()
    def resolver(
        root: Any, info: graphene.ResolveInfo, **kwargs
    ) -> PaginatedConnection:
        # Permission checks
        self._enforce_model_permission(info, model, operation_name, graphql_meta)
        graphql_meta.ensure_operation_access(operation_name, info=info)

        # Get base queryset
        manager = getattr(model, manager_name)
        queryset = manager.all()
        queryset = self._apply_tenant_scope(
            queryset, info, model, operation=operation_name
        )

        # Parse pagination parameters
        try:
            page = int(kwargs.get("page", 1))
        except (ValueError, TypeError):
            page = 1
        try:
            per_page = int(
                kwargs.get("per_page", self.settings.default_page_size)
            )
        except (ValueError, TypeError):
            per_page = self.settings.default_page_size
        per_page = max(1, min(per_page, self.settings.max_page_size))

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

        # Check for invalid filters (pipeline returns none())
        if hasattr(queryset, '_result_cache') and queryset._result_cache == []:
            return EmptyPaginatedResult(per_page)

        # Apply ordering using helper
        ordering_helper = QueryOrderingHelper(
            self, model, ordering_config, self.settings
        )
        queryset, items, has_prop_ordering, uncapped_total = ordering_helper.apply(
            queryset,
            kwargs.get("order_by"),
            kwargs.get("distinct_on"),
        )

        # Calculate pagination values
        if uncapped_total is not None:
            total_count = uncapped_total
        elif items is not None:
            total_count = len(items)
        else:
            total_count = queryset.count()

        # Calculate page count, handling empty results
        if total_count > 0:
            page_count = (total_count + per_page - 1) // per_page
        else:
            page_count = 0

        # Ensure page is within valid range
        if page_count == 0:
            page = 1
        else:
            page = max(1, min(page, page_count))

        # Apply pagination
        start = (page - 1) * per_page
        end = start + per_page

        if items is not None:
            items = items[start:end]
        else:
            items = list(queryset[start:end])

        # Create pagination info
        page_info = PaginationInfo(
            total_count=total_count,
            page_count=page_count,
            current_page=page,
            per_page=per_page,
            has_next_page=page < page_count,
            has_previous_page=page > 1,
        )

        items = self._apply_field_masks(items, info, model)
        return PaginatedResult(items=items, page_info=page_info)

    # Build arguments using shared builder
    arguments = build_query_arguments(
        settings=self.settings,
        ordering_config=ordering_config,
        nested_where_input=nested_where_input,
        filter_class=filter_class,
        include_pagination=True,
        use_page_based=True,
    )

    # Add quick filter if available
    if filter_class and "quick" in getattr(filter_class, "base_filters", {}):
        field = filter_class.base_filters["quick"]
        arguments["quick"] = graphene.Argument(
            graphene.String,
            description=getattr(field, "help_text", "Quick search across text fields"),
        )

    return graphene.Field(
        PaginatedConnection,
        args=arguments,
        resolver=resolver,
        description=f"Retrieve a paginated list of {model_name} instances using {manager_name} manager",
    )

"""
Paginated query builder helpers.
"""

from typing import Any, List, Optional, Type

import graphene
from django.db import models

from ..core.meta import get_model_graphql_meta
from ..extensions.optimization import optimize_query
from .queries_ordering import get_default_ordering


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

    def __init__(self, items, page_info):
        self.items = items
        self.page_info = page_info


def generate_paginated_query(
    self,
    model: Type[models.Model],
    manager_name: str = "objects",
    result_model: Optional[Type[models.Model]] = None,
    operation_name: str = "paginated",
) -> graphene.Field:
    """
    Generates a query field with advanced pagination support using the specified manager.
    Returns both the paginated results and pagination metadata. When result_model is
    provided (e.g., for HistoricalRecords managers), it controls the GraphQL type used
    for the paginated items so that history entries expose their specific schema.
    The ``operation_name`` argument lets callers enforce specific GraphQLMeta guards
    (``history`` when listing audit trails, ``paginated`` otherwise).
    """
    result_model = result_model or model
    filter_model = result_model or model
    model_type = self.type_generator.generate_object_type(result_model)
    model_name = result_model.__name__.lower()

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
        ordering_config = type(
            "OrderingConfig", (), {"allowed": [], "default": []}
        )()

    @optimize_query()
    def resolver(
        root: Any, info: graphene.ResolveInfo, **kwargs
    ) -> PaginatedConnection:
        manager = getattr(model, manager_name)
        queryset = manager.all()
        graphql_meta.ensure_operation_access(operation_name, info=info)

        try:
            page = int(kwargs.get("page", 1))
        except Exception:
            page = 1
        try:
            per_page = int(
                kwargs.get("per_page", self.settings.default_page_size)
            )
        except Exception:
            per_page = self.settings.default_page_size
        per_page = max(1, min(per_page, self.settings.max_page_size))

        # Apply query optimization first
        queryset = self.optimizer.optimize_queryset(queryset, info, model)

        # Apply advanced filtering (same as list queries)
        filters = kwargs.get("filters")
        if filters:
            queryset = self.filter_generator.apply_complex_filters(
                queryset, filters
            )

        # Apply basic filtering (same as list queries)
        basic_filters = {
            k: v
            for k, v in kwargs.items()
            if k not in ["filters", "order_by", "page", "per_page", "include"]
        }
        if basic_filters and filter_class:
            filterset = filter_class(basic_filters, queryset)
            if filterset.is_valid():
                queryset = filterset.qs
            else:
                # If filterset is invalid, return empty result
                class EmptyPaginationInfo:
                    def __init__(self):
                        self.total_count = 0
                        self.page_count = 0
                        self.current_page = 1
                        self.per_page = per_page
                        self.has_next_page = False
                        self.has_previous_page = False

                class EmptyPaginatedResult:
                    def __init__(self):
                        self.items = []
                        self.page_info = EmptyPaginationInfo()

                return EmptyPaginatedResult()

        # Apply ordering (same as list queries)
        items: Optional[List[Any]] = None
        order_by = self._normalize_ordering_specs(
            kwargs.get("order_by"), ordering_config
        )
        if order_by:
            queryset, order_by = self._apply_count_annotations_for_ordering(
                queryset, model, order_by
            )
            db_specs, prop_specs = self._split_order_specs(model, order_by)
            if db_specs:
                queryset = queryset.order_by(*db_specs)
            if prop_specs:
                prop_limit = getattr(
                    self.settings, "max_property_ordering_results", None
                )
                if prop_limit:
                    max_items = min(prop_limit, page * per_page)
                    queryset = queryset[:max_items]
                items = list(queryset)
                items = self._apply_property_ordering(items, prop_specs)

        # Calculate pagination values
        if items is not None:
            total_count = len(items)
        else:
            total_count = queryset.count()
        page_count = (total_count + per_page - 1) // per_page

        # Ensure page is within valid range
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

    # Define arguments for the query
    arguments = {
        "page": graphene.Int(description="Page number (1-based)", default_value=1),
        "per_page": graphene.Int(
            description="Number of records per page",
            default_value=self.settings.default_page_size,
        ),
    }

    # Add complex filtering argument (same as list queries)
    filter_class = self.filter_generator.generate_filter_set(filter_model)
    complex_filter_input = self.filter_generator.generate_complex_filter_input(
        filter_model
    )

    arguments["filters"] = graphene.Argument(
        complex_filter_input,
        description="Advanced filtering with AND, OR, NOT operations",
    )

    # Add basic filtering arguments if filter class is available (same as list queries)
    if filter_class:
        for name, field in filter_class.base_filters.items():
            # Only expose 'quick' and 'include' filters as direct arguments
            if name not in ["quick", "include"]:
                continue

            field_type = graphene.String  # Default to String

            # Map filter types to GraphQL types (same logic as list queries)
            if hasattr(field, "field_class"):
                if (
                    "Number" in field.__class__.__name__
                    or "Integer" in field.__class__.__name__
                ):
                    field_type = graphene.Float
                elif "Boolean" in field.__class__.__name__:
                    field_type = graphene.Boolean
                elif "Date" in field.__class__.__name__:
                    field_type = graphene.Date

            # Handle ModelMultipleChoiceFilter for __in filters
            if (
                "ModelMultipleChoiceFilter" in field.__class__.__name__
                or name.endswith("__in")
            ):
                # For __in filters, use List of appropriate type
                if (
                    "Number" in field.__class__.__name__
                    or "Integer" in field.__class__.__name__
                ):
                    field_type = graphene.List(graphene.Float)
                else:
                    field_type = graphene.List(graphene.String)

            arguments[name] = graphene.Argument(
                field_type,
                description=getattr(field, "help_text", f"Filter by {name}"),
            )

    # Add ordering arguments (same as list queries)
    if self.settings.enable_ordering:
        order_desc = "Fields to order by (prefix with - for descending)"
        if ordering_config.allowed:
            order_desc += f". Allowed: {', '.join(ordering_config.allowed)}"
        arguments["order_by"] = graphene.List(
            graphene.String,
            description=order_desc,
            default_value=get_default_ordering(ordering_config),
        )

    return graphene.Field(
        PaginatedConnection,
        args=arguments,
        resolver=resolver,
        description=f"Retrieve a paginated list of {model_name} instances using {manager_name} manager",
    )

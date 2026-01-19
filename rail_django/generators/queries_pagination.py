"""
Paginated query builder helpers.
"""

import logging

from typing import Any, List, Optional, Type

import graphene
from django.db import models

from ..core.meta import get_model_graphql_meta
from ..extensions.optimization import optimize_query
from .queries_ordering import get_default_ordering

logger = logging.getLogger(__name__)


def _get_nested_filter_generator(schema_name: str):
    """Lazy import to avoid circular dependencies."""
    from .filter_inputs import NestedFilterInputGenerator
    return NestedFilterInputGenerator(schema_name=schema_name)


def _get_nested_filter_applicator(schema_name: str):
    """Lazy import to avoid circular dependencies."""
    from .filter_inputs import NestedFilterApplicator
    return NestedFilterApplicator(schema_name=schema_name)


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
    model: type[models.Model],
    manager_name: str = "objects",
    result_model: Optional[type[models.Model]] = None,
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

    # Generate filter class and nested filter components BEFORE resolver
    # so they are available in the resolver's closure scope
    filter_class = self.filter_generator.generate_filter_set(filter_model)

    nested_where_input = None
    nested_filter_applicator = None
    try:
        nested_generator = _get_nested_filter_generator(self.schema_name)
        nested_where_input = nested_generator.generate_where_input(filter_model)
        nested_filter_applicator = _get_nested_filter_applicator(self.schema_name)
    except Exception as e:
        logger.warning(f"Could not generate nested filter for {filter_model.__name__}: {e}")

    @optimize_query()
    def resolver(
        root: Any, info: graphene.ResolveInfo, **kwargs
    ) -> PaginatedConnection:
        self._enforce_model_permission(info, model, operation_name, graphql_meta)
        graphql_meta.ensure_operation_access(operation_name, info=info)
        manager = getattr(model, manager_name)
        queryset = manager.all()
        queryset = self._apply_tenant_scope(
            queryset, info, model, operation=operation_name
        )

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

        # Apply saved filter
        saved_filter_name_or_id = kwargs.get("savedFilter")
        where = kwargs.get("where")
        
        if saved_filter_name_or_id and nested_filter_applicator:
            try:
                from ..saved_filter import SavedFilter
                # Try to find by ID first, then name
                saved = None
                if str(saved_filter_name_or_id).isdigit():
                    saved = SavedFilter.objects.filter(pk=saved_filter_name_or_id).first()
                if not saved:
                    # Filter by name, model_name and owner/public
                    user = info.context.user if hasattr(info.context, "user") else None
                    q = models.Q(name=saved_filter_name_or_id, model_name=model.__name__)
                    if user and user.is_authenticated:
                        q &= (models.Q(is_shared=True) | models.Q(created_by=user))
                    else:
                        q &= models.Q(is_shared=True)
                    saved = SavedFilter.objects.filter(q).first()

                if saved:
                    # Update usage stats
                    SavedFilter.objects.filter(pk=saved.pk).update(
                        use_count=models.F("use_count") + 1,
                        last_used_at=models.functions.Now()
                    )
                    
                    saved_where = saved.filter_json
                    if saved_where:
                        # User provided 'where' overrides saved filter
                        if where:
                            # Ensure where is a dict before merging
                            if not isinstance(where, dict):
                                try:
                                    where = dict(where)
                                except Exception:
                                    where = {}
                            # Use apply_presets logic which merges deep
                            where = nested_filter_applicator._deep_merge(saved_where, where)
                        else:
                            where = saved_where
            except Exception as e:
                logger.warning(f"Failed to apply saved filter '{saved_filter_name_or_id}': {e}")

        # Apply nested 'where' filtering (Prisma/Hasura style)
        presets = kwargs.get("presets")
        include_ids = kwargs.get("include")

        if presets and nested_filter_applicator:
            # Apply presets if available
            if where is None:
                where = {}
            # Ensure where is a dict
            if not isinstance(where, dict):
                 try:
                    where = dict(where)
                 except Exception:
                     pass
            where = nested_filter_applicator.apply_presets(where, presets, model)

        if include_ids:
            if where is None:
                where = {}
            elif not isinstance(where, dict):
                try:
                    where = dict(where)
                except Exception:
                    where = {"AND": [where]}
            merged_include = []
            existing_include = where.get("include")
            if existing_include:
                if isinstance(existing_include, (list, tuple, set)):
                    merged_include.extend(existing_include)
                else:
                    merged_include.append(existing_include)
            if isinstance(include_ids, (list, tuple, set)):
                merged_include.extend(include_ids)
            else:
                merged_include.append(include_ids)
            where["include"] = merged_include

        if where and nested_filter_applicator:
            queryset = nested_filter_applicator.apply_where_filter(
                queryset, where, model
            )

        # Apply basic filtering (same as list queries)
        basic_filters = {
            k: v
            for k, v in kwargs.items()
            if k not in ["where", "order_by", "page", "per_page", "include"]
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
        items: Optional[list[Any]] = None
        uncapped_total: Optional[int] = None  # Track true total before property ordering cap
        order_by = self._normalize_ordering_specs(
            kwargs.get("order_by"), ordering_config
        )
        distinct_on = kwargs.get("distinct_on")

        if order_by:
            queryset, order_by = self._apply_count_annotations_for_ordering(
                queryset, model, order_by
            )
            db_specs, prop_specs = self._split_order_specs(model, order_by)

            if distinct_on:
                queryset = self._apply_distinct_on(queryset, distinct_on, db_specs)
            elif db_specs:
                queryset = queryset.order_by(*db_specs)

            if prop_specs:
                # Get true count BEFORE capping for accurate pagination
                uncapped_total = queryset.count()

                prop_limit = getattr(
                    self.settings, "max_property_ordering_results", None
                )
                warn_on_cap = bool(
                    getattr(self.settings, "property_ordering_warn_on_cap", True)
                )
                if prop_limit:
                    max_items = min(prop_limit, page * per_page)
                    if warn_on_cap and uncapped_total > prop_limit:
                        logger.warning(
                            "Property ordering on %s capped at %s results (total: %s).",
                            model.__name__,
                            max_items,
                            uncapped_total,
                        )
                    queryset = queryset[:max_items]
                items = list(queryset)
                items = self._apply_property_ordering(items, prop_specs)
        elif distinct_on:
             # Distinct on without explicit ordering - requires implicit ordering to match distinct fields
             queryset = self._apply_distinct_on(queryset, distinct_on, [])

        # Calculate pagination values
        # Use uncapped_total if property ordering was applied, otherwise count normally
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
        # For empty results, keep page=1 for consistent UX
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

    # Define arguments for the query
    arguments = {
        "page": graphene.Int(description="Page number (1-based)", default_value=1),
        "per_page": graphene.Int(
            description="Number of records per page",
            default_value=self.settings.default_page_size,
        ),
    }

    # Use nested_where_input generated earlier (before resolver)
    if nested_where_input:
        arguments["where"] = graphene.Argument(
            nested_where_input,
            description="Nested filtering with typed field inputs (Prisma/Hasura style)",
        )
        
        # Add presets argument
        arguments["presets"] = graphene.Argument(
            graphene.List(graphene.String),
            description="List of filter presets to apply",
        )

        # Add savedFilter argument
        arguments["savedFilter"] = graphene.Argument(
            graphene.String,
            description="Name or ID of a saved filter to apply",
        )

    # Add basic filtering arguments if filter class is available (same as list queries)
    if filter_class:
        for name, field in filter_class.base_filters.items():
            # Only expose 'quick' and 'include' filters as direct arguments
            if name not in ["quick", "include"]:
                continue

            if name == "include":
                field_type = graphene.List(graphene.ID)
            else:
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

        arguments["distinct_on"] = graphene.List(
            graphene.String,
            description="Distinct by fields (Postgres DISTINCT ON). Must match prefix of order_by.",
        )

    return graphene.Field(
        PaginatedConnection,
        args=arguments,
        resolver=resolver,
        description=f"Retrieve a paginated list of {model_name} instances using {manager_name} manager",
    )

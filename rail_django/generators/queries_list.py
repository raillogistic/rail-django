"""
Single and list query builders.
"""

import logging

from typing import Any, List, Optional, Type, Union

import graphene
from django.db import models

try:
    from graphene_django.filter import DjangoFilterConnectionField  # type: ignore
except Exception:
    DjangoFilterConnectionField = None

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

def generate_single_query(
    self, model: type[models.Model], manager_name: str = "objects"
) -> graphene.Field:
    """
    Generate a single object query for a model using the specified manager.
    For polymorphic models, uses the base model type with polymorphic_type field
    to identify the specific subclass instead of union types.
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
    self, model: type[models.Model], manager_name: str = "objects"
) -> Union[graphene.List, DjangoFilterConnectionField]:
    """
    Generates a query field for retrieving a list of model instances using the specified manager.
    For polymorphic models, returns the base model type to allow querying all instances.
    Supports advanced filtering, pagination, and ordering.

    Supports nested Prisma/Hasura-style filtering with typed inputs (e.g., name: { icontains: "..." }).
    """
    model_type = self.type_generator.generate_object_type(model)
    model_name = model.__name__.lower()
    graphql_meta = get_model_graphql_meta(model)
    ordering_config = getattr(graphql_meta, "ordering_config", None)
    if ordering_config is None:
        ordering_config = type(
            "OrderingConfig", (), {"allowed": [], "default": []}
        )()

    # Generate filter classes
    filter_class = self.filter_generator.generate_filter_set(model)
    nested_where_input = None
    nested_filter_applicator = None

    # Generate nested filter input (Prisma/Hasura style)
    try:
        nested_generator = _get_nested_filter_generator(self.schema_name)
        nested_where_input = nested_generator.generate_where_input(model)
        nested_filter_applicator = _get_nested_filter_applicator(self.schema_name)
    except Exception as e:
        logger.warning(f"Could not generate nested filter for {model.__name__}: {e}")

    if self.settings.use_relay and DjangoFilterConnectionField is not None:
        # Use Relay connection for cursor-based pagination
        @optimize_query()
        def resolver(root: Any, info: graphene.ResolveInfo, **kwargs):
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
            resolver=resolver,
            description=f"Retrieve a list of {model_name} instances with pagination using {manager_name} manager",
        )

    @optimize_query()
    def resolver(
        root: Any, info: graphene.ResolveInfo, **kwargs
    ) -> list[models.Model]:
        self._enforce_model_permission(info, model, "list", graphql_meta)
        graphql_meta.ensure_operation_access("list", info=info)
        manager = getattr(model, manager_name)
        queryset = manager.all()
        queryset = self._apply_tenant_scope(
            queryset, info, model, operation="list"
        )

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
                            if where is None:
                                where = {}
                            if not isinstance(where, dict):
                                try:
                                    where = dict(where)
                                except Exception:
                                    pass
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
                     # This might happen if 'where' is a Graphene InputObjectType that hasn't been converted to dict yet?
                     # Graphene usually passes dicts for inputs.
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

        # Apply basic filtering
        basic_filters = {
            k: v
            for k, v in kwargs.items()
            if k not in ["where", "order_by", "offset", "limit", "include"]
        }
        if basic_filters and filter_class:
            filterset = filter_class(basic_filters, queryset)
            if filterset.is_valid():
                queryset = filterset.qs
            else:
                # If filterset is invalid, return empty queryset
                return []

        # Apply ordering
        items: Optional[list[Any]] = None
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
                prop_limit = getattr(
                    self.settings, "max_property_ordering_results", None
                )
                warn_on_cap = bool(
                    getattr(self.settings, "property_ordering_warn_on_cap", True)
                )
                if prop_limit:
                    requested_limit = kwargs.get("limit")
                    max_items = min(prop_limit, (requested_limit or prop_limit))
                    if (
                        warn_on_cap
                        and requested_limit
                        and requested_limit > prop_limit
                    ):
                        logger.warning(
                            "Property ordering on %s capped at %s results (requested %s).",
                            model.__name__,
                            max_items,
                            requested_limit,
                        )
                    queryset = queryset[:max_items]
                items = list(queryset)
                items = self._apply_property_ordering(items, prop_specs)
        elif distinct_on:
             # Distinct on without explicit ordering - requires implicit ordering to match distinct fields
             queryset = self._apply_distinct_on(queryset, distinct_on, [])

        # Apply pagination
        if self.settings.enable_pagination:
            offset = kwargs.get("offset") or 0
            limit = kwargs.get("limit") or self.settings.default_page_size
            if items is None:
                queryset = queryset[offset : offset + limit]
                items = list(queryset)
            else:
                items = items[offset : offset + limit]
        elif items is None:
            items = list(queryset)

        items = self._apply_field_masks(items, info, model)
        return items

    arguments = {}

    # Add nested-style where argument (Prisma/Hasura style)
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

    # Add basic filtering arguments if filter class is available
    if filter_class:
        for name, field in filter_class.base_filters.items():
            # Only expose 'quick' and 'include' filters as direct arguments
            if name not in ["quick", "include"]:
                continue

            if name == "include":
                field_type = graphene.List(graphene.ID)
            else:
                field_type = graphene.String  # Default to String

            # Map filter types to GraphQL types
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

    if "include" not in arguments:
        arguments["include"] = graphene.Argument(
            graphene.List(graphene.ID),
            description="Include specific IDs regardless of other filters",
        )

    # Add pagination arguments
    if self.settings.enable_pagination:
        arguments.update(
            {
                "offset": graphene.Int(description="Number of records to skip"),
                "limit": graphene.Int(
                    description="Number of records to return"
                ),
            }
        )

    # Add ordering arguments
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

    return graphene.List(
        model_type,
        args=arguments,
        resolver=resolver,
        description=f"Retrieve a list of {model_name} instances using {manager_name} manager",
    )

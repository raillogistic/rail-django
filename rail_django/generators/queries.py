"""
Query Generation System for Django GraphQL Auto-Generation

This module provides the QueryGenerator class, which is responsible for creating
GraphQL queries for Django models, including single object, list, and filtered queries.
"""

from typing import Any, Dict, List, Optional, Type, Union

import graphene
from django.apps import apps
from django.db import models
from django.db.models import Count, ForeignKey, ManyToManyField, OneToOneField, Q
from graphene_django import DjangoObjectType

# Resilient import: DjangoFilterConnectionField may not exist in some graphene-django versions
try:
    from graphene_django.filter import DjangoFilterConnectionField  # type: ignore
except Exception:
    DjangoFilterConnectionField = None  # Fallback when Relay field is unavailable

from ..conf import get_query_generator_settings
from ..core.meta import get_model_graphql_meta
from ..core.performance import get_query_optimizer
from ..core.security import get_authz_manager
from ..core.settings import QueryGeneratorSettings
from ..security.field_permissions import mask_sensitive_fields
from ..extensions.optimization import (
    QueryOptimizationConfig,
    get_optimizer,
    get_performance_monitor,
    optimize_query,
)
from .filters import AdvancedFilterGenerator
from .inheritance import inheritance_handler
from .types import TypeGenerator
from .introspector import ModelIntrospector

# Default ordering applied when no explicit ordering is provided.
DEFAULT_ORDERING_FALLBACK = ["-id"]


class PaginationInfo(graphene.ObjectType):
    """
    Informations de pagination pour les requêtes GraphQL paginées.

    Cette classe est définie au niveau du module pour permettre la sérialisation
    (pickle) lors de la mise en cache des résultats.
    """

    total_count = graphene.Int(description="Total number of records")
    page_count = graphene.Int(description="Total number of pages")
    current_page = graphene.Int(description="Current page number")
    per_page = graphene.Int(description="Number of records per page")
    has_next_page = graphene.Boolean(description="Whether there is a next page")
    has_previous_page = graphene.Boolean(description="Whether there is a previous page")


class PaginatedResult:
    """
    Classe de résultat paginé pour les requêtes GraphQL.

    Cette classe est définie au niveau du module pour permettre la sérialisation
    (pickle) lors de la mise en cache des résultats.
    """

    def __init__(self, items, page_info):
        self.items = items
        self.page_info = page_info


class GroupingBucketType(graphene.ObjectType):
    """
    Bucket de regroupement retourné par les requêtes de groupement.
    """

    key = graphene.String(required=True, description="Valeur brute du groupe")
    label = graphene.String(
        required=True,
        description="Libellé lisible pour le groupe (nom de relation ou choix)",
    )
    count = graphene.Int(required=True, description="Nombre d'enregistrements")


class QueryGenerator:
    """
    Generates GraphQL queries for Django models.

    This class supports:
    - Single object queries with filtering
    - List queries with pagination and filtering
    - Advanced filtering with nested field support
    - Performance optimization and monitoring
    - Multi-schema query generation
    - Security and authorization integration
    - Query caching and complexity analysis
    """

    def __init__(
        self,
        type_generator: TypeGenerator,
        settings: Optional[QueryGeneratorSettings] = None,
        schema_name: str = "default",
    ):
        """
        Initialize the QueryGenerator.

        Args:
            type_generator: TypeGenerator instance for creating GraphQL types
            settings: Query generator settings or None for defaults
            schema_name: Name of the schema for multi-schema support
        """
        self.type_generator = type_generator
        self.schema_name = schema_name

        # Use hierarchical settings if no explicit settings provided
        if settings is None:
            self.settings = QueryGeneratorSettings.from_schema(schema_name)
        else:
            self.settings = settings

        # Initialize performance and security components
        self.query_optimizer = get_query_optimizer(schema_name)
        self.authorization_manager = get_authz_manager(schema_name)

        self._query_registry: Dict[Type[models.Model], Dict[str, Any]] = {}
        self._filter_generator = AdvancedFilterGenerator()
        self._query_fields: Dict[str, graphene.Field] = {}

        # Initialize performance optimization
        self.optimizer = get_optimizer()
        self.performance_monitor = get_performance_monitor()

    @property
    def filter_generator(self):
        """Access to the filter generator instance."""
        return self._filter_generator

    def _is_historical_model(self, model: Type[models.Model]) -> bool:
        """Return True if the model corresponds to a django-simple-history model."""
        try:
            name = getattr(model, "__name__", "")
            module = getattr(model, "__module__", "")
        except Exception:
            return False
        if name.startswith("Historical"):
            return True
        if "simple_history" in module:
            return True
        return False

    def get_manager_queryset_model(
        self, model: Type[models.Model], manager_name: str
    ) -> Optional[Type[models.Model]]:
        """Return the model class produced by the given manager's queryset."""
        try:
            manager = getattr(model, manager_name)
        except Exception:
            return None

        if manager is None:
            return None

        queryset_model: Optional[Type[models.Model]] = None
        try:
            queryset = manager.get_queryset()
            queryset_model = getattr(queryset, "model", None)
        except Exception:
            try:
                queryset = manager.all()
                queryset_model = getattr(queryset, "model", None)
            except Exception:
                queryset_model = None

        if queryset_model is None:
            queryset_model = getattr(manager, "model", None)

        return queryset_model

    def is_history_related_manager(
        self, model: Type[models.Model], manager_name: str
    ) -> bool:
        """Return True when the given manager is the HistoricalRecords manager."""
        manager = None
        try:
            manager = getattr(model, manager_name, None)
        except Exception:
            manager = None

        if manager is None:
            return False

        manager_model = self.get_manager_queryset_model(model, manager_name)
        if manager_model is not None and self._is_historical_model(manager_model):
            return True

        manager_class = getattr(manager, "__class__", None)
        class_name = getattr(manager_class, "__name__", "").lower()
        class_module = getattr(manager_class, "__module__", "")

        if "simple_history" in class_module:
            return True
        if "historical" in class_name or "history" in class_name:
            return True

        return manager_name.lower().startswith("history")

    def _apply_field_masks(
        self,
        data: Union[models.Model, List[models.Model]],
        info: graphene.ResolveInfo,
        model: Type[models.Model],
    ):
        """Hide or mask fields based on field-level permissions."""
        context_user = getattr(getattr(info, "context", None), "user", None)
        if (
            not context_user
            or not getattr(context_user, "is_authenticated", False)
            or context_user.is_superuser
        ):
            return data

        def mask_instance(instance: models.Model):
            if not isinstance(instance, models.Model):
                return instance
            field_defs = list(instance._meta.concrete_fields)
            field_names = [field.name for field in field_defs]
            snapshot = {name: getattr(instance, name, None) for name in field_names}
            masked = mask_sensitive_fields(
                snapshot, context_user, model, instance=instance
            )
            for field in field_defs:
                name = field.name
                attname = getattr(field, "attname", name)
                if name in masked:
                    instance.__dict__[attname] = masked[name]
                else:
                    instance.__dict__[attname] = None
            return instance

        if isinstance(data, list):
            return [mask_instance(item) for item in data]
        return mask_instance(data)

    def _apply_count_annotations_for_ordering(
        self,
        queryset: models.QuerySet,
        model: Type[models.Model],
        order_by: List[str],
    ) -> (models.QuerySet, List[str]):
        """
        Annotate queryset for any order_by fields that request <relation>_count or <relation>__count.
        Supports forward ManyToMany and reverse relations using accessor names.
        Returns updated queryset and a possibly transformed order_by list.
        """
        if not order_by:
            return queryset, order_by

        new_order_by: List[str] = []
        annotated_aliases: set = set()

        for spec in order_by:
            desc = spec.startswith("-")
            field = spec[1:] if desc else spec

            base = None
            alias = None

            if field.endswith("_count"):
                base = field[: -len("_count")]
                alias = f"{base}_count"
            elif field.endswith("_count"):
                base = field[: -len("_count")]
                alias = field

            if base:
                # Determine if base is a ManyToMany relation to apply distinct
                is_m2m = False
                try:
                    # Check forward fields
                    for f in model._meta.get_fields():
                        if getattr(f, "name", None) == base:
                            try:
                                from django.db.models.fields.related import (
                                    ManyToManyField,
                                )
                                from django.db.models.fields.reverse_related import (
                                    ManyToManyRel,
                                )

                                is_m2m = isinstance(f, ManyToManyField) or isinstance(
                                    f, ManyToManyRel
                                )
                            except Exception:
                                pass
                            break
                    else:
                        # Check reverse relations by accessor name
                        if hasattr(model._meta, "related_objects"):
                            from django.db.models.fields.reverse_related import (
                                ManyToManyRel,
                            )

                            for rel in model._meta.related_objects:
                                if rel.get_accessor_name() == base:
                                    is_m2m = isinstance(rel, ManyToManyRel)
                                    break
                except Exception:
                    # If introspection fails, default to non-distinct
                    is_m2m = False

                if alias and alias not in annotated_aliases:
                    try:
                        queryset = queryset.annotate(
                            **{alias: Count(base, distinct=is_m2m)}
                        )
                        annotated_aliases.add(alias)
                    except Exception:
                        try:
                            queryset = queryset.annotate(**{alias: Count(base)})
                            annotated_aliases.add(alias)
                        except Exception:
                            # If annotation fails, fall back to original spec
                            alias = None

                if alias:
                    new_order_by.append(f"-{alias}" if desc else alias)
                else:
                    new_order_by.append(spec)
            else:
                new_order_by.append(spec)

        return queryset, new_order_by

    def _normalize_ordering_specs(
        self, order_by: Optional[List[str]], ordering_config
    ) -> List[str]:
        """
        Apply default ordering and validate specs against GraphQLMeta configuration.
        """

        normalized = [spec for spec in (order_by or []) if spec]
        if not normalized:
            if ordering_config.default:
                normalized = list(ordering_config.default)
            else:
                normalized = list(DEFAULT_ORDERING_FALLBACK)

        allowed = getattr(ordering_config, "allowed", None) or []
        if allowed and normalized:
            invalid = [spec for spec in normalized if spec.lstrip("-") not in allowed]
            if invalid:
                raise ValueError(
                    f"Unsupported ordering fields for {self.schema_name}: {', '.join(invalid)}"
                )

        return normalized

    def _split_order_specs(
        self, model: Type[models.Model], order_by: List[str]
    ) -> (List[str], List[str]):
        """Split order_by specs into DB fields and property-based fields."""
        if not order_by:
            return [], []
        try:
            introspector = ModelIntrospector(model)
            prop_names = set(introspector.properties.keys())
        except Exception:
            prop_names = set()
        db_specs: List[str] = []
        prop_specs: List[str] = []
        for spec in order_by:
            name = spec[1:] if spec.startswith("-") else spec
            if name in prop_names:
                prop_specs.append(spec)
            else:
                db_specs.append(spec)
        return db_specs, prop_specs

    def _safe_prop_value(self, obj: Any, prop_name: str):
        """Return a comparable key for property sorting, nulls last."""
        try:
            val = getattr(obj, prop_name)
        except Exception:
            val = None
        if val is None:
            return (1, None)
        # If value is not directly comparable, fall back to string representation
        try:
            _ = val < val  # type check to ensure comparable
            return (0, val)
        except Exception:
            return (0, str(val))

    def _apply_property_ordering(
        self, items: List[Any], prop_specs: List[str]
    ) -> List[Any]:
        """Apply stable multi-key sort on a Python list based on property specs."""
        if not prop_specs:
            return items
        # Stable sort: apply from last to first
        for spec in reversed(prop_specs):
            desc = spec.startswith("-")
            name = spec[1:] if desc else spec
            try:
                items.sort(key=lambda o: self._safe_prop_value(o, name), reverse=desc)
            except Exception:
                # If sorting fails, skip this spec
                continue
        return items

    def generate_single_query(
        self, model: Type[models.Model], manager_name: str = "objects"
    ) -> graphene.Field:
        """
        Generate a single object query for a model using the specified manager.
        For polymorphic models, uses the base model type with polymorphic_type field
        to identify the specific subclass instead of union types.

        Args:
            model: Django model class
            manager_name: Name of the manager to use (defaults to "objects")
        """
        # Always use the base model type for single queries
        # The polymorphic_type field will indicate the actual class
        model_type = self.type_generator.generate_object_type(model)

        graphql_meta = get_model_graphql_meta(model)

        def resolve_single(root, info, id):
            """Resolver for single object queries."""
            try:
                manager = getattr(model, manager_name)
                instance = manager.get(pk=id)
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
    ) -> Union[graphene.List, DjangoFilterConnectionField]:
        """
        Generates a query field for retrieving a list of model instances using the specified manager.
        For polymorphic models, returns the base model type to allow querying all instances.
        Supports advanced filtering, pagination, and ordering.

        Args:
            model: Django model class
            manager_name: Name of the manager to use (defaults to "objects")
        """

        # Regular list query for non-polymorphic models
        model_type = self.type_generator.generate_object_type(model)
        model_name = model.__name__.lower()
        graphql_meta = get_model_graphql_meta(model)
        ordering_config = getattr(graphql_meta, "ordering_config", None)
        if ordering_config is None:
            ordering_config = type(
                "OrderingConfig", (), {"allowed": [], "default": []}
            )()
        filter_class = self.filter_generator.generate_filter_set(model)
        complex_filter_input = self.filter_generator.generate_complex_filter_input(
            model
        )
        if self.settings.use_relay and DjangoFilterConnectionField is not None:
            # Use Relay connection for cursor-based pagination
            return DjangoFilterConnectionField(
                model_type,
                filterset_class=filter_class,
                description=f"Retrieve a list of {model_name} instances with pagination using {manager_name} manager",
            )
        else:

            @optimize_query()
            def resolver(
                root: Any, info: graphene.ResolveInfo, **kwargs
            ) -> List[models.Model]:
                manager = getattr(model, manager_name)
                queryset = manager.all()
                graphql_meta.ensure_operation_access("list", info=info)

                # Apply query optimization first
                queryset = self.optimizer.optimize_queryset(queryset, info, model)

                # Apply advanced filtering
                filters = kwargs.get("filters")
                if filters:
                    queryset = self.filter_generator.apply_complex_filters(
                        queryset, filters
                    )

                # Apply basic filtering
                basic_filters = {
                    k: v
                    for k, v in kwargs.items()
                    if k not in ["filters", "order_by", "limit", "offset", "include"]
                }
                if basic_filters and filter_class:
                    filterset = filter_class(basic_filters, queryset)
                    queryset = filterset.qs

                # Apply ordering
                order_by = self._normalize_ordering_specs(
                    kwargs.get("order_by"), ordering_config
                )
                items: Optional[List[Any]] = None
                if order_by:
                    queryset, order_by = self._apply_count_annotations_for_ordering(
                        queryset, model, order_by
                    )
                    db_specs, prop_specs = self._split_order_specs(model, order_by)
                    if db_specs:
                        queryset = queryset.order_by(*db_specs)
                    if prop_specs:
                        items = list(queryset)
                        items = self._apply_property_ordering(items, prop_specs)

                # Apply pagination
                offset = kwargs.get("offset")
                limit = kwargs.get("limit")
                if items is not None:
                    # In-memory pagination on sorted list
                    if offset is not None and limit is not None:
                        items = items[offset : offset + limit]
                    elif limit is not None:
                        items = items[:limit]
                    return self._apply_field_masks(items, info, model)
                else:
                    if offset is not None and limit is not None:
                        queryset = queryset[offset : offset + limit]
                    elif limit is not None:
                        queryset = queryset[:limit]
                    return self._apply_field_masks(list(queryset), info, model)

            # Define arguments for the query
            arguments = {}

            # Add complex filtering argument
            arguments["filters"] = graphene.Argument(
                complex_filter_input,
                description="Advanced filtering with AND, OR, NOT operations",
            )

            # Add basic filtering arguments if filter class is available
            if filter_class:
                for name, field in filter_class.base_filters.items():
                    # Only expose 'quick' and 'include' filters as direct arguments
                    if name not in ["quick", "include"]:
                        continue

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

                    # Special-case the global 'include' filter to use [ID!] as requested
                    if name == "include":
                        # GraphQL list of non-null ID elements
                        try:
                            field_type = graphene.List(graphene.NonNull(graphene.ID))
                        except Exception:
                            # Fallback if NonNull is unavailable in environment
                            field_type = graphene.List(graphene.ID)

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
                    default_value=ordering_config.default or DEFAULT_ORDERING_FALLBACK,
                )

            return graphene.List(
                model_type,
                args=arguments,
                resolver=resolver,
                description=f"Retrieve a list of {model_name} instances using {manager_name} manager",
            )

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

        Args:
            model: Django model class
            manager_name: Name of the manager to use (defaults to "objects")
            result_model: Optional model class describing the actual queryset items.
            operation_name: Guard name to enforce via GraphQLMeta.
        """
        result_model = result_model or model
        filter_model = result_model or model
        model_type = self.type_generator.generate_object_type(result_model)
        model_name = result_model.__name__.lower()

        # Create a pagination info type (using module-level class)
        # PaginationInfo is now defined at module level for pickle support

        # Create a model-specific connection type for the paginated results
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
                    items = list(queryset)
                    items = self._apply_property_ordering(items, prop_specs)

            # Calculate pagination values
            page = kwargs.get("page", 1)
            per_page = kwargs.get("per_page", self.settings.default_page_size)
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
            # Return a simple object with the required attributes
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
                default_value=ordering_config.default or DEFAULT_ORDERING_FALLBACK,
            )

        return graphene.Field(
            PaginatedConnection,
            args=arguments,
            resolver=resolver,
            description=f"Retrieve a paginated list of {model_name} instances using {manager_name} manager",
        )

    def add_filtering_support(
        self, query: graphene.Field, model: Type[models.Model]
    ) -> graphene.Field:
        """
        Adds filtering capabilities to an existing query field.
        """
        filter_class = self.type_generator.generate_filter_type(model)
        if not filter_class:
            return query

        # Add filter arguments to the query
        for name, field in filter_class.base_filters.items():
            query.args[name] = graphene.Argument(
                self.type_generator.FIELD_TYPE_MAP.get(type(field), graphene.String)
            )

        # Wrap the original resolver to apply filters
        original_resolver = query.resolver

        def filtered_resolver(root: Any, info: graphene.ResolveInfo, **kwargs):
            result = original_resolver(root, info, **kwargs)
            if isinstance(result, models.QuerySet):
                filterset = filter_class(kwargs, result)
                return filterset.qs
            return result

        query.resolver = filtered_resolver
        return query

    def _resolve_group_by_field(
        self, model: Type[models.Model], path: str
    ) -> Optional[models.Field]:
        """
        Validate a group_by path against model fields and return the final field if valid.

        Rejects unknown segments and many-to-many paths to avoid ambiguous counts.
        """
        current_model = model
        final_field: Optional[models.Field] = None
        for segment in path.split("__"):
            try:
                final_field = current_model._meta.get_field(segment)
            except Exception:
                return None
            if isinstance(final_field, ManyToManyField):
                return None
            if isinstance(final_field, (ForeignKey, OneToOneField)) and getattr(
                final_field, "remote_field", None
            ):
                current_model = final_field.remote_field.model
            else:
                current_model = current_model
        return final_field

    def generate_grouping_query(
        self, model: Type[models.Model], manager_name: str = "objects"
    ) -> graphene.Field:
        """
        Generate a lightweight grouping query (counts per value) using the same filter inputs as list queries.

        Returns buckets keyed by the grouped value with a display label and count.
        """
        model_name = model.__name__.lower()
        graphql_meta = get_model_graphql_meta(model)
        filter_class = self.filter_generator.generate_filter_set(model)
        complex_filter_input = self.filter_generator.generate_complex_filter_input(
            model
        )
        max_buckets = getattr(self.settings, "max_grouping_buckets", 200) or 200

        @optimize_query()
        def resolver(root: Any, info: graphene.ResolveInfo, **kwargs):
            group_by: Optional[str] = kwargs.get("group_by")
            if not group_by:
                return []

            field = self._resolve_group_by_field(model, group_by)
            if field is None:
                return []

            limit = kwargs.get("limit") or max_buckets
            try:
                limit = int(limit)
            except Exception:
                limit = max_buckets
            limit = max(1, min(limit, max_buckets))

            manager = getattr(model, manager_name)
            queryset = manager.all()
            graphql_meta.ensure_operation_access("list", info=info)

            # Apply query optimization first
            queryset = self.optimizer.optimize_queryset(queryset, info, model)

            # Apply advanced filtering
            filters = kwargs.get("filters")
            if filters:
                queryset = self.filter_generator.apply_complex_filters(
                    queryset, filters
                )

            # Apply basic filtering
            basic_filters = {
                k: v
                for k, v in kwargs.items()
                if k
                not in [
                    "filters",
                    "group_by",
                    "order_by",
                    "limit",
                    "include",
                ]
            }
            if basic_filters and filter_class:
                filterset = filter_class(basic_filters, queryset)
                if filterset.is_valid():
                    queryset = filterset.qs
                else:
                    return []

            value_path = group_by
            queryset = queryset.values(value_path).annotate(total=Count("id"))

            order_by = kwargs.get("order_by") or "group"
            if order_by == "count":
                queryset = queryset.order_by("-total")
            elif order_by == "-count":
                queryset = queryset.order_by("total")
            elif order_by == "-group":
                queryset = queryset.order_by(f"-{value_path}")
            else:
                queryset = queryset.order_by(value_path)

            queryset = queryset[:limit]

            buckets = []
            for entry in queryset:
                raw_value = entry.get(value_path)
                label_value = raw_value
                if getattr(field, "choices", None):
                    label_value = dict(field.flatchoices).get(raw_value, raw_value)
                if raw_value is None:
                    label_value = "Non renseigné"
                elif isinstance(
                    field, (ForeignKey, OneToOneField)
                ) and raw_value is not None:
                    try:
                        related_model = field.remote_field.model
                        related_obj = (
                            related_model._default_manager.using(queryset.db)
                            .filter(pk=raw_value)
                            .first()
                        )
                        if related_obj:
                            label_value = str(related_obj)
                    except Exception:
                        label_value = label_value

                buckets.append(
                    GroupingBucketType(
                        key="__EMPTY__" if raw_value is None else str(raw_value),
                        label=str(label_value)
                        if label_value is not None
                        else "Non renseigné",
                        count=int(entry.get("total", 0) or 0),
                    )
                )

            return buckets

        arguments = {
            "group_by": graphene.Argument(
                graphene.String,
                required=True,
                description="Nom du champ pour le regroupement (chemin Django avec __ autorisé)",
            ),
            "order_by": graphene.Argument(
                graphene.String,
                required=False,
                description="Ordre de tri: group, -group, count, -count (défaut: group)",
            ),
            "limit": graphene.Argument(
                graphene.Int,
                required=False,
                description=f"Nombre max de groupes (défaut: {max_buckets}, max: {max_buckets})",
            ),
        }
        if complex_filter_input:
            arguments["filters"] = graphene.Argument(
                complex_filter_input,
                description="Filtres avancés identiques aux requêtes de liste",
            )
        if filter_class:
            for name, field in filter_class.base_filters.items():
                arguments[name] = graphene.Argument(
                    self.type_generator.FIELD_TYPE_MAP.get(
                        type(field), graphene.String
                    )
                )

        return graphene.Field(
            graphene.List(GroupingBucketType),
            args=arguments,
            resolver=resolver,
            description=f"Regroupement avec comptage pour {model_name} (manager {manager_name})",
        )

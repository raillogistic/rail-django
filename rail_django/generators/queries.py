"""
Query Generation System for Django GraphQL Auto-Generation

This module provides the QueryGenerator class, which is responsible for creating
GraphQL queries for Django models, including single object, list, and filtered queries.
"""

from typing import Any, Dict, List, Optional, Tuple, Type, Union

import graphene
from django.contrib.auth.models import AnonymousUser
from django.db import models
from graphql import GraphQLError

from ..core.security import get_authz_manager
from ..core.services import get_query_optimizer
from ..core.settings import QueryGeneratorSettings
from ..extensions.optimization import get_optimizer, get_performance_monitor
from ..security.field_permissions import mask_sensitive_fields
from .filter_inputs import AdvancedFilterGenerator
from .queries_grouping import (  # noqa: F401
    GroupingBucketType,
    generate_grouping_query as _generate_grouping_query,
)
from .queries_list import (
    generate_list_query as _generate_list_query,
    generate_single_query as _generate_single_query,
)
from .queries_ordering import (
    apply_count_annotations_for_ordering as _apply_count_annotations_for_ordering,
    apply_property_ordering as _apply_property_ordering,
    normalize_ordering_specs as _normalize_ordering_specs,
    safe_prop_value as _safe_prop_value,
    split_order_specs as _split_order_specs,
)
from .queries_pagination import (  # noqa: F401
    PaginatedResult,
    PaginationInfo,
    generate_paginated_query as _generate_paginated_query,
)
from .types import TypeGenerator
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

        self._query_registry: dict[type[models.Model], dict[str, Any]] = {}
        self._filter_generator = AdvancedFilterGenerator()
        self._query_fields: dict[str, graphene.Field] = {}

        # Initialize performance optimization
        self.optimizer = get_optimizer(schema_name)
        self.performance_monitor = get_performance_monitor(schema_name)

    def generate_introspection_queries(self) -> Dict[str, graphene.Field]:
        """Generate introspection queries like __filterSchema."""
        from ..extensions.metadata import FilterSchemaType, resolve_filter_schema
        
        return {
            "filterSchema": graphene.Field(
                FilterSchemaType,
                model=graphene.String(required=True),
                depth=graphene.Int(default_value=1),
                resolver=resolve_filter_schema,
                description="Introspect available filters for a model"
            )
        }

    @property
    def filter_generator(self):
        """Access to the filter generator instance."""
        return self._filter_generator

    def _is_historical_model(self, model: type[models.Model]) -> bool:
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
        self, model: type[models.Model], manager_name: str
    ) -> Optional[type[models.Model]]:
        """Return the model class produced by the given manager's queryset."""
        try:
            manager = getattr(model, manager_name)
        except Exception:
            return None

        if manager is None:
            return None

        queryset_model: Optional[type[models.Model]] = None
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
        self, model: type[models.Model], manager_name: str
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
        data: Union[models.Model, list[models.Model]],
        info: graphene.ResolveInfo,
        model: type[models.Model],
    ):
        """Hide or mask fields based on field-level permissions."""
        context_user = getattr(getattr(info, "context", None), "user", None)
        if context_user is None:
            context_user = AnonymousUser()
        if getattr(context_user, "is_superuser", False):
            return data

        def mask_instance(instance: models.Model):
            if not isinstance(instance, models.Model):
                return instance
            field_defs = list(instance._meta.concrete_fields)
            
            snapshot = {}
            for field in field_defs:
                # Optimization: For relation fields (ForeignKeys/OneToOne), use attname (the ID)
                # to avoid triggering a database query to fetch the related object.
                # We store it under field.name so permission rules match correctly.
                if field.is_relation and (field.many_to_one or field.one_to_one):
                    val = getattr(instance, field.attname, None)
                else:
                    val = getattr(instance, field.name, None)
                snapshot[field.name] = val

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
        model: type[models.Model],
        order_by: list[str],
    ) -> tuple[models.QuerySet, list[str]]:
        return _apply_count_annotations_for_ordering(queryset, model, order_by)

    def _apply_distinct_on(
        self,
        queryset: models.QuerySet,
        distinct_on: List[str],
        order_by: List[str],
    ) -> models.QuerySet:
        """Apply DISTINCT ON clause (Postgres only) or fallback."""
        from django.db import connection
        from django.db.models import F

        if connection.vendor == "postgresql":
            # Validate: distinct_on fields must be prefix of order_by
            # This is a Postgres requirement: SELECT DISTINCT ON (a) ... ORDER BY a, b
            # If explicit ordering is provided, it must start with the distinct fields.
            # If not, we might need to prepend them or rely on the caller to ensure it.
            
            # Here we assume order_by contains the full ordering specs.
            # If order_by is empty or doesn't match, Django/Postgres will raise an error.
            # However, to be safe, we can try to prepend distinct fields to order_by if not present?
            # But the caller (generate_list_query) passes db_specs as order_by.
            
            # Simple implementation: let Django handle the SQL generation.
            # Users must ensure order_by starts with distinct_on fields.
            return queryset.order_by(*order_by).distinct(*distinct_on)
        else:
            # Fallback: use subquery with window function
            from django.db.models import Window
            from django.db.models.functions import RowNumber

            partition_by = [F(f) for f in distinct_on]
            # Convert string order specs to expressions if needed, or just use them
            # _parse_order_by isn't available here directly, let's use F() for simple fields
            # or rely on the fact that order_by list strings work in order_by().
            
            # For Window functions in annotate, order_by needs to be F() expressions or similar
            # not just strings like "-created_at".
            
            # Simplified fallback for now: group by distinct fields and take first?
            # Window functions are the most robust way but require recent Django/DB support.
            
            try:
                window_ordering = []
                for o in order_by:
                    if o.startswith("-"):
                        window_ordering.append(F(o[1:]).desc())
                    else:
                        window_ordering.append(F(o).asc())

                annotated = queryset.annotate(
                    _row_num=Window(
                        expression=RowNumber(),
                        partition_by=partition_by,
                        order_by=window_ordering,
                    )
                )
                return annotated.filter(_row_num=1)
            except Exception:
                # If window functions fail (e.g. SQLite old version), log warning and return original
                # or maybe just distinct() if no args? But that's distinct ROW.
                return queryset

    def _normalize_ordering_specs(
        self, order_by: Optional[list[str]], ordering_config
    ) -> list[str]:
        return _normalize_ordering_specs(order_by, ordering_config, self.schema_name)

    def _split_order_specs(
        self, model: type[models.Model], order_by: list[str]
    ) -> tuple[list[str], list[str]]:
        return _split_order_specs(model, order_by)

    def _safe_prop_value(self, obj: Any, prop_name: str):
        return _safe_prop_value(obj, prop_name)

    def _apply_property_ordering(
        self, items: list[Any], prop_specs: list[str]
    ) -> list[Any]:
        return _apply_property_ordering(items, prop_specs)

    def _apply_tenant_scope(
        self,
        queryset: models.QuerySet,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "read",
    ) -> models.QuerySet:
        try:
            from ..extensions.multitenancy import apply_tenant_queryset
        except Exception:
            return queryset
        return apply_tenant_queryset(
            queryset,
            info,
            model,
            schema_name=self.schema_name,
            operation=operation,
        )

    def _enforce_tenant_access(
        self,
        instance: models.Model,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "read",
    ) -> None:
        try:
            from ..extensions.multitenancy import ensure_tenant_access
        except Exception:
            return
        ensure_tenant_access(
            instance, info, model, schema_name=self.schema_name, operation=operation
        )

    def _has_operation_guard(self, graphql_meta, operation: str) -> bool:
        guards = getattr(graphql_meta, "_operation_guards", None) or {}
        return operation in guards or "*" in guards

    def _build_model_permission_name(
        self, model: type[models.Model], codename: str
    ) -> str:
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        return f"{app_label}.{codename}_{model_name}"

    def _enforce_model_permission(
        self,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        operation: str,
        graphql_meta=None,
    ) -> None:
        if not getattr(
            self.authorization_manager.settings, "enable_authorization", True
        ):
            return
        if not getattr(self.settings, "require_model_permissions", True):
            return
        if graphql_meta is not None and self._has_operation_guard(
            graphql_meta, operation
        ):
            return

        user = getattr(getattr(info, "context", None), "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError("Authentication required")

        codename = getattr(self.settings, "model_permission_codename", "view")
        codename = str(codename or "").strip()
        if not codename:
            return

        permission_name = self._build_model_permission_name(model, codename)
        has_perm = getattr(user, "has_perm", None)
        if not callable(has_perm) or not has_perm(permission_name):
            raise GraphQLError(f"Permission required: {permission_name}")

    def generate_single_query(
        self, model: type[models.Model], manager_name: str = "objects"
    ) -> graphene.Field:
        return _generate_single_query(self, model, manager_name)

    def generate_list_query(
        self, model: type[models.Model], manager_name: str = "objects"
    ) -> Any:
        return _generate_list_query(self, model, manager_name)

    def generate_paginated_query(
        self,
        model: type[models.Model],
        manager_name: str = "objects",
        result_model: Optional[type[models.Model]] = None,
        operation_name: str = "paginated",
    ) -> graphene.Field:
        return _generate_paginated_query(
            self,
            model,
            manager_name=manager_name,
            result_model=result_model,
            operation_name=operation_name,
        )

    def add_filtering_support(
        self, query: graphene.Field, model: type[models.Model]
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
                result = self._apply_tenant_scope(
                    result, info, model, operation="list"
                )
                filterset = filter_class(kwargs, result)
                return filterset.qs
            return result

        query.resolver = filtered_resolver
        return query

    def generate_grouping_query(
        self, model: type[models.Model], manager_name: str = "objects"
    ) -> graphene.Field:
        return _generate_grouping_query(self, model, manager_name)

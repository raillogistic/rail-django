"""
Query Generation System for Django GraphQL Auto-Generation

This module provides the QueryGenerator class, which is responsible for creating
GraphQL queries for Django models, including single object, list, and filtered queries.
"""

from typing import Any, Dict, List, Optional, Tuple, Type, Union

import graphene
from django.contrib.auth.models import AnonymousUser
from django.db import models

from ..core.security import get_authz_manager
from ..core.services import get_query_optimizer
from ..core.settings import QueryGeneratorSettings
from ..extensions.optimization import get_optimizer, get_performance_monitor
from ..security.field_permissions import mask_sensitive_fields
from .filters import AdvancedFilterGenerator
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
                filterset = filter_class(kwargs, result)
                return filterset.qs
            return result

        query.resolver = filtered_resolver
        return query

    def generate_grouping_query(
        self, model: type[models.Model], manager_name: str = "objects"
    ) -> graphene.Field:
        return _generate_grouping_query(self, model, manager_name)

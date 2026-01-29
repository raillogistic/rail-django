"""
Nested Filter Input Generator for GraphQL.

This module provides the NestedFilterInputGenerator class that generates
typed GraphQL filter input types for Django models following the Prisma/Hasura
pattern where each field has its own typed filter input.

Example generated schema:
    input ProductWhereInput {
        name: StringFilterInput
        price: FloatFilterInput
        category: CategoryWhereInput  # Nested relation
        tags_count: CountFilterInput  # M2M count
        AND: [ProductWhereInput!]
        OR: [ProductWhereInput!]
        NOT: ProductWhereInput
    }

Note:
    Use get_nested_filter_generator() from the security module to obtain
    singleton instances for better cache reuse across requests.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set, Type

import graphene
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from graphene.utils.str_converters import to_camel_case

from .types import (
    IDFilterInput,
    CountFilterInput,
)
from .generator_utils import (
    DEFAULT_MAX_NESTED_DEPTH,
    DEFAULT_CACHE_MAX_SIZE,
    get_filter_input_for_field,
    is_historical_model,
    generate_computed_filters,
    generate_array_field_filters,
    generate_date_trunc_filters,
    generate_date_extract_filters,
    generate_historical_filters,
    get_advanced_filter_types,
)

logger = logging.getLogger(__name__)


class NestedFilterInputGenerator:
    """
    Generates nested GraphQL filter input types for Django models.

    This generator creates typed filter inputs following the Prisma/Hasura pattern
    where each field has its own typed filter input (StringFilter, IntFilter, etc.)
    instead of flat lookup expressions.

    Attributes:
        max_nested_depth: Maximum depth for nested relationship filters
        enable_count_filters: Whether to generate count filters for relations
        schema_name: Schema name for multi-schema support
        cache_max_size: Maximum number of cached filter input types
    """

    def __init__(
        self,
        max_nested_depth: int = DEFAULT_MAX_NESTED_DEPTH,
        enable_count_filters: bool = True,
        schema_name: Optional[str] = None,
        cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
    ):
        """
        Initialize the nested filter input generator.

        Args:
            max_nested_depth: Maximum depth for nested relationship filters.
            enable_count_filters: Whether to generate count filters for relations.
            schema_name: Schema name for multi-schema support.
            cache_max_size: Maximum number of cached filter input types.
        """
        self.max_nested_depth = max_nested_depth
        self.enable_count_filters = enable_count_filters
        self.schema_name = schema_name or "default"
        self.cache_max_size = cache_max_size

        # Instance-level cache (not class-level) for better isolation
        self._filter_input_cache: Dict[str, Type[graphene.InputObjectType]] = {}
        self._generation_stack: Set[str] = set()  # Prevent infinite recursion

        try:
            from ...core.settings import FilteringSettings
            self.filtering_settings = FilteringSettings.from_schema(self.schema_name)
        except (ImportError, AttributeError, KeyError):
            self.filtering_settings = None

    def clear_cache(self) -> None:
        """Clear the filter input cache for this generator."""
        self._filter_input_cache.clear()
        self._generation_stack.clear()

    def _evict_cache_if_needed(self) -> None:
        """Evict oldest cache entries if cache exceeds max size."""
        if len(self._filter_input_cache) >= self.cache_max_size:
            keys_to_remove = list(self._filter_input_cache.keys())[
                : self.cache_max_size // 10 or 1
            ]
            for key in keys_to_remove:
                del self._filter_input_cache[key]
            logger.debug(
                f"Evicted {len(keys_to_remove)} cache entries from "
                f"{self.schema_name} filter generator"
            )

    def generate_where_input(
        self,
        model: Type[models.Model],
        depth: int = 0,
    ) -> Type[graphene.InputObjectType]:
        """
        Generate a WhereInput type for a Django model.

        Args:
            model: Django model class to generate filter for
            depth: Current nesting depth (used internally for recursion)

        Returns:
            GraphQL InputObjectType for filtering the model
        """
        model_name = model.__name__
        cache_key = f"{self.schema_name}_{model_name}_where_{depth}"

        if cache_key in self._filter_input_cache:
            return self._filter_input_cache[cache_key]

        self._evict_cache_if_needed()

        if cache_key in self._generation_stack:
            return self._create_placeholder_input(model_name)

        self._generation_stack.add(cache_key)

        try:
            fields = self._generate_model_fields(model, depth)
            fields.update(self._generate_standard_filters(model))
            fields.update(self._generate_optional_filters(model))

            where_input = self._create_where_input_type(model_name, fields, depth)
            self._filter_input_cache[cache_key] = where_input

            return where_input
        finally:
            self._generation_stack.discard(cache_key)

    def _generate_model_fields(
        self, model: Type[models.Model], depth: int
    ) -> Dict[str, graphene.InputField]:
        """Generate filter fields for all model fields."""
        fields = {}

        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue

            field_name = field.name

            if field_name in ("id", "pk") and not isinstance(field, models.AutoField):
                continue
            if field_name.startswith("_") or "polymorphic" in field_name.lower():
                continue

            if isinstance(field, models.ForeignKey):
                fields.update(self._generate_fk_filter(field, depth))
            elif isinstance(field, models.ManyToManyField):
                fields.update(self._generate_m2m_filter(field, depth))
            elif isinstance(field, models.OneToOneField):
                fields.update(self._generate_fk_filter(field, depth))
            elif hasattr(field, "related_model") and field.related_model:
                fields.update(self._generate_reverse_filter(field, depth))
            else:
                filter_input = get_filter_input_for_field(field)
                if filter_input:
                    fields[field_name] = graphene.InputField(
                        filter_input,
                        name=to_camel_case(field_name),
                        description=f"Filtrer par {field_name}",
                    )

        return fields

    def _generate_standard_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """Generate standard filter fields available on all models."""
        fields = {
            "id": graphene.InputField(IDFilterInput, description="Filtrer par ID"),
            "quick": graphene.InputField(
                graphene.String, description="Recherche rapide dans plusieurs champs de texte"
            ),
            "include": graphene.InputField(
                graphene.List(graphene.NonNull(graphene.ID)),
                description="Inclure des IDs spécifiques indépendamment des autres filtres",
            ),
        }

        if is_historical_model(model):
            fields.update(generate_historical_filters(model))

        fields.update(generate_computed_filters(model))

        return fields

    def _generate_optional_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """Generate optional filter fields based on FilteringSettings."""
        fields = {}

        if not self.filtering_settings:
            return fields

        advanced_types = get_advanced_filter_types()

        if getattr(self.filtering_settings, "enable_full_text_search", False):
            fields["search"] = graphene.InputField(
                advanced_types["FullTextSearchInput"],
                description="Full-text search (Postgres) with icontains fallback",
            )

        if getattr(self.filtering_settings, "enable_window_filters", False):
            fields["_window"] = graphene.InputField(
                advanced_types["WindowFilterInput"],
                name="_window",
                description="Filter by window function (rank, percentile, row_number)",
            )

        if getattr(self.filtering_settings, "enable_subquery_filters", False):
            fields["_subquery"] = graphene.InputField(
                advanced_types["SubqueryFilterInput"],
                name="_subquery",
                description="Filter by correlated subquery",
            )
            fields["_exists"] = graphene.InputField(
                advanced_types["ExistsFilterInput"],
                name="_exists",
                description="Filter by existence of related records",
            )

        if getattr(self.filtering_settings, "enable_array_filters", False):
            fields.update(generate_array_field_filters(model))

        if getattr(self.filtering_settings, "enable_field_comparison", False):
            fields["_compare"] = graphene.InputField(
                advanced_types["FieldCompareFilterInput"],
                name="_compare",
                description="Compare fields to each other",
            )

        if getattr(self.filtering_settings, "enable_date_trunc_filters", False):
            fields.update(generate_date_trunc_filters(
                model, advanced_types["DateTruncFilterInput"]
            ))

        if getattr(self.filtering_settings, "enable_extract_date_filters", False):
            fields.update(generate_date_extract_filters(
                model, advanced_types["ExtractDateFilterInput"]
            ))

        return fields

    def _generate_fk_filter(
        self, field: models.ForeignKey, depth: int
    ) -> Dict[str, graphene.InputField]:
        """Generate filter for ForeignKey field."""
        filters = {}
        field_name = field.name
        related_model = field.related_model

        filters[field_name] = graphene.InputField(
            IDFilterInput,
            name=to_camel_case(field_name),
            description=f"Filter by {field_name} ID",
        )

        if depth < self.max_nested_depth and related_model:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                rel_name = f"{field_name}_rel"
                filters[rel_name] = graphene.InputField(
                    nested_where,
                    name=to_camel_case(rel_name),
                    description=f"Filter by {field_name} fields",
                )
            except (FieldDoesNotExist, RecursionError, AttributeError, TypeError) as e:
                logger.debug(f"Could not generate nested filter for {field_name}: {e}")

        return filters

    def _generate_m2m_filter(
        self, field: models.ManyToManyField, depth: int
    ) -> Dict[str, graphene.InputField]:
        """Generate filter for ManyToMany field."""
        filters = {}
        field_name = field.name
        related_model = field.related_model
        advanced_types = get_advanced_filter_types()

        filters[field_name] = graphene.InputField(
            IDFilterInput,
            name=to_camel_case(field_name),
            description=f"Filter by any {field_name} ID",
        )

        agg_name = f"{field_name}_agg"
        filters[agg_name] = graphene.InputField(
            advanced_types["AggregationFilterInput"],
            name=to_camel_case(agg_name),
            description=f"Filter by aggregated {field_name} values",
        )

        if self.filtering_settings and getattr(
            self.filtering_settings, "enable_conditional_aggregation", False
        ):
            cond_agg_name = f"{field_name}_cond_agg"
            filters[cond_agg_name] = graphene.InputField(
                advanced_types["ConditionalAggregationFilterInput"],
                name=to_camel_case(cond_agg_name),
                description=f"Filter by conditional aggregation on {field_name}",
            )

        if self.enable_count_filters:
            count_name = f"{field_name}_count"
            filters[count_name] = graphene.InputField(
                CountFilterInput,
                name=to_camel_case(count_name),
                description=f"Filter by {field_name} count",
            )

        if depth < self.max_nested_depth and related_model:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                for suffix, desc in [
                    ("_some", "At least one"),
                    ("_every", "All"),
                    ("_none", "No"),
                ]:
                    name = f"{field_name}{suffix}"
                    filters[name] = graphene.InputField(
                        nested_where,
                        name=to_camel_case(name),
                        description=f"{desc} {field_name} matches",
                    )
            except (FieldDoesNotExist, RecursionError, AttributeError, TypeError) as e:
                logger.debug(f"Could not generate nested M2M filter for {field_name}: {e}")

        return filters

    def _generate_reverse_filter(
        self, field: Any, depth: int
    ) -> Dict[str, graphene.InputField]:
        """Generate filter for reverse relation."""
        filters = {}

        accessor_name = (
            getattr(field, "name", None)
            or getattr(field, "get_accessor_name", lambda: None)()
        )
        if not accessor_name:
            return filters

        related_model = getattr(field, "related_model", None)
        if not related_model:
            return filters

        advanced_types = get_advanced_filter_types()

        agg_name = f"{accessor_name}_agg"
        filters[agg_name] = graphene.InputField(
            advanced_types["AggregationFilterInput"],
            name=to_camel_case(agg_name),
            description=f"Filter by aggregated {accessor_name} values",
        )

        if self.filtering_settings and getattr(
            self.filtering_settings, "enable_conditional_aggregation", False
        ):
            cond_agg_name = f"{accessor_name}_cond_agg"
            filters[cond_agg_name] = graphene.InputField(
                advanced_types["ConditionalAggregationFilterInput"],
                name=to_camel_case(cond_agg_name),
                description=f"Filter by conditional aggregation on {accessor_name}",
            )

        if self.enable_count_filters:
            count_name = f"{accessor_name}_count"
            filters[count_name] = graphene.InputField(
                CountFilterInput,
                name=to_camel_case(count_name),
                description=f"Filter by {accessor_name} count",
            )

        if depth < self.max_nested_depth:
            try:
                nested_where = self.generate_where_input(related_model, depth + 1)
                for suffix, desc in [
                    ("_some", "At least one"),
                    ("_every", "All"),
                    ("_none", "No"),
                ]:
                    name = f"{accessor_name}{suffix}"
                    filters[name] = graphene.InputField(
                        nested_where,
                        name=to_camel_case(name),
                        description=f"{desc} {accessor_name} matches",
                    )
            except (FieldDoesNotExist, RecursionError, AttributeError, TypeError) as e:
                logger.debug(f"Could not generate reverse filter for {accessor_name}: {e}")

        return filters

    def _create_where_input_type(
        self,
        model_name: str,
        fields: Dict[str, graphene.InputField],
        depth: int,
    ) -> Type[graphene.InputObjectType]:
        """Create the WhereInput type with boolean operators."""
        type_name = f"{model_name}WhereInput"
        type_ref = [None]

        fields["AND"] = graphene.List(
            lambda: type_ref[0], description="All conditions must match (AND)"
        )
        fields["OR"] = graphene.List(
            lambda: type_ref[0], description="At least one condition must match (OR)"
        )
        fields["NOT"] = graphene.InputField(
            lambda: type_ref[0], description="Condition must not match (NOT)"
        )

        where_input_type = type(type_name, (graphene.InputObjectType,), fields)
        type_ref[0] = where_input_type

        return where_input_type

    def _create_placeholder_input(self, model_name: str) -> Type[graphene.InputObjectType]:
        """
        Create a placeholder input type for recursive relationships.

        Args:
            model_name: Name of the model

        Returns:
            Placeholder InputObjectType
        """
        # ... implementation ...
        pass


def generate_where_input_for_model(
    model: Type[models.Model],
    schema_name: str = "default",
    max_depth: Optional[int] = None,
) -> Type[graphene.InputObjectType]:
    """
    Helper function to generate a WhereInput type for a model using default settings.
    
    Args:
        model: Django model class
        schema_name: Schema name for multi-schema support
        max_depth: Optional override for maximum nesting depth
        
    Returns:
        GraphQL InputObjectType for filtering the model
    """
    from .security import get_nested_filter_generator
    generator = get_nested_filter_generator(schema_name=schema_name)
    if max_depth is not None:
        # Create a new generator if custom depth is needed, or update existing one?
        # Typically singleton is used. For custom depth we might need a temporary generator
        # or just pass it if the method supports it.
        # But generator.generate_where_input accepts depth (current depth), not max_depth.
        # The generator instance holds max_nested_depth.
        # So we should probably create a new generator instance if max_depth is provided.
        from .generator import NestedFilterInputGenerator
        generator = NestedFilterInputGenerator(
            schema_name=schema_name, 
            max_nested_depth=max_depth
        )
        
    return generator.generate_where_input(model)


__all__ = [
    "NestedFilterInputGenerator",
    "generate_where_input_for_model",
]

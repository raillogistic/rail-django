"""
Advanced Filter Generators for Rail Django.

Provides legacy-compatible filter generators that wrap the new nested filter system,
ensuring backwards compatibility with existing code.

Classes:
    - AdvancedFilterGenerator: Legacy-compatible filter generator with full API
    - EnhancedFilterGenerator: Legacy-compatible enhanced filter generator for metadata
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Type

import graphene
from django.db import models

from .generator import NestedFilterInputGenerator
from .applicator import NestedFilterApplicator
from .generator_utils import DEFAULT_MAX_NESTED_DEPTH, MAX_ALLOWED_NESTED_DEPTH
from .analysis import (
    PerformanceAnalyzer,
    FilterMetadataGenerator,
    GroupedFieldFilter,
)
from .mixins import (
    SchemaSettingsMixin,
    HistoricalModelMixin,
    GraphQLMetaIntegrationMixin,
    QuickFilterMixin,
)

logger = logging.getLogger(__name__)


class AdvancedFilterGenerator(
    SchemaSettingsMixin, HistoricalModelMixin, GraphQLMetaIntegrationMixin
):
    """
    Legacy-compatible filter generator that provides the same API as the old
    filters.py AdvancedFilterGenerator, but uses the new nested filter system.

    This class is provided for backwards compatibility with code that imports
    AdvancedFilterGenerator. New code should use NestedFilterInputGenerator directly.

    Example:
        generator = AdvancedFilterGenerator(max_nested_depth=3)
        where_input_type = generator.generate_where_input(MyModel)
        filter_set = generator.generate_filter_set(MyModel)
    """

    def __init__(
        self,
        max_nested_depth: int = DEFAULT_MAX_NESTED_DEPTH,
        enable_nested_filters: bool = True,
        schema_name: Optional[str] = None,
    ):
        """
        Initialize the advanced filter generator.

        Args:
            max_nested_depth: Maximum nesting depth for related model filters
            enable_nested_filters: Whether to enable nested relation filters
            schema_name: Schema name for caching and settings
        """
        self.max_nested_depth = min(max_nested_depth, MAX_ALLOWED_NESTED_DEPTH)
        self.enable_nested_filters = enable_nested_filters
        self.schema_name = schema_name or "default"
        self._filter_cache: Dict[str, Any] = {}
        self._visited_models: Set = set()

        # Create the nested generator
        self._nested_generator = NestedFilterInputGenerator(
            max_nested_depth=self.max_nested_depth,
            enable_count_filters=True,
            schema_name=self.schema_name,
        )
        self._filter_applicator = NestedFilterApplicator(schema_name=self.schema_name)
        self._metadata_generator = FilterMetadataGenerator(schema_name=self.schema_name)

    def generate_filter_set(
        self, model: Type[models.Model], current_depth: int = 0
    ) -> Type:
        """
        Generate a FilterSet-like class for the given Django model.

        For backwards compatibility, this returns a class that can be used
        with django-filter's DjangoFilterConnectionField.

        Args:
            model: Django model to generate filters for
            current_depth: Current nesting depth

        Returns:
            FilterSet class (uses django_filters if available)
        """
        cache_key = f"{model.__name__}_{current_depth}"

        if cache_key in self._filter_cache:
            return self._filter_cache[cache_key]

        # Try to create a real django-filter FilterSet for Relay compatibility
        try:
            import django_filters
            from django_filters import FilterSet

            # Generate basic filters for the model
            filters = {}
            for field in model._meta.get_fields():
                if not hasattr(field, "name"):
                    continue

                field_name = field.name
                if field_name in ("polymorphic_ctype",) or "_ptr" in field_name:
                    continue

                # Add basic filters based on field type
                if isinstance(field, (models.CharField, models.TextField)):
                    filters[field_name] = django_filters.CharFilter(
                        field_name=field_name,
                        lookup_expr="icontains",
                    )
                    filters[f"{field_name}__exact"] = django_filters.CharFilter(
                        field_name=field_name,
                        lookup_expr="exact",
                    )
                elif isinstance(
                    field, (models.IntegerField, models.FloatField, models.DecimalField)
                ):
                    filters[field_name] = django_filters.NumberFilter(
                        field_name=field_name
                    )
                    filters[f"{field_name}__gt"] = django_filters.NumberFilter(
                        field_name=field_name, lookup_expr="gt"
                    )
                    filters[f"{field_name}__lt"] = django_filters.NumberFilter(
                        field_name=field_name, lookup_expr="lt"
                    )
                elif isinstance(field, (models.DateField, models.DateTimeField)):
                    filters[field_name] = django_filters.DateFilter(
                        field_name=field_name
                    )
                    filters[f"{field_name}__gt"] = django_filters.DateFilter(
                        field_name=field_name, lookup_expr="gt"
                    )
                    filters[f"{field_name}__lt"] = django_filters.DateFilter(
                        field_name=field_name, lookup_expr="lt"
                    )
                elif isinstance(field, models.BooleanField):
                    filters[field_name] = django_filters.BooleanFilter(
                        field_name=field_name
                    )
                elif isinstance(field, models.ForeignKey):
                    filters[field_name] = django_filters.NumberFilter(
                        field_name=field_name
                    )

            # Add quick filter across merged primitive/default + GraphQLMeta fields
            quick_fields = self.get_quick_filter_fields(model)
            if quick_fields:
                filters["quick"] = django_filters.CharFilter(
                    method="filter_quick", help_text="Quick search across configured fields"
                )

            def make_filter_quick_method(model_class, quick_fields_list):
                """Create a filter_quick method that searches across configured fields."""
                quick_mixin = QuickFilterMixin()

                def filter_quick(self, queryset, name, value):
                    if not value:
                        return queryset
                    q_objects = quick_mixin.build_quick_filter_q(
                        model_class,
                        value,
                        quick_filter_fields=quick_fields_list,
                    )
                    if not q_objects:
                        return queryset
                    return queryset.filter(q_objects)

                return filter_quick

            filter_set_class = type(
                f"{model.__name__}FilterSet",
                (FilterSet,),
                {
                    **filters,
                    "filter_quick": make_filter_quick_method(model, quick_fields),
                    "Meta": type(
                        "Meta",
                        (),
                        {
                            "model": model,
                            "fields": list(filters.keys()),
                            "strict": False,
                        },
                    ),
                },
            )

            self._filter_cache[cache_key] = filter_set_class
            return filter_set_class

        except ImportError:
            # django-filter not available, return a placeholder
            logger.warning(
                "django-filter not available, returning placeholder FilterSet"
            )
            return type(
                f"{model.__name__}FilterSet",
                (),
                {"Meta": type("Meta", (), {"model": model})},
            )

    def generate_where_input(
        self, model: Type[models.Model]
    ) -> Type[graphene.InputObjectType]:
        """
        Generate a WhereInput type for GraphQL filtering.

        Args:
            model: Django model class

        Returns:
            GraphQL InputObjectType for filtering
        """
        return self._nested_generator.generate_where_input(model)

    def apply_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
        model: Optional[Type[models.Model]] = None,
    ) -> models.QuerySet:
        """
        Apply filters to a queryset.

        Args:
            queryset: Django queryset
            where_input: Filter input dictionary
            model: Optional model class

        Returns:
            Filtered queryset
        """
        return self._filter_applicator.apply_where_filter(queryset, where_input, model)

    def analyze_query_performance(
        self, model: Type[models.Model], filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze the performance implications of applied filters.

        Args:
            model: Django model being filtered
            filters: Dictionary of applied filters

        Returns:
            Performance analysis dictionary
        """
        analyzer = PerformanceAnalyzer()
        return analyzer.analyze_query_performance(model, filters)

    def get_optimized_queryset(
        self,
        model: Type[models.Model],
        filters: Dict[str, Any],
        base_queryset: Optional[models.QuerySet] = None,
    ) -> models.QuerySet:
        """
        Get an optimized queryset based on the filters being applied.

        Args:
            model: Django model
            filters: Dictionary of filters
            base_queryset: Optional base queryset

        Returns:
            Optimized queryset
        """
        analyzer = PerformanceAnalyzer()
        return analyzer.get_optimized_queryset(model, filters, base_queryset)


class EnhancedFilterGenerator:
    """
    Legacy-compatible enhanced filter generator for metadata generation.

    This class provides the same API as the old filters.py EnhancedFilterGenerator,
    but uses the new FilterMetadataGenerator under the hood.

    Example:
        generator = EnhancedFilterGenerator(schema_name="default")
        filters = generator.get_grouped_filters(MyModel)
        for f in filters:
            print(f.field_name, f.operations)
    """

    def __init__(
        self,
        max_nested_depth: int = DEFAULT_MAX_NESTED_DEPTH,
        enable_nested_filters: bool = True,
        schema_name: Optional[str] = None,
        enable_quick_filter: bool = False,
    ):
        """
        Initialize the enhanced filter generator.

        Args:
            max_nested_depth: Maximum nesting depth for related model filters
            enable_nested_filters: Whether to enable nested relation filters
            schema_name: Schema name for caching
            enable_quick_filter: Whether to enable quick filter functionality
        """
        self.max_nested_depth = min(max_nested_depth, MAX_ALLOWED_NESTED_DEPTH)
        self.enable_nested_filters = enable_nested_filters
        self.schema_name = schema_name or "default"
        self.enable_quick_filter = enable_quick_filter
        self._metadata_generator = FilterMetadataGenerator(schema_name=self.schema_name)
        self._grouped_filter_cache: Dict[
            Type[models.Model], List[GroupedFieldFilter]
        ] = {}

    def get_grouped_filters(
        self, model: Type[models.Model]
    ) -> List[GroupedFieldFilter]:
        """
        Get grouped filters for a model.

        Args:
            model: Django model

        Returns:
            List of GroupedFieldFilter objects
        """
        return self._metadata_generator.get_grouped_filters(model)


__all__ = [
    "AdvancedFilterGenerator",
    "EnhancedFilterGenerator",
]

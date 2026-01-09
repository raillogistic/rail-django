"""
Advanced Filtering System for Django GraphQL Auto-Generation

This module provides the FilterGenerator class, which creates sophisticated
GraphQL filters based on Django model field types, supporting complex
filter combinations and field-specific operations.
"""

from cProfile import label
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

import graphene
from django.db import models
from django.db.models import Q
from graphene_django import DjangoObjectType

# Resilient import: DjangoFilterConnectionField may not exist in some graphene-django versions
try:
    from graphene_django.filter import DjangoFilterConnectionField  # type: ignore
except Exception:
    DjangoFilterConnectionField = None
import logging
from datetime import date, datetime, timedelta

import django_filters
from django.utils import timezone
from django_filters import (
    BooleanFilter,
    CharFilter,
    ChoiceFilter,
    DateFilter,
    FilterSet,
    ModelChoiceFilter,
    ModelMultipleChoiceFilter,
    MultipleChoiceFilter,
    NumberFilter,
)

from ..core.meta import GraphQLMeta, get_model_graphql_meta
from .introspector import ModelIntrospector

logger = logging.getLogger(__name__)

# Configuration constants for nested filtering
DEFAULT_MAX_NESTED_DEPTH = 3
MAX_ALLOWED_NESTED_DEPTH = 5


class FilterOperation:
    """
    Represents a single filter operation for a field.
    """

    def __init__(
        self,
        name: str,
        filter_type: str,
        lookup_expr: str = None,
        description: str = None,
        is_array: bool = False,
    ):
        self.name = name
        self.filter_type = filter_type
        self.lookup_expr = lookup_expr or "exact"
        self.description = description
        self.is_array = is_array


class GroupedFieldFilter:
    """
    Represents a grouped filter for a single field with multiple operations.
    """

    def __init__(
        self, field_name: str, field_type: str, operations: List[FilterOperation]
    ):
        self.field_name = field_name
        self.field_type = field_type
        self.operations = operations

    def to_dict(self):
        """Convert to dictionary format for metadata."""
        return {
            "field_name": self.field_name,
            "field_type": self.field_type,
            "operations": [
                {
                    "name": op.name,
                    "filter_type": op.filter_type,
                    "lookup_expr": op.lookup_expr,
                    "description": op.description,
                    "is_array": op.is_array,
                }
                for op in self.operations
            ],
        }


class EnhancedFilterGenerator:
    """
    Enhanced filter generator that creates grouped filters with comprehensive operations.
    """

    def __init__(
        self,
        max_nested_depth: int = DEFAULT_MAX_NESTED_DEPTH,
        enable_nested_filters: bool = True,
        schema_name: Optional[str] = None,
        enable_quick_filter: bool = False,
    ):
        self.max_nested_depth = min(max_nested_depth, MAX_ALLOWED_NESTED_DEPTH)
        self.enable_nested_filters = enable_nested_filters
        self.schema_name = schema_name or "default"
        # Quick filter is disabled by default per project requirements
        self.enable_quick_filter = enable_quick_filter
        self._filter_cache: Dict[Type[models.Model], Type[FilterSet]] = {}
        self._grouped_filter_cache: Dict[
            Type[models.Model], List[GroupedFieldFilter]
        ] = {}
        self._visited_models: set = set()

        logger.debug(
            f"Initialized EnhancedFilterGenerator for schema '{self.schema_name}' "
            f"with max_nested_depth={self.max_nested_depth}, "
            f"enable_nested_filters={self.enable_nested_filters}"
        )

    def get_grouped_filters(
        self, model: Type[models.Model]
    ) -> List[GroupedFieldFilter]:
        """
        Get grouped filters for a model.

        Args:
            model: Django model to generate grouped filters for

        Returns:
            List of GroupedFieldFilter objects
        """
        if model in self._grouped_filter_cache:
            return self._grouped_filter_cache[model]

        grouped_filters = []

        # Process each field in the model
        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue
            if (
                field.name == "polymorphic_ctype"
                or "_ptr" in field.name
                or "quick" in field.name
            ):
                continue
            field_operations = self._generate_field_operations(field)
            if field_operations:
                grouped_filter = GroupedFieldFilter(
                    field_name=field.name,
                    field_type=field.__class__.__name__,
                    operations=field_operations,
                )
                grouped_filters.append(grouped_filter)

        # Cache the result
        self._grouped_filter_cache[model] = grouped_filters
        return grouped_filters

    def _generate_field_operations(self, field: models.Field) -> List[FilterOperation]:
        """
        Generate comprehensive filter operations for a specific field type.

        Args:
            field: Django model field

        Returns:
            List of FilterOperation objects
        """
        operations = []
        field_name = field.name

        # CharField with choices should only expose exact, in, isnull
        if isinstance(field, models.CharField) and getattr(field, "choices", None):
            operations.extend(self._get_choice_operations(field_name, field.choices))
        elif isinstance(field, (models.CharField, models.TextField)):
            operations.extend(self._get_text_operations(field_name))
        elif isinstance(
            field, (models.IntegerField, models.FloatField, models.DecimalField)
        ):
            operations.extend(self._get_numeric_operations(field_name))
        elif isinstance(field, (models.DateField, models.DateTimeField)):
            operations.extend(self._get_date_operations(field_name))
        elif isinstance(field, models.BooleanField):
            operations.extend(self._get_boolean_operations(field_name))
        elif isinstance(field, models.ForeignKey):
            operations.extend(self._get_foreign_key_operations(field_name))
        elif isinstance(field, models.ManyToManyField):
            operations.extend(self._get_many_to_many_operations(field_name))
        elif hasattr(field, "choices") and field.choices:
            operations.extend(self._get_choice_operations(field_name, field.choices))
        elif isinstance(field, (models.FileField, models.ImageField)):
            operations.extend(self._get_file_operations(field_name))
        elif isinstance(field, models.JSONField):
            operations.extend(self._get_json_operations(field_name))

        return operations

    def _get_text_operations(self, field_name: str) -> List[FilterOperation]:
        """Get comprehensive text field operations."""
        return [
            FilterOperation(
                "exact", "CharFilter", "exact", f"Exact match for {field_name}"
            ),
            FilterOperation(
                "iexact",
                "CharFilter",
                "iexact",
                f"Case-insensitive exact match for {field_name}",
            ),
            FilterOperation(
                "contains", "CharFilter", "contains", f"Contains text in {field_name}"
            ),
            FilterOperation(
                "icontains",
                "CharFilter",
                "icontains",
                f"Case-insensitive contains text in {field_name}",
            ),
            FilterOperation(
                "startswith",
                "CharFilter",
                "startswith",
                f"Starts with text in {field_name}",
            ),
            FilterOperation(
                "istartswith",
                "CharFilter",
                "istartswith",
                f"Case-insensitive starts with text in {field_name}",
            ),
            FilterOperation(
                "endswith", "CharFilter", "endswith", f"Ends with text in {field_name}"
            ),
            FilterOperation(
                "iendswith",
                "CharFilter",
                "iendswith",
                f"Case-insensitive ends with text in {field_name}",
            ),
            FilterOperation(
                "in",
                "MultipleChoiceFilter",
                "in",
                f"Match any of the provided values for {field_name}",
                is_array=True,
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
            FilterOperation(
                "regex",
                "CharFilter",
                "regex",
                f"Regular expression match for {field_name}",
            ),
            FilterOperation(
                "iregex",
                "CharFilter",
                "iregex",
                f"Case-insensitive regular expression match for {field_name}",
            ),
        ]

    def _get_numeric_operations(self, field_name: str) -> List[FilterOperation]:
        """Get comprehensive numeric field operations."""
        return [
            FilterOperation(
                "exact", "NumberFilter", "exact", f"Exact value for {field_name}"
            ),
            FilterOperation(
                "gt", "NumberFilter", "gt", f"Greater than value for {field_name}"
            ),
            FilterOperation(
                "gte",
                "NumberFilter",
                "gte",
                f"Greater than or equal to value for {field_name}",
            ),
            FilterOperation(
                "lt", "NumberFilter", "lt", f"Less than value for {field_name}"
            ),
            FilterOperation(
                "lte",
                "NumberFilter",
                "lte",
                f"Less than or equal to value for {field_name}",
            ),
            FilterOperation(
                "in",
                "BaseInFilter",
                "in",
                f"Match any of the provided numeric values for {field_name}",
                is_array=True,
            ),
            FilterOperation(
                "range", "RangeFilter", "range", f"Value within range for {field_name}"
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
        ]

    def _get_date_operations(self, field_name: str) -> List[FilterOperation]:
        """Get comprehensive date field operations."""
        return [
            FilterOperation(
                "exact", "DateFilter", "exact", f"Exact date for {field_name}"
            ),
            FilterOperation("gt", "DateFilter", "gt", f"After date for {field_name}"),
            FilterOperation(
                "gte", "DateFilter", "gte", f"On or after date for {field_name}"
            ),
            FilterOperation("lt", "DateFilter", "lt", f"Before date for {field_name}"),
            FilterOperation(
                "lte", "DateFilter", "lte", f"On or before date for {field_name}"
            ),
            FilterOperation(
                "range",
                "DateRangeFilter",
                "range",
                f"Date within range for {field_name}",
            ),
            FilterOperation(
                "year", "NumberFilter", "year", f"Filter by year for {field_name}"
            ),
            FilterOperation(
                "month", "NumberFilter", "month", f"Filter by month for {field_name}"
            ),
            FilterOperation(
                "day", "NumberFilter", "day", f"Filter by day for {field_name}"
            ),
            FilterOperation(
                "week_day",
                "NumberFilter",
                "week_day",
                f"Filter by week day for {field_name}",
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
            FilterOperation(
                "today",
                "BooleanFilter",
                "today",
                f"Filtrer {field_name} pour aujourd'hui",
            ),
            FilterOperation(
                "yesterday",
                "BooleanFilter",
                "yesterday",
                f"Filtrer {field_name} pour hier",
            ),
            FilterOperation(
                "this_week",
                "BooleanFilter",
                "this_week",
                f"Filtrer {field_name} pour cette semaine",
            ),
            FilterOperation(
                "this_month",
                "BooleanFilter",
                "this_month",
                f"Filtrer {field_name} pour ce mois-ci",
            ),
            FilterOperation(
                "this_year",
                "BooleanFilter",
                "this_year",
                f"Filtrer {field_name} pour cette année",
            ),
        ]

    def _get_boolean_operations(self, field_name: str) -> List[FilterOperation]:
        """Get boolean field operations."""
        return [
            FilterOperation(
                "exact", "BooleanFilter", "exact", f"Boolean value for {field_name}"
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
        ]

    def _get_foreign_key_operations(self, field_name: str) -> List[FilterOperation]:
        """Get foreign key field operations."""
        return [
            FilterOperation(
                "exact", "NumberFilter", "exact", f"Exact ID for {field_name}"
            ),
            FilterOperation(
                "in",
                "BaseInFilter",
                "in",
                f"Match any of the provided IDs for {field_name}",
                is_array=True,
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
        ]

    def _get_many_to_many_operations(self, field_name: str) -> List[FilterOperation]:
        """Get many-to-many field operations."""
        return [
            FilterOperation(
                "exact", "NumberFilter", "exact", f"Exact ID in {field_name}"
            ),
            FilterOperation(
                "in",
                "BaseInFilter",
                "in",
                f"Match any of the provided IDs in {field_name}",
                is_array=True,
            ),
            FilterOperation(
                "isnull",
                "BooleanFilter",
                "isnull",
                f"Check if {field_name} has no related objects",
            ),
            FilterOperation(
                "count",
                "NumberFilter",
                "count",
                f"Count of related objects in {field_name}",
            ),
            FilterOperation(
                "count_gt",
                "NumberFilter",
                "count_gt",
                f"Count greater than for {field_name}",
            ),
            FilterOperation(
                "count_gte",
                "NumberFilter",
                "count_gte",
                f"Count greater than or equal for {field_name}",
            ),
            FilterOperation(
                "count_lt",
                "NumberFilter",
                "count_lt",
                f"Count less than for {field_name}",
            ),
            FilterOperation(
                "count_lte",
                "NumberFilter",
                "count_lte",
                f"Count less than or equal for {field_name}",
            ),
        ]

    def _get_choice_operations(
        self, field_name: str, choices: List
    ) -> List[FilterOperation]:
        """Get choice field operations."""
        return [
            FilterOperation(
                "exact", "ChoiceFilter", "exact", f"Exact choice for {field_name}"
            ),
            FilterOperation(
                "in",
                "MultipleChoiceFilter",
                "in",
                f"Match any of the provided choices for {field_name}",
                is_array=True,
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
        ]

    def _get_file_operations(self, field_name: str) -> List[FilterOperation]:
        """Get file field operations."""
        return [
            FilterOperation(
                "exact", "CharFilter", "exact", f"Exact file path for {field_name}"
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
        ]

    def _get_json_operations(self, field_name: str) -> List[FilterOperation]:
        """Get JSON field operations."""
        return [
            FilterOperation(
                "exact", "CharFilter", "exact", f"Exact JSON match for {field_name}"
            ),
            FilterOperation(
                "isnull", "BooleanFilter", "isnull", f"Check if {field_name} is null"
            ),
            FilterOperation(
                "has_key",
                "CharFilter",
                "has_key",
                f"Check if JSON has key in {field_name}",
            ),
            FilterOperation(
                "has_keys",
                "CharFilter",
                "has_keys",
                f"Check if JSON has all keys in {field_name}",
                is_array=True,
            ),
            FilterOperation(
                "has_any_keys",
                "CharFilter",
                "has_any_keys",
                f"Check if JSON has any of the keys in {field_name}",
                is_array=True,
            ),
        ]


class AdvancedFilterGenerator:
    """
    Generates advanced GraphQL filters for Django models based on field types.

    This class creates sophisticated filtering capabilities for GraphQL queries,
    supporting various field types and operations including text search, numeric
    ranges, date filtering, boolean logic, and nested relationship filtering.

    Features:
    - Field-specific filter operations (contains, exact, range, etc.)
    - Nested relationship filtering with configurable depth
    - Complex logical combinations (AND, OR, NOT)
    - Caching for performance optimization
    - Multi-schema support for different filtering configurations

    Supported Field Types:
    - CharField: contains, icontains, exact, iexact, startswith, endswith
    - IntegerField/FloatField: exact, lt, lte, gt, gte, range
    - DateField/DateTimeField: exact, lt, lte, gt, gte, range, year, month, day
    - BooleanField: exact
    - ChoiceField: exact, in
    - ForeignKey/OneToOne: nested filtering on related model fields
    - ManyToMany: nested filtering with multiple related objects

    Args:
        max_nested_depth: Maximum depth for nested relationship filtering (default: 3, max: 5)
        enable_nested_filters: Whether to enable nested field filtering (default: True)
        schema_name: Optional schema name for context (for future multi-schema support)

    Example:
        >>> filter_generator = AdvancedFilterGenerator(max_nested_depth=2)
        >>> filter_class = filter_generator.generate_filter_class(User)
        >>> # Creates filters like: name__contains, email__iexact, profile__bio__contains
    """

    def __init__(
        self,
        max_nested_depth: int = DEFAULT_MAX_NESTED_DEPTH,
        enable_nested_filters: bool = True,
        schema_name: Optional[str] = None,
    ):
        """
        Initialize the filter generator with nested filtering configuration.

        Args:
            max_nested_depth: Maximum depth for nested relationship filtering (default: 3, max: 5)
            enable_nested_filters: Whether to enable nested field filtering (default: True)
            schema_name: Optional schema name for context (for future multi-schema support)
        """
        self._filter_cache: Dict[Type[models.Model], Type[FilterSet]] = {}
        self.max_nested_depth = min(max_nested_depth, MAX_ALLOWED_NESTED_DEPTH)
        self.enable_nested_filters = enable_nested_filters
        self.schema_name = schema_name or "default"
        self._visited_models: set = (
            set()
        )  # Track visited models to prevent infinite recursion

        # Log configuration for debugging
        logger.debug(
            f"Initialized AdvancedFilterGenerator for schema '{self.schema_name}' "
            f"with max_nested_depth={self.max_nested_depth}, "
            f"enable_nested_filters={self.enable_nested_filters}"
        )

    def _is_historical_model(self, model: Type[models.Model]) -> bool:
        """Return True when the model originates from django-simple-history."""
        try:
            name = getattr(model, "__name__", "")
            module = getattr(model, "__module__", "")
        except Exception:
            return False
        if name.startswith("Historical"):
            return True
        return "simple_history" in module

    def _generate_historical_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, django_filters.Filter]:
        """Expose friendly filters for simple-history specific fields."""
        filters: Dict[str, django_filters.Filter] = {}

        # Allow filtering revisions by the original instance primary keys.
        filters["instance__in"] = django_filters.BaseInFilter(
            field_name="id",
            lookup_expr="in",
            label="Instances",
            help_text="Filtrer par identifiants d'instance d'origine.",
        )

        # Mirror the manual chips used in the frontend for create/update/delete types.
        try:
            history_field = model._meta.get_field("history_type")
            choices = getattr(history_field, "choices", None)
            if choices:
                filters["history_type__in"] = MultipleChoiceFilter(
                    field_name="history_type",
                    choices=choices,
                    label="Type de changement",
                    help_text="Filtrer par type de modification (création, modification, suppression).",
                )
        except Exception:
            pass

        return filters

    def generate_filter_set(
        self, model: Type[models.Model], current_depth: int = 0
    ) -> Type[FilterSet]:
        """
        Generate a FilterSet class for the given Django model with nested filtering support.

        Args:
            model: Django model to generate filters for
            current_depth: Current nesting depth (used for recursion control)

        Returns:
            FilterSet class with comprehensive filtering capabilities
        """
        # Create cache key based on model and depth
        cache_key = f"{model.__name__}_{current_depth}"

        if cache_key in self._filter_cache:
            logger.debug(f"Returning cached FilterSet for {cache_key}")
            return self._filter_cache[cache_key]

        # Prevent infinite recursion
        if model in self._visited_models:
            logger.warning(
                f"Circular reference detected for model {model.__name__} at depth {current_depth}"
            )
            return self._generate_basic_filter_set(model)

        # Check depth limits
        if current_depth >= self.max_nested_depth:
            logger.debug(
                f"Maximum nested depth ({self.max_nested_depth}) reached for {model.__name__}"
            )
            return self._generate_basic_filter_set(model)

        # Add model to visited set
        self._visited_models.add(model)

        try:
            # Get GraphQLMeta configuration for the model
            graphql_meta = get_model_graphql_meta(model)

            # Generate filters for all fields
            filters = {}
            for field in model._meta.get_fields():
                if hasattr(field, "name"):  # Skip reverse relations without names
                    field_filters = self._generate_field_filters(
                        field, current_depth, allow_nested=True
                    )
                    field_filters = self._apply_field_config_overrides(
                        field.name, field_filters, graphql_meta
                    )
                    filters.update(field_filters)

            # Add custom filters from GraphQLMeta
            if graphql_meta and graphql_meta.custom_filters:
                custom_filters = graphql_meta.get_custom_filters()
                filters.update(custom_filters)

            # Always include the 'quick' filter argument
            try:
                quick_fields = list(getattr(graphql_meta, "quick_filter_fields", []))
                if not quick_fields and getattr(
                    graphql_meta.filtering, "auto_detect_quick", True
                ):
                    quick_fields = self._get_default_quick_filter_fields(model)

                quick_filter = self._generate_quick_filter(model, quick_fields)
                if quick_filter:
                    filters["quick"] = quick_filter
            except Exception as e:
                logger.warning(
                    f"Failed to configure quick filter for {model.__name__}: {e}"
                )
            # Development-only verbose print removed to avoid console spam and slowdown
            # Use logger.debug if trace is needed:

            # Generate reverse relationship count filters
            reverse_count_filters = self._generate_reverse_relationship_count_filters(
                model
            )
            filters.update(reverse_count_filters)

            # Generate reverse relationship field filters
            reverse_field_filters = self._generate_reverse_relationship_field_filters(
                model
            )
            filters.update(reverse_field_filters)

            # Generate property filters
            property_filters = self._generate_property_filters(model)
            filters.update(property_filters)

            if self._is_historical_model(model):
                filters.update(self._generate_historical_filters(model))

            # Generate dynamic filter methods for count filters
            filter_methods = self._generate_count_filter_methods(model, filters)

            # Add a global 'include' filter to union specified IDs into results
            def filter_include(self, queryset, name, value):
                """
                Purpose: Union the provided primary key IDs with the current filtered queryset.
                Args:
                    self: The FilterSet instance (required by django-filters method hooks)
                    queryset: The current QuerySet after other filters are applied
                    name: The filter name ('include')
                    value: List of IDs to include (GraphQL ID values)
                Returns:
                    QuerySet: A combined queryset that includes records matching existing filters
                    plus records with pk in 'value'. Ensures deterministic ordering by placing
                    included IDs at the top, followed by the usual results, using a stable
                    secondary ordering.
                Raises:
                    None: Errors are logged and the original queryset is returned as fallback
                Example:
                    >>> filter_include(qs, 'include', ['1','2'])
                    <QuerySet ...>
                """
                try:
                    if not value:
                        return queryset
                    # Sanitize IDs: keep original types; cast numeric strings to int
                    sanitized_ids = []
                    for v in value:
                        try:
                            if isinstance(v, str) and v.isdigit():
                                sanitized_ids.append(int(v))
                            else:
                                sanitized_ids.append(v)
                        except Exception:
                            sanitized_ids.append(v)
                    # Build a combined queryset that includes:
                    # - All records from the current filtered queryset
                    # - All records with pk in sanitized_ids (even if excluded by other filters)
                    # Use OR across PK IN subquery to avoid unstable UNION ordering.
                    model_cls = queryset.model
                    from django.db.models import Case, When, Value, IntegerField

                    combined_qs = model_cls.objects.filter(
                        Q(pk__in=sanitized_ids) | Q(pk__in=queryset.values("pk"))
                    ).distinct()

                    # Deterministic ordering:
                    # 1) Included IDs first (priority = 0)
                    # 2) Others next (priority = 1)
                    # 3) Stable secondary order by PK to avoid flicker across executions
                    combined_qs = combined_qs.annotate(
                        _include_priority=Case(
                            When(pk__in=sanitized_ids, then=Value(0)),
                            default=Value(1),
                            output_field=IntegerField(),
                        )
                    ).order_by("_include_priority", "pk")

                    return combined_qs
                except Exception as e:
                    logger.warning(
                        f"Failed to apply 'include' union on {queryset.model.__name__}: {e}"
                    )
                    # Fallback: return original queryset
                    return queryset

            filters["include"] = django_filters.BaseInFilter(
                field_name="pk",
                method="filter_include",
                label="Include records by ID",
                help_text=(
                    "Include specific IDs in the results regardless of other filters"
                ),
            )
            filter_methods["filter_include"] = filter_include

            # Create FilterSet class
            filter_set_class = type(
                f"{model.__name__}FilterSet",
                (FilterSet,),
                {
                    **filters,
                    **filter_methods,
                    "Meta": type(
                        "Meta",
                        (),
                        {
                            "model": model,
                            "fields": list(filters.keys()),
                            "strict": False,  # Allow partial matches
                        },
                    ),
                },
            )

            # Cache the result
            self._filter_cache[cache_key] = filter_set_class
            return filter_set_class

        except Exception as e:
            logger.error(f"Error generating FilterSet for {model.__name__}: {e}")
            return self._generate_basic_filter_set(model)
        finally:
            # Remove model from visited set
            self._visited_models.discard(model)

    def _generate_quick_filter(
        self, model: Type[models.Model], quick_filter_fields: List[str]
    ) -> Optional[CharFilter]:
        """
        Generate a quick filter that searches across multiple fields.

        Args:
            model: Django model to generate quick filter for
            quick_filter_fields: List of field paths to include in quick search

        Returns:
            CharFilter that searches across specified fields
        """

        def quick_filter_method(queryset, name, value):
            if not value:
                return queryset

            q_objects = Q()
            for field_path in quick_filter_fields:
                try:
                    # Get the field type to determine appropriate lookup
                    field = self._get_field_from_path(model, field_path)
                    if field:
                        if isinstance(field, (models.CharField, models.TextField)):
                            q_objects |= Q(**{f"{field_path}__icontains": value})
                        elif isinstance(
                            field,
                            (
                                models.IntegerField,
                                models.FloatField,
                                models.DecimalField,
                            ),
                        ):
                            try:
                                numeric_value = float(value)
                                q_objects |= Q(**{field_path: numeric_value})
                            except (ValueError, TypeError):
                                continue
                        elif isinstance(field, models.BooleanField):
                            if value.lower() in ["true", "1", "yes", "on"]:
                                q_objects |= Q(**{field_path: True})
                            elif value.lower() in ["false", "0", "no", "off"]:
                                q_objects |= Q(**{field_path: False})
                        else:
                            # For other field types, try exact match
                            q_objects |= Q(**{f"{field_path}__icontains": value})
                except Exception as e:
                    logger.warning(
                        f"Error processing quick filter field {field_path}: {e}"
                    )
                    continue

            return queryset.filter(q_objects)

        return django_filters.CharFilter(
            method=quick_filter_method,
            help_text=f'Recherche rapide sur les champs : {", ".join(quick_filter_fields)}',
        )

    def _get_default_quick_filter_fields(self, model: Type[models.Model]) -> List[str]:
        """
        Get default searchable fields for quick filter when no specific fields are defined.

        Args:
            model: Django model to get searchable fields for

        Returns:
            List of field names suitable for quick search
        """
        searchable_fields = []

        for field in model._meta.get_fields():
            if hasattr(field, "name"):
                # Include text fields that are suitable for searching
                if isinstance(field, (models.CharField, models.TextField)):
                    # Skip very short fields and password-like fields
                    if (
                        (
                            hasattr(field, "max_length")
                            and field.max_length
                            and field.max_length < 10
                        )
                        or "password" in field.name.lower()
                        or "token" in field.name.lower()
                    ):
                        continue
                    searchable_fields.append(field.name)
                # Include email fields
                elif isinstance(field, models.EmailField):
                    searchable_fields.append(field.name)

        # Add some common related field searches if they exist
        common_related_fields = [
            "author__username",
            "author__first_name",
            "author__last_name",
            "user__username",
            "user__first_name",
            "user__last_name",
            "category__name",
            "tags__name",
        ]

        for field_path in common_related_fields:
            try:
                if self._get_field_from_path(model, field_path):
                    searchable_fields.append(field_path)
            except:
                continue

        return searchable_fields

    def _get_field_from_path(
        self, model: Type[models.Model], field_path: str
    ) -> Optional[models.Field]:
        """
        Get Django field from a field path (e.g., 'user__profile__name').

        Args:
            model: Starting model
            field_path: Field path with double underscores for relationships

        Returns:
            Django field instance or None if not found
        """
        try:
            current_model = model
            field_parts = field_path.split("__")

            for i, part in enumerate(field_parts):
                field = current_model._meta.get_field(part)

                # If this is the last part, return the field
                if i == len(field_parts) - 1:
                    return field

                # If it's a relationship field, get the related model
                if hasattr(field, "related_model"):
                    current_model = field.related_model
                else:
                    return None

            return None
        except Exception:
            return None

    # Date filter helper methods
    def _filter_date_today(self, queryset, field_name: str, value):
        """Filter for today's date."""
        if not value:
            return queryset
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        return queryset.filter(**{f"{field_name}": today})

    def _filter_date_yesterday(self, queryset, field_name: str, value):
        """Filter for yesterday's date."""
        if not value:
            return queryset
        yesterday = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        ) - timedelta(days=1)
        return queryset.filter(**{f"{field_name}": yesterday})

    def _filter_date_this_week(self, queryset, field_name: str, value):
        """Filter for this week's dates."""
        if not value:
            return queryset
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        days_since_monday = today.weekday()
        this_week_start = today - timedelta(days=days_since_monday)
        this_week_end = this_week_start + timedelta(days=6)
        return queryset.filter(
            **{f"{field_name}__range": [this_week_start, this_week_end]}
        )

    def _filter_date_past_week(self, queryset, field_name: str, value):
        """Filter for past week's dates."""
        if not value:
            return queryset
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        days_since_monday = today.weekday()
        this_week_start = today - timedelta(days=days_since_monday)
        past_week_start = this_week_start - timedelta(days=7)
        past_week_end = this_week_start - timedelta(days=1)
        return queryset.filter(
            **{f"{field_name}__range": [past_week_start, past_week_end]}
        )

    def _filter_date_this_month(self, queryset, field_name: str, value):
        """Filter for this month's dates."""
        if not value:
            return queryset
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        this_month_start = today.replace(day=1)
        if today.month == 12:
            next_month_start = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month_start = today.replace(month=today.month + 1, day=1)
        this_month_end = next_month_start - timedelta(days=1)
        return queryset.filter(
            **{f"{field_name}__dat__range": [this_month_start, this_month_end]}
        )

    def _filter_date_past_month(self, queryset, field_name: str, value):
        """Filter for past month's dates."""
        if not value:
            return queryset
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        this_month_start = today.replace(day=1)
        if this_month_start.month == 1:
            past_month_start = this_month_start.replace(
                year=this_month_start.year - 1, month=12, day=1
            )
        else:
            past_month_start = this_month_start.replace(
                month=this_month_start.month - 1, day=1
            )
        past_month_end = this_month_start - timedelta(days=1)
        return queryset.filter(
            **{f"{field_name}__range": [past_month_start, past_month_end]}
        )

    def _filter_date_this_year(self, queryset, field_name: str, value):
        """Filter for this year's dates."""
        if not value:
            return queryset
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        this_year_start = today.replace(month=1, day=1)
        this_year_end = today.replace(month=12, day=31)
        return queryset.filter(
            **{f"{field_name}__dat__range": [this_year_start, this_year_end]}
        )

    def _filter_date_past_year(self, queryset, field_name: str, value):
        """Filter for past year's dates."""
        if not value:
            return queryset
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        past_year_start = today.replace(year=today.year - 1, month=1, day=1)
        past_year_end = today.replace(year=today.year - 1, month=12, day=31)
        return queryset.filter(
            **{f"{field_name}__range": [past_year_start, past_year_end]}
        )

    def _generate_basic_filter_set(self, model: Type[models.Model]) -> Type[FilterSet]:
        """
        Create a basic FilterSet without nested relationships to prevent infinite recursion.

        Args:
            model: Django model to generate basic filters for

        Returns:
            Basic FilterSet class without nested filtering
        """
        cache_key = f"{model.__name__}_basic"

        if cache_key in self._filter_cache:
            return self._filter_cache[cache_key]

        # Generate only basic field filters (no nested relationships)
        filters = {}
        for field in model._meta.get_fields():
            if hasattr(field, "name"):  # Skip reverse relations without names
                field_filters = self._generate_field_filters(
                    field, 0, allow_nested=False
                )
                filters.update(field_filters)

        filter_set_class = type(
            f"{model.__name__}BasicFilterSet",
            (FilterSet,),
            {
                **filters,
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
        logger.debug(
            f"Generated basic FilterSet for {model.__name__} with {len(filters)} filters"
        )

        return filter_set_class

    def _generate_field_filters(
        self, field: models.Field, current_depth: int = 0, allow_nested: bool = True
    ) -> Dict[str, django_filters.Filter]:
        """
        Generates specific filters based on Django field type.

        Args:
            field: Django model field
            current_depth: Current nesting depth for recursive calls
            allow_nested: Whether to allow nested field generation

        Returns:
            Dictionary of filter name to Filter instance mappings
        """
        filters = {}
        field_name = field.name

        # CharField with choices should expose only exact, in, isnull
        if isinstance(field, models.CharField) and getattr(field, "choices", None):
            filters.update(self._generate_choice_filters(field_name, field.choices))
        elif isinstance(field, (models.CharField, models.TextField)):
            filters.update(self._generate_text_filters(field_name))
        elif isinstance(
            field, (models.IntegerField, models.FloatField, models.DecimalField)
        ):
            filters.update(self._generate_numeric_filters(field_name))
        elif isinstance(field, (models.DateField, models.DateTimeField)):
            filters.update(self._generate_date_filters(field_name))
        elif isinstance(field, models.BooleanField):
            filters.update(self._generate_boolean_filters(field_name))
        elif isinstance(field, (models.FileField, models.ImageField)):
            filters.update(self._generate_file_filters(field_name))
        elif isinstance(field, models.JSONField):
            filters.update(self._generate_json_filters(field_name))
        elif hasattr(field, "choices") and field.choices:
            filters.update(self._generate_choice_filters(field_name, field.choices))
        elif isinstance(field, models.ForeignKey):
            # Always generate basic foreign key filters (exact, in, isnull)
            filters.update(
                self._generate_foreign_key_filters(field_name, field.related_model)
            )

            # Add nested field filters only if enabled and within depth limits
            if (
                self.enable_nested_filters
                and allow_nested
                and current_depth < self.max_nested_depth
                and field.related_model not in self._visited_models
            ):
                filters.update(
                    self._generate_nested_field_filters(field, current_depth)
                )
        elif isinstance(field, models.ManyToManyField):
            # Always generate ManyToMany filters (exact, in, isnull, counts)
            filters.update(
                self._generate_many_to_many_filters(field_name, field.related_model)
            )

            # Add nested field filters only if enabled and within depth limits
            if (
                self.enable_nested_filters
                and allow_nested
                and current_depth < self.max_nested_depth
                and field.related_model not in self._visited_models
            ):
                filters.update(
                    self._generate_nested_field_filters(field, current_depth)
                )

        return filters

    def _apply_field_config_overrides(
        self,
        field_name: str,
        field_filters: Dict[str, django_filters.Filter],
        graphql_meta: GraphQLMeta,
    ) -> Dict[str, django_filters.Filter]:
        """
        Restrict auto-generated filters based on GraphQLMeta.filtering.fields configuration.
        """

        field_config = graphql_meta.filtering.fields.get(field_name)
        if not field_config:
            return field_filters

        allowed_lookups = set(field_config.lookups or [])
        if allowed_lookups:
            for filter_name, filter_instance in list(field_filters.items()):
                lookup_expr = getattr(filter_instance, "lookup_expr", None)
                if not lookup_expr:
                    lookup_expr = "exact"
                if lookup_expr == "exact" and "__" in filter_name:
                    lookup_expr = filter_name.split("__")[-1]
                if lookup_expr not in allowed_lookups:
                    del field_filters[filter_name]

        if field_config.choices:
            normalized_choices = []
            for value in field_config.choices:
                label = getattr(value, "label", None)
                if (
                    label is None
                    and isinstance(value, (tuple, list))
                    and len(value) >= 2
                ):
                    normalized_choices.append((value[0], value[1]))
                else:
                    normalized_choices.append((value, label or str(value)))

            for filter_instance in field_filters.values():
                filter_instance.extra.pop("choices", None)

        return field_filters

    def _generate_count_filter_methods(
        self, model: Type[models.Model], filters: Dict[str, django_filters.Filter]
    ) -> Dict[str, callable]:
        """
        Generate dynamic filter methods for count-based filtering.

        Args:
            model: Django model
            filters: Dictionary of filters that have been generated

        Returns:
            Dictionary of method names to method implementations
        """
        methods = {}

        # Generate methods for ManyToMany count filters
        for field in model._meta.get_fields():
            if isinstance(field, models.ManyToManyField):
                field_name = field.name

                # Generate count filter methods
                methods[f"filter_{field_name}_count"] = (
                    self._create_count_filter_method(field_name, "exact")
                )
                methods[f"filter_{field_name}_count_gt"] = (
                    self._create_count_filter_method(field_name, "gt")
                )
                methods[f"filter_{field_name}_count_gte"] = (
                    self._create_count_filter_method(field_name, "gte")
                )
                methods[f"filter_{field_name}_count_lt"] = (
                    self._create_count_filter_method(field_name, "lt")
                )
                methods[f"filter_{field_name}_count_lte"] = (
                    self._create_count_filter_method(field_name, "lte")
                )

        # Generate methods for reverse ManyToOne count filters
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                # Skip OneToOne reverse relationships
                from django.db.models.fields.reverse_related import OneToOneRel

                if isinstance(rel, OneToOneRel):
                    continue

                accessor_name = rel.get_accessor_name()
                if accessor_name:
                    methods[f"filter_{accessor_name}_count"] = (
                        self._create_reverse_count_filter_method(accessor_name, "exact")
                    )
                    methods[f"filter_{accessor_name}_count_gt"] = (
                        self._create_reverse_count_filter_method(accessor_name, "gt")
                    )
                    methods[f"filter_{accessor_name}_count_gte"] = (
                        self._create_reverse_count_filter_method(accessor_name, "gte")
                    )
                    methods[f"filter_{accessor_name}_count_lt"] = (
                        self._create_reverse_count_filter_method(accessor_name, "lt")
                    )
                    methods[f"filter_{accessor_name}_count_lte"] = (
                        self._create_reverse_count_filter_method(accessor_name, "lte")
                    )

        return methods

    def _create_count_filter_method(self, field_name: str, lookup_type: str):
        """
        Create a filter method for ManyToMany count filtering.

        Args:
            field_name: Name of the ManyToMany field
            lookup_type: Type of lookup (exact, gt, gte, lt, lte)

        Returns:
            Filter method function
        """

        def filter_method(self, queryset, name, value):
            if value is None:
                return queryset

            from django.db.models import Count

            # Annotate with count and filter
            count_field = f"{field_name}_count_annotation"
            queryset = queryset.annotate(**{count_field: Count(field_name)})

            if lookup_type == "exact":
                return queryset.filter(**{count_field: value})
            elif lookup_type == "gt":
                return queryset.filter(**{f"{count_field}__gt": value})
            elif lookup_type == "gte":
                return queryset.filter(**{f"{count_field}__gte": value})
            elif lookup_type == "lt":
                return queryset.filter(**{f"{count_field}__lt": value})
            elif lookup_type == "lte":
                return queryset.filter(**{f"{count_field}__lte": value})

            return queryset

        return filter_method

    def _create_reverse_count_filter_method(self, accessor_name: str, lookup_type: str):
        """
        Create a filter method for reverse ManyToOne count filtering.

        Args:
            accessor_name: Name of the reverse relationship accessor
            lookup_type: Type of lookup (exact, gt, gte, lt, lte)

        Returns:
            Filter method function
        """

        def filter_method(self, queryset, name, value):
            if value is None:
                return queryset

            from django.db.models import Count

            # Annotate with count and filter
            count_field = f"{accessor_name}_count_annotation"
            queryset = queryset.annotate(**{count_field: Count(accessor_name)})

            if lookup_type == "exact":
                return queryset.filter(**{count_field: value})
            elif lookup_type == "gt":
                return queryset.filter(**{f"{count_field}__gt": value})
            elif lookup_type == "gte":
                return queryset.filter(**{f"{count_field}__gte": value})
            elif lookup_type == "lt":
                return queryset.filter(**{f"{count_field}__lt": value})
            elif lookup_type == "lte":
                return queryset.filter(**{f"{count_field}__lte": value})

            return queryset

        return filter_method

    def _generate_reverse_relationship_count_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, django_filters.Filter]:
        """
        Generate count filters for reverse ManyToOne relationships.

        Args:
            model: Django model to generate reverse relationship count filters for

        Returns:
            Dictionary of filter name to Filter instance mappings
        """
        filters = {}

        # Get reverse relationships from model meta
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                # Skip OneToOne reverse relationships as they don't need count filters
                from django.db.models.fields.reverse_related import OneToOneRel

                if isinstance(rel, OneToOneRel):
                    continue

                accessor_name = rel.get_accessor_name()
                if accessor_name:
                    # Add count filters for reverse ManyToOne relationships
                    filters[f"{accessor_name}_count"] = NumberFilter(
                        method=f"filter_{accessor_name}_count",
                        help_text=f"Filtrer par le nombre de relations {accessor_name}",
                    )
                    filters[f"{accessor_name}_count__gt"] = NumberFilter(
                        method=f"filter_{accessor_name}_count_gt",
                        help_text=f"Filtrer par le nombre de relations {accessor_name} supérieur à",
                    )
                    filters[f"{accessor_name}_count__gte"] = NumberFilter(
                        method=f"filter_{accessor_name}_count_gte",
                        help_text=f"Filtrer par le nombre de relations {accessor_name} supérieur ou égal à",
                    )
                    filters[f"{accessor_name}_count__lt"] = NumberFilter(
                        method=f"filter_{accessor_name}_count_lt",
                        help_text=f"Filtrer par le nombre de relations {accessor_name} inférieur à",
                    )
                    filters[f"{accessor_name}_count__lte"] = NumberFilter(
                        method=f"filter_{accessor_name}_count_lte",
                        help_text=f"Filtrer par le nombre de relations {accessor_name} inférieur ou égal à",
                    )

        return filters

    def _create_property_filter_method(self, property_name: str, lookup_expr: str):
        """
        Create a custom filter method for property-based filtering.

        Args:
            property_name: Name of the property to filter on
            lookup_expr: Django lookup expression (e.g., 'exact', 'icontains', 'gt')

        Returns:
            Filter method that can be used with django-filter
        """

        def filter_method(queryset, name, value):
            """
            Custom filter method for property-based filtering.

            Since properties are computed at runtime, we need to evaluate
            them for each object and filter accordingly.
            """
            if value is None:
                return queryset

            # Get all objects and evaluate the property
            filtered_ids = []

            for obj in queryset:
                try:
                    # Get the property value
                    property_value = getattr(obj, property_name)

                    # Apply the lookup expression
                    if self._property_matches_filter(
                        property_value, value, lookup_expr
                    ):
                        filtered_ids.append(obj.pk)

                except (AttributeError, TypeError) as e:
                    logger.warning(
                        f"Error evaluating property {property_name} on {obj}: {e}"
                    )
                    continue

            # Return filtered queryset
            return queryset.filter(pk__in=filtered_ids)

        return filter_method

    def _property_matches_filter(
        self, property_value: Any, filter_value: Any, lookup_expr: str
    ) -> bool:
        """
        Check if a property value matches the filter criteria.

        Args:
            property_value: The actual value of the property
            filter_value: The value to filter by
            lookup_expr: The lookup expression to apply

        Returns:
            True if the property value matches the filter criteria
        """
        try:
            if lookup_expr == "exact":
                return property_value == filter_value
            elif lookup_expr == "iexact":
                return str(property_value).lower() == str(filter_value).lower()
            elif lookup_expr == "contains":
                return str(filter_value) in str(property_value)
            elif lookup_expr == "icontains":
                return str(filter_value).lower() in str(property_value).lower()
            elif lookup_expr == "startswith":
                return str(property_value).startswith(str(filter_value))
            elif lookup_expr == "istartswith":
                return str(property_value).lower().startswith(str(filter_value).lower())
            elif lookup_expr == "endswith":
                return str(property_value).endswith(str(filter_value))
            elif lookup_expr == "iendswith":
                return str(property_value).lower().endswith(str(filter_value).lower())
            elif lookup_expr == "gt":
                return property_value > filter_value
            elif lookup_expr == "gte":
                return property_value >= filter_value
            elif lookup_expr == "lt":
                return property_value < filter_value
            elif lookup_expr == "lte":
                return property_value <= filter_value
            elif lookup_expr == "in":
                return property_value in filter_value
            elif lookup_expr == "isnull":
                return (property_value is None) == filter_value
            elif lookup_expr == "year":
                # Handle date year filtering
                if hasattr(property_value, "year"):
                    return property_value.year == filter_value
                return False
            elif lookup_expr == "month":
                # Handle date month filtering
                if hasattr(property_value, "month"):
                    return property_value.month == filter_value
                return False
            elif lookup_expr == "day":
                # Handle date day filtering
                if hasattr(property_value, "day"):
                    return property_value.day == filter_value
                return False
            else:
                # Default to exact match for unknown lookup expressions
                return property_value == filter_value

        except (TypeError, ValueError) as e:
            logger.warning(
                f"Error comparing property value {property_value} with filter {filter_value} using {lookup_expr}: {e}"
            )
            return False

    def _generate_nested_field_filters(
        self, field: models.Field, current_depth: int
    ) -> Dict[str, django_filters.Filter]:
        """
        Generates nested field filters for related model fields.

        Args:
            field: Django ForeignKey or OneToOneField
            current_depth: Current nesting depth

        Returns:
            Dictionary of nested filter name to Filter instance mappings
        """
        nested_filters = {}
        field_name = field.name
        related_model = field.related_model

        # Skip nested filters for Simple History models
        try:
            if related_model and self._is_historical_model(related_model):
                return nested_filters
        except:
            pass

        if not related_model:
            return nested_filters

        # Track performance optimization suggestions
        optimization_suggestions = []

        # Get all fields from the related model
        for related_field in related_model._meta.get_fields():
            if not hasattr(related_field, "name") or related_field.many_to_many:
                continue

            nested_field_name = f"{field_name}__{related_field.name}"

            # Generate filters based on the related field type
            # CharField with choices should expose only exact, in, isnull
            if isinstance(related_field, models.CharField) and getattr(
                related_field, "choices", None
            ):
                nested_filters.update(
                    self._generate_choice_filters(
                        nested_field_name, related_field.choices
                    )
                )
            elif isinstance(related_field, (models.CharField, models.TextField)):
                nested_filters.update(
                    self._generate_nested_text_filters(
                        nested_field_name, related_field.name
                    )
                )
            elif isinstance(
                related_field,
                (models.IntegerField, models.FloatField, models.DecimalField),
            ):
                nested_filters.update(
                    self._generate_nested_numeric_filters(
                        nested_field_name, related_field.name
                    )
                )
            elif isinstance(related_field, (models.DateField, models.DateTimeField)):
                nested_filters.update(
                    self._generate_nested_date_filters(
                        nested_field_name, related_field.name
                    )
                )
            elif isinstance(related_field, models.BooleanField):
                nested_filters.update(
                    self._generate_nested_boolean_filters(
                        nested_field_name, related_field.name
                    )
                )
            elif isinstance(related_field, models.ForeignKey):
                # Add basic foreign key filter
                filter_cls = NumberFilter
                if isinstance(related_field.related_model._meta.pk, models.UUIDField):
                    filter_cls = CharFilter

                nested_filters[nested_field_name] = filter_cls(
                    field_name=nested_field_name,
                    help_text=f"Filtrer par ID de {nested_field_name}",
                )
                # Support membership and null checks for foreign key IDs
                nested_filters[f"{nested_field_name}__in"] = (
                    django_filters.BaseInFilter(
                        field_name=nested_field_name,
                        lookup_expr="in",
                        help_text=f"Correspondre à l'un des identifiants fournis pour {nested_field_name}",
                    )
                )
                nested_filters[f"{nested_field_name}__isnull"] = BooleanFilter(
                    field_name=nested_field_name,
                    lookup_expr="isnull",
                    help_text=f"Vérifier si {nested_field_name} est nul",
                )

                # Recursively add deeper nested filters if within depth limits
                if current_depth + 1 < self.max_nested_depth:
                    deeper_nested_filters = self._generate_nested_field_filters(
                        related_field, current_depth + 1
                    )
                    # Prefix the deeper nested filters with current field name
                    for deep_filter_name, deep_filter in deeper_nested_filters.items():
                        prefixed_name = f"{field_name}__{deep_filter_name}"
                        # Extract the lookup expression from the filter name
                        if "__" in deep_filter_name:
                            base_field_path = deep_filter_name.rsplit("__", 1)[0]
                            lookup_expr = deep_filter_name.rsplit("__", 1)[1]
                        else:
                            base_field_path = deep_filter_name
                            lookup_expr = "exact"

                        # Create the correct field path for Django ORM
                        correct_field_path = f"{field_name}__{base_field_path}"

                        # Create a new filter instance with the correct field_name
                        filter_class = type(deep_filter)
                        new_filter = filter_class(
                            field_name=correct_field_path,
                            lookup_expr=lookup_expr,
                            help_text=getattr(
                                deep_filter,
                                "help_text",
                                f"Filter by {correct_field_path}",
                            ),
                        )
                        nested_filters[prefixed_name] = new_filter

        # Log performance optimization suggestions
        if nested_filters:
            field_path = field_name
            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                optimization_suggestions.append(f"select_related('{field_path}')")
            elif hasattr(field, "related_model"):
                optimization_suggestions.append(f"prefetch_related('{field_path}')")

            if optimization_suggestions:
                logger.debug(
                    f"Performance suggestion for {related_model.__name__}: "
                    f"Consider using {', '.join(optimization_suggestions)} for better performance"
                )

        return nested_filters

    def analyze_query_performance(
        self, model: Type[models.Model], filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze the performance implications of applied filters and suggest optimizations.

        Args:
            model: Django model being filtered
            filters: Dictionary of applied filters

        Returns:
            Dictionary containing performance analysis and optimization suggestions
        """
        analysis = {
            "model": model.__name__,
            "total_filters": len(filters),
            "nested_filters": 0,
            "max_depth": 0,
            "select_related_suggestions": set(),
            "prefetch_related_suggestions": set(),
            "potential_n_plus_one_risks": [],
            "performance_score": "good",  # good, moderate, poor
            "recommendations": [],
        }

        # Analyze each filter
        for filter_name, filter_value in filters.items():
            if "__" in filter_name:
                # Calculate depth
                depth = filter_name.count("__") - 1  # Subtract 1 for lookup expression
                if depth > 0:
                    # Only count as nested filter if it crosses model boundaries
                    analysis["nested_filters"] += 1
                    analysis["max_depth"] = max(analysis["max_depth"], depth)

                    # Extract field path (remove lookup expression)
                    parts = filter_name.split("__")
                    lookup_expr = parts[-1]
                    field_path_parts = parts[:-1]

                    # Build field path for optimization suggestions
                    current_model = model
                    field_path = []

                    for i, part in enumerate(field_path_parts):
                        try:
                            field = current_model._meta.get_field(part)
                            field_path.append(part)

                            if isinstance(
                                field, (models.ForeignKey, models.OneToOneField)
                            ):
                                # Forward relationship - suggest select_related
                                path = "__".join(field_path)
                                analysis["select_related_suggestions"].add(path)
                                current_model = field.related_model
                            elif hasattr(field, "related_model"):
                                # Reverse relationship - suggest prefetch_related
                                path = "__".join(field_path)
                                analysis["prefetch_related_suggestions"].add(path)
                                analysis["potential_n_plus_one_risks"].append(path)
                                current_model = field.related_model
                        except:
                            break

        # Calculate performance score
        if analysis["max_depth"] > 3 or analysis["nested_filters"] > 10:
            analysis["performance_score"] = "poor"
        elif analysis["max_depth"] > 2 or analysis["nested_filters"] > 5:
            analysis["performance_score"] = "moderate"

        # Generate recommendations
        if analysis["select_related_suggestions"]:
            select_related_list = sorted(analysis["select_related_suggestions"])
            analysis["recommendations"].append(
                f"Use select_related({', '.join(repr(s) for s in select_related_list)}) "
                f"to optimize forward relationship queries"
            )

        if analysis["prefetch_related_suggestions"]:
            prefetch_related_list = sorted(analysis["prefetch_related_suggestions"])
            analysis["recommendations"].append(
                f"Use prefetch_related({', '.join(repr(p) for p in prefetch_related_list)}) "
                f"to optimize reverse relationship queries"
            )

        if analysis["potential_n_plus_one_risks"]:
            analysis["recommendations"].append(
                f"Potential N+1 query risks detected in: {', '.join(analysis['potential_n_plus_one_risks'])}"
            )

        if analysis["max_depth"] > 3:
            analysis["recommendations"].append(
                f"Consider reducing max_nested_depth from {analysis['max_depth']} to improve performance"
            )

        # Convert sets to lists for JSON serialization
        analysis["select_related_suggestions"] = list(
            analysis["select_related_suggestions"]
        )
        analysis["prefetch_related_suggestions"] = list(
            analysis["prefetch_related_suggestions"]
        )

        # Log performance analysis
        logger.info(
            f"Performance analysis for {model.__name__}: "
            f"Score={analysis['performance_score']}, "
            f"Nested filters={analysis['nested_filters']}, "
            f"Max depth={analysis['max_depth']}"
        )

        return analysis

    def get_optimized_queryset(
        self, model: Type[models.Model], filters: Dict[str, Any], base_queryset=None
    ) -> models.QuerySet:
        """
        Get an optimized queryset based on the filters being applied.

        Args:
            model: Django model
            filters: Dictionary of filters to be applied
            base_queryset: Optional base queryset to optimize

        Returns:
            Optimized QuerySet with appropriate select_related and prefetch_related calls
        """
        if base_queryset is None:
            queryset = model.objects.all()
        else:
            queryset = base_queryset

        # Analyze performance implications
        analysis = self.analyze_query_performance(model, filters)

        # Apply select_related optimizations
        if analysis["select_related_suggestions"]:
            queryset = queryset.select_related(*analysis["select_related_suggestions"])
            logger.debug(
                f"Applied select_related({analysis['select_related_suggestions']}) to {model.__name__} queryset"
            )

        # Apply prefetch_related optimizations
        if analysis["prefetch_related_suggestions"]:
            queryset = queryset.prefetch_related(
                *analysis["prefetch_related_suggestions"]
            )
            logger.debug(
                f"Applied prefetch_related({analysis['prefetch_related_suggestions']}) to {model.__name__} queryset"
            )

        return queryset
        """Generate nested text-specific filters for related fields."""
        # return {
        #     f'{field_name}__contains': CharFilter(
        #         field_name=field_name.replace('__', '__'),
        #         lookup_expr='contains',
        #         help_text=f'Filter {base_field_name} containing the specified text (case-sensitive)'
        #     ),
        #     f'{field_name}__icontains': CharFilter(
        #         field_name=field_name.replace('__', '__'),
        #         lookup_expr='icontains',
        #         help_text=f'Filter {base_field_name} containing the specified text (case-insensitive)'
        #     ),
        #     f'{field_name}__startswith': CharFilter(
        #         field_name=field_name.replace('__', '__'),
        #         lookup_expr='startswith',
        #         help_text=f'Filter {base_field_name} starting with the specified text'
        #     ),
        #     f'{field_name}__endswith': CharFilter(
        #         field_name=field_name.replace('__', '__'),
        #         lookup_expr='endswith',
        #         help_text=f'Filter {base_field_name} ending with the specified text'
        #     ),
        #     f'{field_name}__exact': CharFilter(
        #         field_name=field_name.replace('__', '__'),
        #         lookup_expr='exact',
        #         help_text=f'Filter {base_field_name} with exact match'
        #     ),
        # }

    def _generate_nested_text_filters(
        self, field_name: str, base_field_name: str
    ) -> Dict[str, CharFilter]:
        """
        Generate nested text-based filters for CharField and TextField.

        Args:
            field_name: The nested field name (e.g., 'category__name')
            base_field_name: The base field name (e.g., 'name')

        Returns:
            Dictionary of nested text filter mappings
        """
        return {
            # Exact matching aliases
            f"{field_name}__exact": CharFilter(
                field_name=field_name,
                lookup_expr="exact",
                help_text=f"Correspondance exacte pour {base_field_name}",
            ),
            field_name: CharFilter(
                field_name=field_name,
                lookup_expr="exact",
                help_text=f"Correspondance exacte pour {base_field_name}",
            ),
            # Case-insensitive text matching
            f"{field_name}__iexact": CharFilter(
                field_name=field_name,
                lookup_expr="iexact",
                help_text=f"Correspondance exacte insensible à la casse pour {base_field_name}",
            ),
            f"{field_name}__icontains": CharFilter(
                field_name=field_name,
                lookup_expr="icontains",
                help_text=f"Correspondance partielle insensible à la casse pour {base_field_name}",
            ),
            f"{field_name}__istartswith": CharFilter(
                field_name=field_name,
                lookup_expr="istartswith",
                help_text=f"Commence par (insensible à la casse) pour {base_field_name}",
            ),
            f"{field_name}__iendswith": CharFilter(
                field_name=field_name,
                lookup_expr="iendswith",
                help_text=f"Se termine par (insensible à la casse) pour {base_field_name}",
            ),
            # Case-sensitive text matching
            f"{field_name}__contains": CharFilter(
                field_name=field_name,
                lookup_expr="contains",
                help_text=f"Contient le texte dans {base_field_name}",
            ),
            f"{field_name}__startswith": CharFilter(
                field_name=field_name,
                lookup_expr="startswith",
                help_text=f"Commence par le texte dans {base_field_name}",
            ),
            f"{field_name}__endswith": CharFilter(
                field_name=field_name,
                lookup_expr="endswith",
                help_text=f"Se termine par le texte dans {base_field_name}",
            ),
        }

    def _generate_nested_numeric_filters(
        self, field_name: str, base_field_name: str
    ) -> Dict[str, NumberFilter]:
        """Generate nested numeric filters for related fields."""
        return {
            f"{field_name}__exact": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="exact",
                help_text=f"Filtrer {base_field_name} avec une valeur exacte",
            ),
            f"{field_name}__gt": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="gt",
                help_text=f"Filtrer {base_field_name} supérieur à la valeur spécifiée",
            ),
            f"{field_name}__gte": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="gte",
                help_text=f"Filtrer {base_field_name} supérieur ou égal à la valeur spécifiée",
            ),
            f"{field_name}__lt": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="lt",
                help_text=f"Filtrer {base_field_name} inférieur à la valeur spécifiée",
            ),
            f"{field_name}__lte": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="lte",
                help_text=f"Filtrer {base_field_name} inférieur ou égal à la valeur spécifiée",
            ),
            # Support array membership for numeric fields
            f"{field_name}__in": django_filters.BaseInFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="in",
                help_text=f"Correspondre à l'une des valeurs numériques fournies pour {base_field_name}",
            ),
            f"{field_name}__range": django_filters.RangeFilter(
                field_name=field_name.replace("__", "__"),
                help_text=f"Filtrer {base_field_name} dans l'intervalle spécifié",
            ),
        }

    def _generate_nested_date_filters(
        self, field_name: str, base_field_name: str
    ) -> Dict[str, DateFilter]:
        """Generate nested date filters for related fields."""
        return {
            f"{field_name}__exact": DateFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="exact",
                help_text=f"Filtrer {base_field_name} avec une correspondance de date exacte",
            ),
            f"{field_name}__gt": DateFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="gt",
                help_text=f"Filtrer {base_field_name} après la date spécifiée",
            ),
            f"{field_name}__gte": DateFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="gte",
                help_text=f"Filtrer {base_field_name} à la date spécifiée ou après",
            ),
            f"{field_name}__lt": DateFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="lt",
                help_text=f"Filtrer {base_field_name} avant la date spécifiée",
            ),
            f"{field_name}__lte": DateFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="lte",
                help_text=f"Filtrer {base_field_name} à la date spécifiée ou avant",
            ),
            f"{field_name}__date": DateFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="date",
                help_text=f"Filtrer {base_field_name} par date (en ignorant l'heure)",
            ),
            f"{field_name}__year": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="year",
                help_text=f"Filtrer {base_field_name} par année",
            ),
            f"{field_name}__month": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="month",
                help_text=f"Filtrer {base_field_name} par mois",
            ),
            f"{field_name}__day": NumberFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="day",
                help_text=f"Filtrer {base_field_name} par jour",
            ),
        }

    def _generate_nested_boolean_filters(
        self, field_name: str, base_field_name: str
    ) -> Dict[str, BooleanFilter]:
        """Generate nested boolean filters for related fields."""
        return {
            f"{field_name}__exact": BooleanFilter(
                field_name=field_name,
                lookup_expr="exact",
                help_text=f"Correspondance exacte pour {base_field_name}",
            ),
            f"{field_name}": BooleanFilter(
                field_name=field_name.replace("__", "__"),
                help_text=f"Filtrer {base_field_name} par valeur booléenne",
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=field_name.replace("__", "__"),
                lookup_expr="isnull",
                help_text=f"Filtrer {base_field_name} pour les valeurs nulles/vides",
            ),
        }

    def _generate_text_filters(self, field_name: str) -> Dict[str, CharFilter]:
        """Generate text-specific filters: contains, icontains, startswith, endswith."""
        return {
            f"{field_name}": CharFilter(
                field_name=field_name,
                help_text=f"Filtrer {field_name} avec correspondance de texte basique",
            ),
            f"{field_name}__contains": CharFilter(
                field_name=field_name,
                lookup_expr="contains",
                help_text=f"Filtrer {field_name} contenant le texte spécifié (sensible à la casse)",
            ),
            f"{field_name}__icontains": CharFilter(
                field_name=field_name,
                lookup_expr="icontains",
                help_text=f"Filtrer {field_name} contenant le texte spécifié (insensible à la casse)",
            ),
            f"{field_name}__startswith": CharFilter(
                field_name=field_name,
                lookup_expr="startswith",
                help_text=f"Filtrer {field_name} commençant par le texte spécifié",
            ),
            f"{field_name}__endswith": CharFilter(
                field_name=field_name,
                lookup_expr="endswith",
                help_text=f"Filtrer {field_name} se terminant par le texte spécifié",
            ),
            f"{field_name}__exact": CharFilter(
                field_name=field_name,
                lookup_expr="exact",
                help_text=f"Filtrer {field_name} avec correspondance exacte",
            ),
        }

    def _generate_numeric_filters(self, field_name: str) -> Dict[str, NumberFilter]:
        """Generate numeric filters: exact, gt, gte, lt, lte, in, range.

        Adds __range support for digit fields (integer, float, decimal) to allow
        filtering values within a minimum and maximum inclusive range.
        """
        return {
            f"{field_name}": NumberFilter(
                field_name=field_name,
                help_text=f"Filtrer {field_name} avec correspondance numérique basique",
            ),
            f"{field_name}__gt": NumberFilter(
                field_name=field_name,
                lookup_expr="gt",
                help_text=f"Filtrer {field_name} supérieur à la valeur spécifiée",
            ),
            f"{field_name}__gte": NumberFilter(
                field_name=field_name,
                lookup_expr="gte",
                help_text=f"Filtrer {field_name} supérieur ou égal à la valeur spécifiée",
            ),
            f"{field_name}__lt": NumberFilter(
                field_name=field_name,
                lookup_expr="lt",
                help_text=f"Filtrer {field_name} inférieur à la valeur spécifiée",
            ),
            f"{field_name}__lte": NumberFilter(
                field_name=field_name,
                lookup_expr="lte",
                help_text=f"Filtrer {field_name} inférieur ou égal à la valeur spécifiée",
            ),
            f"{field_name}__in": django_filters.BaseInFilter(
                field_name=field_name,
                lookup_expr="in",
                help_text=f"Filtrer {field_name} correspondant à l'une des valeurs fournies (tableau Int[])",
            ),
            f"{field_name}__range": django_filters.RangeFilter(
                field_name=field_name,
                help_text=f"Filtrer {field_name} dans l'intervalle inclus spécifié",
            ),
        }

    def _generate_date_filters(self, field_name: str) -> Dict[str, DateFilter]:
        """Generate date filters: year, month, day, range, gt, lt, and time-based filters."""
        filters = {
            f"{field_name}__year": NumberFilter(
                field_name=field_name,
                lookup_expr="year",
                help_text=f"Filtrer {field_name} par année",
            ),
            f"{field_name}__month": NumberFilter(
                field_name=field_name,
                lookup_expr="month",
                help_text=f"Filtrer {field_name} par mois",
            ),
            f"{field_name}__day": NumberFilter(
                field_name=field_name,
                lookup_expr="day",
                help_text=f"Filtrer {field_name} par jour",
            ),
            # Add exact date matching for non-nested date fields
            f"{field_name}__exact": DateFilter(
                field_name=field_name,
                lookup_expr="exact",
                help_text=f"Filtrer {field_name} avec une correspondance de date exacte",
            ),
            f"{field_name}__gt": DateFilter(
                field_name=field_name,
                lookup_expr="gt",
                help_text=f"Filtrer {field_name} après la date spécifiée",
            ),
            f"{field_name}__lt": DateFilter(
                field_name=field_name,
                lookup_expr="lt",
                help_text=f"Filtrer {field_name} avant la date spécifiée",
            ),
            f"{field_name}__range": django_filters.DateRangeFilter(
                field_name=field_name,
                help_text=f"Filtrer {field_name} dans l'intervalle de dates spécifié",
            ),
        }

        # Add time-based filters
        today = (
            timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        )
        yesterday = today - timedelta(days=1)

        # Calculate week boundaries (Monday as start of week)
        days_since_monday = today.weekday()
        this_week_start = today - timedelta(days=days_since_monday)
        this_week_end = this_week_start + timedelta(days=6)
        past_week_start = this_week_start - timedelta(days=7)
        past_week_end = this_week_start - timedelta(days=1)

        # Calculate month boundaries
        this_month_start = today.replace(day=1)
        if today.month == 12:
            next_month_start = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month_start = today.replace(month=today.month + 1, day=1)
        this_month_end = next_month_start - timedelta(days=1)

        if this_month_start.month == 1:
            past_month_start = this_month_start.replace(
                year=this_month_start.year - 1, month=12, day=1
            )
        else:
            past_month_start = this_month_start.replace(
                month=this_month_start.month - 1, day=1
            )
        past_month_end = this_month_start - timedelta(days=1)

        # Calculate year boundaries
        this_year_start = today.replace(month=1, day=1)
        this_year_end = today.replace(month=12, day=31)
        past_year_start = this_year_start.replace(year=this_year_start.year - 1)
        past_year_end = this_year_end.replace(year=this_year_end.year - 1)

        # Add time-based filters using custom filter methods
        time_filters = {
            f"{field_name}_today": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_today(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour aujourd'hui",
                
            ),
            f"{field_name}_yesterday": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_yesterday(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour hier",
            ),
            f"{field_name}_this_week": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_this_week(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour cette semaine",
            ),
            f"{field_name}_past_week": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_past_week(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour la semaine passée",
            ),
            f"{field_name}_this_month": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_this_month(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour ce mois-ci",
            ),
            f"{field_name}_past_month": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_past_month(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour le mois passé",
            ),
            f"{field_name}_this_year": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_this_year(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour cette année",
            ),
            f"{field_name}_past_year": django_filters.BooleanFilter(
                method=lambda queryset, name, value: self._filter_date_past_year(
                    queryset, field_name, value
                ),
                help_text=f"Filtrer {field_name} pour l'année passée",
            ),
        }

        filters.update(time_filters)
        return filters

    def _generate_boolean_filters(self, field_name: str) -> Dict[str, BooleanFilter]:
        """Generate boolean filters: exact matching."""
        return {
            f"{field_name}": BooleanFilter(
                field_name=field_name,
                help_text=f"Filtrer {field_name} par valeur booléenne",
            ),
        }

    def _generate_choice_filters(
        self, field_name: str, choices: List
    ) -> Dict[str, ChoiceFilter]:
        """Generate choice filters: exact, in, isnull."""
        choice_values = [choice[0] for choice in choices]
        return {
            f"{field_name}": ChoiceFilter(
                field_name=field_name,
                choices=choices,
                help_text=f"Filtrer {field_name} par choix spécifique",
            ),
            f"{field_name}__in": django_filters.MultipleChoiceFilter(
                field_name=field_name,
                choices=choices,
                help_text=f"Filtrer {field_name} par plusieurs choix",
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                help_text=f"Vérifier si {field_name} est nul",
            ),
        }

    def _generate_file_filters(self, field_name: str) -> Dict[str, CharFilter]:
        """Generate file-specific filters: isnull, exact."""
        return {
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                label=f'{field_name.replace("_", " ").title()} Is Null',
            ),
            f"{field_name}__exact": CharFilter(
                field_name=f"{field_name}__exact",
                label=f'{field_name.replace("_", " ").title()} Exact',
            ),
        }

    def _generate_json_filters(self, field_name: str) -> Dict[str, CharFilter]:
        """Generate JSON-specific filters: exact match and null checks."""
        return {
            f"{field_name}": CharFilter(
                field_name=field_name,
                lookup_expr="exact",
                help_text=f"Filtrer {field_name} avec correspondance JSON exacte",
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=field_name,
                lookup_expr="isnull",
                help_text=f"Filtrer {field_name} pour les valeurs nulles/vides",
            ),
        }

    def _generate_foreign_key_filters(
        self, field_name: str, related_model: Type[models.Model] = None
    ) -> Dict[str, django_filters.Filter]:
        """Generate foreign key filters: exact, in, isnull."""
        filter_cls = NumberFilter
        if related_model and isinstance(related_model._meta.pk, models.UUIDField):
            filter_cls = CharFilter

        filters = {
            f"{field_name}": filter_cls(
                field_name=field_name, help_text=f"Filtrer par ID de {field_name}"
            ),
        }

        # Only add ModelMultipleChoiceFilter if we have the related model
        if related_model:
            filters[f"{field_name}__in"] = django_filters.ModelMultipleChoiceFilter(
                field_name=field_name,
                queryset=related_model.objects.all(),
                to_field_name="pk",
                help_text=f"Filtrer par plusieurs ID de {field_name}",
            )

        # Always support isnull for ForeignKey/OneToOne
        filters[f"{field_name}__isnull"] = BooleanFilter(
            field_name=field_name,
            lookup_expr="isnull",
            help_text=f"Vérifier si {field_name} est nul",
        )

        return filters

    def _generate_many_to_many_filters(
        self, field_name: str, related_model: Type[models.Model]
    ) -> Dict[str, django_filters.Filter]:
        """
        Generate ManyToMany field filters including count filters.

        Args:
            field_name: Name of the ManyToMany field
            related_model: Related model class

        Returns:
            Dictionary of filter name to Filter instance mappings
        """
        filter_cls = NumberFilter
        if related_model and isinstance(related_model._meta.pk, models.UUIDField):
            filter_cls = CharFilter

        filters = {
            # Basic ManyToMany filters
            f"{field_name}": filter_cls(
                field_name=field_name, help_text=f"Filtrer par ID de {field_name}"
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=field_name,
                lookup_expr="isnull",
                help_text=f"Vérifier si {field_name} n'a pas d'objets liés",
            ),
            # Count filters for ManyToMany relationships
            f"{field_name}_count": NumberFilter(
                method=f"filter_{field_name}_count",
                help_text=f"Filtrer par le nombre de relations {field_name}",
            ),
            f"{field_name}_count__gt": NumberFilter(
                method=f"filter_{field_name}_count_gt",
                help_text=f"Filtrer par le nombre de relations {field_name} supérieur à",
            ),
            f"{field_name}_count__gte": NumberFilter(
                method=f"filter_{field_name}_count_gte",
                help_text=f"Filtrer par le nombre de relations {field_name} supérieur ou égal à",
            ),
            f"{field_name}_count__lt": NumberFilter(
                method=f"filter_{field_name}_count_lt",
                help_text=f"Filtrer par le nombre de relations {field_name} inférieur à",
            ),
            f"{field_name}_count__lte": NumberFilter(
                method=f"filter_{field_name}_count_lte",
                help_text=f"Filtrer par le nombre de relations {field_name} inférieur ou égal à",
            ),
        }

        if related_model:
            filters[f"{field_name}__in"] = django_filters.ModelMultipleChoiceFilter(
                field_name=field_name,
                queryset=related_model.objects.all(),
                to_field_name="pk",
                help_text=f"Filtrer par plusieurs ID de {field_name}",
            )

        return filters

    def _get_basic_filter_lookups(self, field: models.Field) -> List[str]:
        """
        Returns basic filter lookups for django-filter Meta.fields configuration.

        Args:
            field: Django model field

        Returns:
            List of lookup expressions for the field
        """
        if isinstance(field, (models.CharField, models.TextField)):
            return ["exact", "icontains", "startswith", "endswith"]
        elif isinstance(
            field, (models.IntegerField, models.FloatField, models.DecimalField)
        ):
            return ["exact", "gt", "gte", "lt", "lte"]
        elif isinstance(field, (models.DateField, models.DateTimeField)):
            return ["exact", "year", "month", "day", "gt", "lt"]
        elif isinstance(field, models.BooleanField):
            return ["exact"]
        elif isinstance(field, (models.FileField, models.ImageField)):
            return ["exact", "isnull"]
        elif isinstance(field, models.JSONField):
            return ["exact", "isnull"]
        elif hasattr(field, "choices") and field.choices:
            return ["exact", "in", "isnull"]
        elif isinstance(field, models.ForeignKey):
            return ["exact", "in"]
        else:
            return ["exact"]

    def generate_complex_filter_input(
        self, model: Type[models.Model]
    ) -> Type[graphene.InputObjectType]:
        """
        Purpose: Build a typed GraphQL InputObjectType to express complex filters with AND/OR/NOT.

        This uses a self-referential, nested InputObjectType instead of a GenericScalar to preserve
        strong typing, autocompletion, and validation. Nested JSON-like structures are naturally
        supported in GraphQL input objects, so callers can pass hierarchies of AND/OR lists and a
        single NOT object.

        Args:
            model (Type[models.Model]): Django model class the filter targets.

        Returns:
            Type[graphene.InputObjectType]: A generated "<ModelName>ComplexFilter" input type with
            typed field filters and AND/OR/NOT recursion for composing logical expressions.

        Raises:
            Exception: If the underlying filter set generation fails for the provided model.

        Example:
            >>> # Example GraphQL variables for a UniteMesure list query
            >>> variables = {
            ...     "filters": {
            ...         "AND": [
            ...             {"code__icontains": "G"},
            ...             {"nom__icontains": "unité"}
            ...         ],
            ...         "OR": [
            ...             {"nom__startswith": "K"},
            ...             {"code__exact": "KG"}
            ...         ],
            ...         "NOT": {"nom__endswith": "zzz"}
            ...     },
            ...     "limit": 5
            ... }
            >>> # The input type name will be "UniteMesureComplexFilter"
        """
        model_name = model.__name__
        filter_set = self.generate_filter_set(model)

        # Create basic filter fields
        filter_fields = {}
        for field_name, filter_instance in filter_set.base_filters.items():
            if isinstance(filter_instance, CharFilter):
                filter_fields[field_name] = graphene.String()
            elif isinstance(filter_instance, NumberFilter):
                filter_fields[field_name] = graphene.Float()
            elif isinstance(filter_instance, DateFilter):
                filter_fields[field_name] = graphene.Date()
            elif isinstance(filter_instance, BooleanFilter):
                filter_fields[field_name] = graphene.Boolean()
            elif isinstance(filter_instance, ChoiceFilter):
                filter_fields[field_name] = graphene.String()
            elif isinstance(
                filter_instance,
                (
                    ModelMultipleChoiceFilter,
                    django_filters.MultipleChoiceFilter,
                    django_filters.BaseInFilter,
                ),
            ):
                # __in filters rely on multiple choice lists
                list_type = graphene.String

                if isinstance(filter_instance, ModelMultipleChoiceFilter):
                    list_type = graphene.ID
                elif isinstance(filter_instance, django_filters.BaseInFilter):
                    # BaseInFilter is typically used for numeric arrays in this generator
                    list_type = graphene.Float

                if (
                    "Number" in filter_instance.__class__.__name__
                    or "Integer" in filter_instance.__class__.__name__
                ):
                    list_type = graphene.Float

                filter_fields[field_name] = graphene.List(graphene.NonNull(list_type))
            else:
                # Fallback for other filter types
                filter_fields[field_name] = graphene.String()

        # Create the complex filter input type
        complex_filter_class = type(
            f"{model_name}ComplexFilter",
            (graphene.InputObjectType,),
            {
                **filter_fields,
                "AND": graphene.List(lambda: complex_filter_class),
                "OR": graphene.List(lambda: complex_filter_class),
                "NOT": graphene.Field(lambda: complex_filter_class),
            },
        )

        return complex_filter_class

    def apply_complex_filters(
        self, queryset: models.QuerySet, filter_input: Dict[str, Any]
    ) -> models.QuerySet:
        """
        Purpose: Apply a nested AND/OR/NOT filter tree to a queryset using Django Q objects.

        Args:
            queryset (models.QuerySet): Base queryset to filter.
            filter_input (Dict[str, Any]): Parsed complex filter input (matching the generated
                <ModelName>ComplexFilter structure). Keys for regular filters use the standard
                "field__lookup" convention.

        Returns:
            models.QuerySet: A queryset filtered by the composed logical expression.

        Raises:
            ValueError: If filter_input contains unsupported structures or types.

        Example:
            >>> # Given variables['filters'] built like in the generate_complex_filter_input example,
            >>> # the resolver passes it into apply_complex_filters(queryset, filters).
            >>> # This method translates the logical tree into Q() objects and returns queryset.filter(Q(...)).
        """
        if not filter_input:
            return queryset

        q_objects = Q()

        # Handle AND operations
        if "AND" in filter_input:
            and_filters = filter_input.pop("AND")
            for and_filter in and_filters:
                and_q = self._build_q_object(and_filter)
                q_objects &= and_q

        # Handle OR operations
        if "OR" in filter_input:
            or_filters = filter_input.pop("OR")
            or_q = Q()
            for or_filter in or_filters:
                or_q |= self._build_q_object(or_filter)
            q_objects &= or_q

        # Handle NOT operations
        if "NOT" in filter_input:
            not_filter = filter_input.pop("NOT")
            not_q = self._build_q_object(not_filter)
            q_objects &= ~not_q

        # Handle regular field filters
        regular_q = self._build_q_object(filter_input)
        q_objects &= regular_q

        return queryset.filter(q_objects)

    def _build_q_object(self, filter_dict: Dict[str, Any]) -> Q:
        """
        Builds a Django Q object from a filter dictionary.

        Args:
            filter_dict: Dictionary containing filter criteria

        Returns:
            Django Q object
        """
        q_object = Q()

        if filter_dict:
            for key, value in filter_dict.items():
                if key in ["AND", "OR", "NOT"]:
                    continue  # These are handled separately

                if value is not None:
                    q_object &= Q(**{key: value})

        return q_object

    def _generate_property_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, django_filters.Filter]:
        """
        Generate filters for @property methods on the model.

        Args:
            model: Django model to generate property filters for

        Returns:
            Dictionary of property filter name to Filter instance mappings
        """
        filters = {}

        # Use ModelIntrospector to detect properties
        introspector = ModelIntrospector(model)
        properties = introspector.properties

        for property_name, property_info in properties.items():
            # Generate filters based on property return type
            property_filters = self._generate_property_type_filters(
                property_name, property_info.return_type
            )
            filters.update(property_filters)

        logger.debug(f"Generated {len(filters)} property filters for {model.__name__}")
        return filters

    def _generate_property_type_filters(
        self, property_name: str, return_type: Any
    ) -> Dict[str, django_filters.Filter]:
        """
        Generate specific filters based on property return type.

        Args:
            property_name: Name of the property
            return_type: Return type annotation of the property

        Returns:
            Dictionary of filter name to Filter instance mappings
        """
        filters = {}

        # Handle different return types
        if return_type == str or return_type == "str":
            filters.update(self._generate_property_text_filters(property_name))
        elif return_type == int or return_type == "int":
            filters.update(self._generate_property_numeric_filters(property_name))
        elif return_type == float or return_type == "float":
            filters.update(self._generate_property_numeric_filters(property_name))
        elif return_type == bool or return_type == "bool":
            filters.update(self._generate_property_boolean_filters(property_name))
        elif (
            return_type == date
            or return_type == "date"
            or str(return_type) == "<class 'datetime.date'>"
        ):
            filters.update(self._generate_property_date_filters(property_name))
        elif return_type == list or return_type == "list":
            # For list properties, provide basic text filtering
            filters.update(self._generate_property_text_filters(property_name))

        else:
            # Default to text filtering for unknown types
            filters.update(self._generate_property_text_filters(property_name))

        return filters

    def _generate_property_text_filters(
        self, property_name: str
    ) -> Dict[str, django_filters.Filter]:
        """Generate text-specific filters for properties: contains, icontains, startswith, endswith."""
        return {
            f"{property_name}": CharFilter(
                method=self._create_property_filter_method(property_name, "exact"),
                help_text=f"Filtrer par la propriété {property_name} avec une correspondance de texte exacte",
            ),
            f"{property_name}__contains": CharFilter(
                method=self._create_property_filter_method(property_name, "contains"),
                help_text=f"Filtrer par la propriété {property_name} contenant le texte spécifié (sensible à la casse)",
            ),
            f"{property_name}__icontains": CharFilter(
                method=self._create_property_filter_method(property_name, "icontains"),
                help_text=f"Filtrer par la propriété {property_name} contenant le texte spécifié (insensible à la casse)",
            ),
            f"{property_name}__startswith": CharFilter(
                method=self._create_property_filter_method(property_name, "startswith"),
                help_text=f"Filtrer par la propriété {property_name} commençant par le texte spécifié",
            ),
            f"{property_name}__endswith": CharFilter(
                method=self._create_property_filter_method(property_name, "endswith"),
                help_text=f"Filtrer par la propriété {property_name} se terminant par le texte spécifié",
            ),
            f"{property_name}__exact": CharFilter(
                method=self._create_property_filter_method(property_name, "exact"),
                help_text=f"Filtrer par la propriété {property_name} avec correspondance exacte",
            ),
        }

    def _generate_property_numeric_filters(
        self, property_name: str
    ) -> Dict[str, django_filters.Filter]:
        """Generate numeric filters for properties: gt, gte, lt, lte."""
        return {
            f"{property_name}": NumberFilter(
                method=self._create_property_filter_method(property_name, "exact"),
                help_text=f"Filtrer par la propriété {property_name} avec correspondance numérique exacte",
            ),
            f"{property_name}__gt": NumberFilter(
                method=self._create_property_filter_method(property_name, "gt"),
                help_text=f"Filtrer par la propriété {property_name} supérieure à la valeur spécifiée",
            ),
            f"{property_name}__gte": NumberFilter(
                method=self._create_property_filter_method(property_name, "gte"),
                help_text=f"Filtrer par la propriété {property_name} supérieure ou égale à la valeur spécifiée",
            ),
            f"{property_name}__lt": NumberFilter(
                method=self._create_property_filter_method(property_name, "lt"),
                help_text=f"Filtrer par la propriété {property_name} inférieure à la valeur spécifiée",
            ),
            f"{property_name}__lte": NumberFilter(
                method=self._create_property_filter_method(property_name, "lte"),
                help_text=f"Filtrer par la propriété {property_name} inférieure ou égale à la valeur spécifiée",
            ),
        }

    def _generate_property_boolean_filters(
        self, property_name: str
    ) -> Dict[str, django_filters.Filter]:
        """Generate boolean filters for properties."""
        return {
            f"{property_name}": BooleanFilter(
                method=self._create_property_filter_method(property_name, "exact"),
                help_text=f"Filtrer par la valeur booléenne de la propriété {property_name}",
            ),
        }

    def _generate_property_date_filters(
        self, property_name: str
    ) -> Dict[str, django_filters.Filter]:
        """Generate date-specific filters for properties: exact, gt, gte, lt, lte, year, month, day."""
        return {
            f"{property_name}": DateFilter(
                method=self._create_property_filter_method(property_name, "exact"),
                help_text=f"Filtrer par la propriété {property_name} avec une correspondance de date exacte",
            ),
            f"{property_name}__exact": DateFilter(
                method=self._create_property_filter_method(property_name, "exact"),
                help_text=f"Filtrer par la propriété {property_name} avec correspondance de date exacte",
            ),
            f"{property_name}__gt": DateFilter(
                method=self._create_property_filter_method(property_name, "gt"),
                help_text=f"Filtrer par la propriété {property_name} après la date spécifiée",
            ),
            f"{property_name}__gte": DateFilter(
                method=self._create_property_filter_method(property_name, "gte"),
                help_text=f"Filtrer par la propriété {property_name} à la date spécifiée ou après",
            ),
            f"{property_name}__lt": DateFilter(
                method=self._create_property_filter_method(property_name, "lt"),
                help_text=f"Filtrer par la propriété {property_name} avant la date spécifiée",
            ),
            f"{property_name}__lte": DateFilter(
                method=self._create_property_filter_method(property_name, "lte"),
                help_text=f"Filtrer par la propriété {property_name} à la date spécifiée ou avant",
            ),
            f"{property_name}__year": NumberFilter(
                method=self._create_property_filter_method(property_name, "year"),
                help_text=f"Filtrer par année de la propriété {property_name}",
            ),
            f"{property_name}__month": NumberFilter(
                method=self._create_property_filter_method(property_name, "month"),
                help_text=f"Filtrer par mois de la propriété {property_name}",
            ),
            f"{property_name}__day": NumberFilter(
                method=self._create_property_filter_method(property_name, "day"),
                help_text=f"Filtrer par jour de la propriété {property_name}",
            ),
        }

    def _generate_reverse_relationship_field_filters(
        self, model
    ) -> Dict[str, django_filters.Filter]:
        """
        Generate filters for actual fields of reverse-related models.

        This method creates filters that allow querying based on fields of models
        that have a foreign key pointing to the current model.

        Args:
            model: The Django model to generate reverse filters for

        Returns:
            Dict[str, django_filters.Filter]: Dictionary of reverse field filters
        """
        filters = {}

        # Get all reverse relationships for this model
        reverse_relations = []

        # Use the modern Django approach to get reverse relationships
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                # Include both OneToMany and OneToOne reverse relationships
                from django.db.models.fields.reverse_related import (
                    ManyToOneRel,
                    OneToOneRel,
                )

                if isinstance(rel, (OneToOneRel, ManyToOneRel)):
                    reverse_relations.append(rel)

        # Also check for forward OneToOne relationships that create reverse access
        for field in model._meta.get_fields():
            if field.is_relation and field.one_to_one and not field.many_to_one:
                # This is a forward OneToOne field, but we want to handle it as a reverse relation
                # for the purpose of generating filters on the related model's fields
                reverse_relations.append(field)

        for relation in reverse_relations:
            if hasattr(relation, "related_model"):
                related_model = relation.related_model
                # Handle different types of relations for accessor name
                if hasattr(relation, "get_accessor_name"):
                    relation_name = relation.get_accessor_name()
                elif hasattr(relation, "name"):
                    relation_name = relation.name
                else:
                    continue  # Skip if we can't determine the relation name

                # Skip if this model is excluded (for now, we'll include all models)
                # TODO: Implement model exclusion logic if needed
                # if self._is_model_excluded(related_model):
                #     continue

                # Generate filters for fields of the related model
                filters.update(
                    self._generate_reverse_nested_field_filters(
                        relation_name, related_model, depth=0
                    )
                )

        return filters

    def _generate_reverse_nested_field_filters(
        self, relation_name: str, related_model, depth: int = 0, max_depth: int = 2
    ) -> Dict[str, django_filters.Filter]:
        """
        Generate nested filters for reverse relationship fields.

        Args:
            relation_name: Name of the reverse relationship
            related_model: The related Django model
            depth: Current nesting depth
            max_depth: Maximum allowed nesting depth

        Returns:
            Dict[str, django_filters.Filter]: Dictionary of nested reverse field filters
        """
        filters = {}

        if depth >= max_depth or related_model is None:
            return filters

        # Get all fields from the related model
        for field in related_model._meta.get_fields():
            if field.is_relation:
                # Handle foreign key and one-to-one relationships
                if hasattr(field, "related_model") and (
                    field.many_to_one or field.one_to_one
                ):
                    field_name = f"{relation_name}__{field.name}"
                    filters.update(
                        self._generate_reverse_foreign_key_filters(field_name, field)
                    )

                    # Recursive nesting for deeper relationships
                    if depth < max_depth - 1:
                        nested_filters = self._generate_reverse_nested_field_filters(
                            field_name, field.related_model, depth + 1, max_depth
                        )
                        filters.update(nested_filters)

                # Handle many-to-many relationships
                elif field.many_to_many:
                    field_name = f"{relation_name}__{field.name}"
                    filters.update(
                        self._generate_reverse_many_to_many_filters(field_name, field)
                    )
            else:
                # Handle regular fields
                field_name = f"{relation_name}__{field.name}"

                if isinstance(field, (models.CharField, models.TextField)):
                    filters.update(
                        self._generate_reverse_text_filters(field_name, field)
                    )
                elif isinstance(
                    field, (models.IntegerField, models.FloatField, models.DecimalField)
                ):
                    filters.update(
                        self._generate_reverse_numeric_filters(field_name, field)
                    )
                elif isinstance(field, (models.DateField, models.DateTimeField)):
                    filters.update(
                        self._generate_reverse_date_filters(field_name, field)
                    )
                elif isinstance(field, models.BooleanField):
                    filters.update(
                        self._generate_reverse_boolean_filters(field_name, field)
                    )
                elif isinstance(field, models.EmailField):
                    filters.update(
                        self._generate_reverse_text_filters(field_name, field)
                    )
                elif isinstance(field, models.URLField):
                    filters.update(
                        self._generate_reverse_text_filters(field_name, field)
                    )

        return filters

    def _generate_reverse_text_filters(
        self, field_name: str, field
    ) -> Dict[str, django_filters.Filter]:
        """Generate text-based filters for reverse relationship text fields."""
        return {
            f"{field_name}": CharFilter(
                field_name=field_name,
                help_text=f"Filtrer par {field_name} avec une correspondance de texte exacte",
            ),
            f"{field_name}__contains": CharFilter(
                field_name=f"{field_name}__contains",
                help_text=f"Filtrer par {field_name} contenant le texte spécifié (sensible à la casse)",
            ),
            f"{field_name}__icontains": CharFilter(
                field_name=f"{field_name}__icontains",
                help_text=f"Filtrer par {field_name} contenant le texte spécifié (insensible à la casse)",
            ),
            f"{field_name}__startswith": CharFilter(
                field_name=f"{field_name}__startswith",
                help_text=f"Filtrer par {field_name} commençant par le texte spécifié",
            ),
            f"{field_name}__endswith": CharFilter(
                field_name=f"{field_name}__endswith",
                help_text=f"Filtrer par {field_name} se terminant par le texte spécifié",
            ),
            f"{field_name}__exact": CharFilter(
                field_name=f"{field_name}__exact",
                help_text=f"Filtrer par {field_name} avec correspondance exacte",
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                help_text=f"Filtrer selon que {field_name} est nul",
            ),
        }

    def _generate_reverse_numeric_filters(
        self, field_name: str, field
    ) -> Dict[str, django_filters.Filter]:
        """Generate numeric filters for reverse relationship numeric fields."""
        return {
            f"{field_name}": NumberFilter(
                field_name=field_name,
                help_text=f"Filtrer par {field_name} avec une correspondance numérique exacte",
            ),
            f"{field_name}__in": type(
                f"{field_name.title()}InFilter",
                (django_filters.BaseInFilter, NumberFilter),
                {},
            )(
                field_name=field_name,
                help_text=f"Filtrer par plusieurs valeurs de {field_name}",
            ),
            f"{field_name}__gt": NumberFilter(
                field_name=f"{field_name}__gt",
                help_text=f"Filtrer par {field_name} supérieur à la valeur spécifiée",
            ),
            f"{field_name}__gte": NumberFilter(
                field_name=f"{field_name}__gte",
                help_text=f"Filtrer par {field_name} supérieur ou égal à la valeur spécifiée",
            ),
            f"{field_name}__lt": NumberFilter(
                field_name=f"{field_name}__lt",
                help_text=f"Filtrer par {field_name} inférieur à la valeur spécifiée",
            ),
            f"{field_name}__lte": NumberFilter(
                field_name=f"{field_name}__lte",
                help_text=f"Filtrer par {field_name} inférieur ou égal à la valeur spécifiée",
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                help_text=f"Filtrer selon que {field_name} est nul",
            ),
        }

    def _generate_reverse_date_filters(
        self, field_name: str, field
    ) -> Dict[str, django_filters.Filter]:
        """Generate date filters for reverse relationship date fields."""
        filters = {
            f"{field_name}": DateFilter(
                field_name=field_name,
                help_text=f"Filtrer par {field_name} avec une correspondance de date exacte",
            ),
            f"{field_name}__gt": DateFilter(
                field_name=f"{field_name}__gt",
                help_text=f"Filtrer par {field_name} après la date spécifiée",
            ),
            f"{field_name}__gte": DateFilter(
                field_name=f"{field_name}__gte",
                help_text=f"Filtrer par {field_name} à la date spécifiée ou après",
            ),
            f"{field_name}__lt": DateFilter(
                field_name=f"{field_name}__lt",
                help_text=f"Filtrer par {field_name} avant la date spécifiée",
            ),
            f"{field_name}__lte": DateFilter(
                field_name=f"{field_name}__lte",
                help_text=f"Filtrer par {field_name} à la date spécifiée ou avant",
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                help_text=f"Filtrer selon que {field_name} est nul",
            ),
        }

        # Add datetime-specific filters if it's a DateTimeField
        if isinstance(field, models.DateTimeField):
            filters.update(
                {
                    f"{field_name}__year": NumberFilter(
                        field_name=f"{field_name}__year",
                        help_text=f"Filtrer par année de {field_name}",
                    ),
                    f"{field_name}__month": NumberFilter(
                        field_name=f"{field_name}__month",
                        help_text=f"Filtrer par mois de {field_name}",
                    ),
                    f"{field_name}__day": NumberFilter(
                        field_name=f"{field_name}__day",
                        help_text=f"Filtrer par jour de {field_name}",
                    ),
                }
            )

        return filters

    def _generate_reverse_boolean_filters(
        self, field_name: str, field
    ) -> Dict[str, django_filters.Filter]:
        """Generate boolean filters for reverse relationship boolean fields."""
        return {
            f"{field_name}": BooleanFilter(
                field_name=field_name, help_text=f"Filter by {field_name} boolean value"
            ),
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                help_text=f"Filter by whether {field_name} is null",
            ),
        }

    def _generate_reverse_foreign_key_filters(
        self, field_name: str, field
    ) -> Dict[str, django_filters.Filter]:
        """Generate filters for reverse relationship foreign key fields."""
        filters: Dict[str, django_filters.Filter] = {
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                help_text=f"Filter by whether {field_name} is null",
            ),
        }

        related_model = getattr(field, "related_model", None)
        if related_model:
            filters[f"{field_name}"] = ModelChoiceFilter(
                field_name=field_name,
                queryset=related_model.objects.all(),
                help_text=f"Filter by {field_name} foreign key",
            )
            filters[f"{field_name}__in"] = ModelMultipleChoiceFilter(
                field_name=field_name,
                queryset=related_model.objects.all(),
                to_field_name="pk",
                help_text=f"Filter by multiple {field_name} foreign key IDs",
            )

        return filters

    def _generate_reverse_many_to_many_filters(
        self, field_name: str, field
    ) -> Dict[str, django_filters.Filter]:
        """Generate filters for reverse relationship many-to-many fields."""
        filters: Dict[str, django_filters.Filter] = {
            f"{field_name}__isnull": BooleanFilter(
                field_name=f"{field_name}__isnull",
                help_text=f"Filter by whether {field_name} has any related objects",
            ),
        }

        related_model = getattr(field, "related_model", None)
        if related_model:
            filters[f"{field_name}"] = ModelMultipleChoiceFilter(
                field_name=field_name,
                queryset=related_model.objects.all(),
                help_text=f"Filter by {field_name} many-to-many relationship",
            )
            filters[f"{field_name}__in"] = ModelMultipleChoiceFilter(
                field_name=field_name,
                queryset=related_model.objects.all(),
                to_field_name="pk",
                help_text=f"Filter by multiple {field_name} many-to-many IDs",
            )

        return filters

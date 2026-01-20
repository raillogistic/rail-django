"""
Base query building utilities shared across list and paginated queries.

This module provides common infrastructure for query generation to reduce
code duplication between queries_list.py and queries_pagination.py.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple, Type

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models

from .exceptions import (
    FilterApplicationError,
    PresetFilterError,
    SavedFilterError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Reserved argument names that should not be passed to FilterSet
RESERVED_QUERY_ARGS: FrozenSet[str] = frozenset([
    "where",
    "order_by",
    "offset",
    "limit",
    "page",
    "per_page",
    "include",
    "presets",
    "savedFilter",
    "distinct_on",
    "quick",
    "search",
    "group_by",
])


# =============================================================================
# Query Context
# =============================================================================

@dataclass
class QueryContext:
    """
    Context object passed through query building pipeline.

    Holds all the state needed for query filtering and processing.
    """
    model: Type[models.Model]
    queryset: models.QuerySet
    info: Any  # graphene.ResolveInfo
    kwargs: Dict[str, Any]
    graphql_meta: Any
    filter_applicator: Any
    filter_class: Any
    ordering_config: Any
    settings: Any
    schema_name: str = "default"

    # Internal state for filter pipeline
    _where: Optional[Dict[str, Any]] = field(default=None, repr=False)


# =============================================================================
# Query Filter Pipeline
# =============================================================================

class QueryFilterPipeline:
    """
    Pipeline for applying filters to a queryset in correct order.

    This class encapsulates the complex filter application logic that was
    previously duplicated between list and paginated queries.

    Usage:
        pipeline = QueryFilterPipeline(context)
        queryset = pipeline.apply_all()
    """

    def __init__(self, context: QueryContext):
        """
        Initialize the filter pipeline.

        Args:
            context: QueryContext with all necessary state
        """
        self.context = context
        self._where: Optional[Dict[str, Any]] = None

    def apply_all(self) -> models.QuerySet:
        """
        Apply all filters in the correct order.

        Returns:
            Filtered queryset
        """
        queryset = self.context.queryset

        # 1. Apply saved filter (merges into where)
        self._apply_saved_filter()

        # 2. Apply presets (merges into where)
        self._apply_presets()

        # 3. Apply include IDs (merges into where)
        self._apply_include_ids()

        # 4. Apply quick filter (merges into where)
        self._apply_quick_filter()

        # 5. Apply where filter
        queryset = self._apply_where_filter(queryset)

        # 6. Apply basic filters
        queryset = self._apply_basic_filters(queryset)

        self.context.queryset = queryset
        return queryset

    def _apply_quick_filter(self) -> None:
        """Apply quick filter by merging into where dict."""
        quick_value = self.context.kwargs.get("quick")
        if not quick_value:
            return

        current_where = self._get_current_where()
        current_where["quick"] = quick_value
        self._where = current_where

    def _apply_saved_filter(self) -> None:
        """Load and merge saved filter if specified."""
        saved_filter_id = self.context.kwargs.get("savedFilter")
        if not saved_filter_id or not self.context.filter_applicator:
            return

        try:
            from ..saved_filter import SavedFilter

            saved = self._load_saved_filter(saved_filter_id)
            if saved and saved.filter_json:
                self._update_usage_stats(saved)
                self._where = self._merge_where(saved.filter_json, self._get_current_where())
        except ImportError:
            logger.debug("SavedFilter model not available")
        except (models.ObjectDoesNotExist, ValueError, TypeError) as e:
            # Specific exceptions for database/data issues
            logger.warning(
                f"Failed to load saved filter '{saved_filter_id}': {e}",
                extra={"saved_filter_id": saved_filter_id, "error_type": type(e).__name__},
            )
        except AttributeError as e:
            # Missing attributes on saved filter object
            logger.warning(
                f"Saved filter '{saved_filter_id}' has invalid structure: {e}",
                extra={"saved_filter_id": saved_filter_id},
            )
        except Exception as e:
            # Catch-all for unexpected errors, log with full context
            logger.exception(
                f"Unexpected error applying saved filter '{saved_filter_id}'",
                extra={"saved_filter_id": saved_filter_id},
            )

    def _load_saved_filter(self, name_or_id: str):
        """
        Load saved filter by ID or name.

        Args:
            name_or_id: Filter ID or name

        Returns:
            SavedFilter instance or None
        """
        from ..saved_filter import SavedFilter

        # Try ID first
        if str(name_or_id).isdigit():
            saved = SavedFilter.objects.filter(pk=name_or_id).first()
            if saved:
                return saved

        # Try name with access control
        user = getattr(self.context.info.context, "user", None)
        q = models.Q(name=name_or_id, model_name=self.context.model.__name__)

        if user and getattr(user, "is_authenticated", False):
            q &= models.Q(is_shared=True) | models.Q(created_by=user)
        else:
            q &= models.Q(is_shared=True)

        return SavedFilter.objects.filter(q).first()

    def _update_usage_stats(self, saved) -> None:
        """
        Update saved filter usage statistics.

        Args:
            saved: SavedFilter instance
        """
        from ..saved_filter import SavedFilter

        SavedFilter.objects.filter(pk=saved.pk).update(
            use_count=models.F("use_count") + 1,
            last_used_at=models.functions.Now()
        )

    def _apply_presets(self) -> None:
        """Apply filter presets."""
        presets = self.context.kwargs.get("presets")
        if not presets or not self.context.filter_applicator:
            return

        current_where = self._get_current_where()
        self._where = self.context.filter_applicator.apply_presets(
            current_where, presets, self.context.model
        )

    def _apply_include_ids(self) -> None:
        """Merge include IDs into where filter."""
        include_ids = self.context.kwargs.get("include")
        if not include_ids:
            return

        current_where = self._get_current_where()

        # Merge existing include with new include
        existing_include = current_where.get("include", [])
        if not isinstance(existing_include, list):
            existing_include = [existing_include] if existing_include else []

        if isinstance(include_ids, (list, tuple)):
            existing_include.extend(include_ids)
        else:
            existing_include.append(include_ids)

        current_where["include"] = existing_include
        self._where = current_where

    def _apply_where_filter(self, queryset: models.QuerySet) -> models.QuerySet:
        """
        Apply the where filter to queryset.

        Args:
            queryset: Django queryset

        Returns:
            Filtered queryset
        """
        where = self._get_current_where()
        if where and self.context.filter_applicator:
            return self.context.filter_applicator.apply_where_filter(
                queryset, where, self.context.model
            )
        return queryset

    def _apply_basic_filters(self, queryset: models.QuerySet) -> models.QuerySet:
        """
        Apply basic FilterSet filters.

        Args:
            queryset: Django queryset

        Returns:
            Filtered queryset
        """
        basic_filters = {
            k: v for k, v in self.context.kwargs.items()
            if k not in RESERVED_QUERY_ARGS and v is not None
        }

        if basic_filters and self.context.filter_class:
            filterset = self.context.filter_class(basic_filters, queryset)
            if filterset.is_valid():
                return filterset.qs
            else:
                logger.debug(f"Invalid filters: {filterset.errors}")
                return queryset.none()

        return queryset

    def _get_current_where(self) -> Dict[str, Any]:
        """
        Get current where dict, initializing from kwargs if needed.

        Returns:
            Where filter dictionary
        """
        if self._where is None:
            where = self.context.kwargs.get("where")
            if where is None:
                self._where = {}
            elif isinstance(where, dict):
                self._where = dict(where)  # Copy to avoid mutation
            else:
                try:
                    self._where = dict(where)
                except (TypeError, ValueError) as e:
                    # where is not dict-convertible (e.g., invalid type)
                    logger.debug(
                        f"Could not convert 'where' to dict: {type(where).__name__}. "
                        f"Using empty filter. Error: {e}"
                    )
                    self._where = {}
        return self._where

    def _merge_where(self, base: Dict, override: Optional[Dict]) -> Dict:
        """
        Deep merge two where dicts.

        Args:
            base: Base dictionary
            override: Override dictionary

        Returns:
            Merged dictionary
        """
        if not override:
            return dict(base) if base else {}
        if not base:
            return dict(override) if override else {}
        return self.context.filter_applicator._deep_merge(base, override)


# =============================================================================
# Query Ordering Helper
# =============================================================================

class QueryOrderingHelper:
    """
    Helper for applying ordering to querysets.

    Handles database ordering, count annotations, distinct on,
    and property-based ordering.
    """

    def __init__(
        self,
        query_generator,
        model: Type[models.Model],
        ordering_config: Any,
        settings: Any,
    ):
        """
        Initialize the ordering helper.

        Args:
            query_generator: Parent QueryGenerator instance
            model: Django model class
            ordering_config: Ordering configuration from GraphQLMeta
            settings: QueryGeneratorSettings
        """
        self.qg = query_generator
        self.model = model
        self.ordering_config = ordering_config
        self.settings = settings

    def apply(
        self,
        queryset: models.QuerySet,
        order_by: Optional[List[str]],
        distinct_on: Optional[List[str]] = None,
    ) -> Tuple[models.QuerySet, Optional[List[Any]], bool, Optional[int]]:
        """
        Apply ordering to queryset.

        Args:
            queryset: Django queryset
            order_by: List of ordering specs
            distinct_on: List of distinct on fields

        Returns:
            Tuple of (queryset, items_if_property_ordered, has_property_ordering, uncapped_total)
        """
        items = None
        has_prop_ordering = False
        uncapped_total = None

        normalized = self.qg._normalize_ordering_specs(order_by, self.ordering_config)

        if not normalized and not distinct_on:
            return queryset, None, False, None

        if normalized:
            # Apply count annotations
            queryset, normalized = self.qg._apply_count_annotations_for_ordering(
                queryset, self.model, normalized
            )

            # Split into DB and property specs
            db_specs, prop_specs = self.qg._split_order_specs(self.model, normalized)

            # Apply distinct on if specified
            if distinct_on:
                queryset = self.qg._apply_distinct_on(queryset, distinct_on, db_specs)
            elif db_specs:
                queryset = queryset.order_by(*db_specs)

            # Handle property ordering
            if prop_specs:
                has_prop_ordering = True
                queryset, items, uncapped_total = self._apply_property_ordering(
                    queryset, prop_specs
                )
        elif distinct_on:
            # Distinct on without explicit ordering
            queryset = self.qg._apply_distinct_on(queryset, distinct_on, [])

        return queryset, items, has_prop_ordering, uncapped_total

    def _apply_property_ordering(
        self,
        queryset: models.QuerySet,
        prop_specs: List[str],
    ) -> Tuple[models.QuerySet, List[Any], Optional[int]]:
        """
        Apply property-based ordering (requires list materialization).

        Args:
            queryset: Django queryset
            prop_specs: List of property ordering specs

        Returns:
            Tuple of (queryset, items, uncapped_total)
        """
        # Get true count before capping
        uncapped_total = queryset.count()

        prop_limit = getattr(self.settings, "max_property_ordering_results", None)
        warn_on_cap = bool(
            getattr(self.settings, "property_ordering_warn_on_cap", True)
        )

        if prop_limit and uncapped_total > prop_limit:
            if warn_on_cap:
                logger.warning(
                    "Property ordering on %s capped at %s results (total: %s).",
                    self.model.__name__,
                    prop_limit,
                    uncapped_total,
                )
            queryset = queryset[:prop_limit]

        items = list(queryset)
        items = self.qg._apply_property_ordering(items, prop_specs)

        return queryset, items, uncapped_total


# =============================================================================
# Argument Builder
# =============================================================================

def build_query_arguments(
    settings,
    ordering_config,
    nested_where_input=None,
    filter_class=None,
    include_pagination: bool = True,
    use_page_based: bool = False,
) -> Dict[str, Any]:
    """
    Build GraphQL query arguments declaratively.

    Args:
        settings: QueryGeneratorSettings
        ordering_config: Ordering configuration from GraphQLMeta
        nested_where_input: Generated where input type
        filter_class: Generated filter class
        include_pagination: Whether to include pagination args
        use_page_based: Use page/per_page instead of offset/limit

    Returns:
        Dictionary of graphene.Argument instances
    """
    import graphene

    from .queries_ordering import get_default_ordering

    arguments = {}

    # Where filter (Prisma/Hasura style)
    if nested_where_input:
        arguments["where"] = graphene.Argument(
            nested_where_input,
            description="Nested filtering with typed field inputs (Prisma/Hasura style)",
        )
        arguments["presets"] = graphene.Argument(
            graphene.List(graphene.String),
            description="List of filter presets to apply",
        )
        arguments["savedFilter"] = graphene.Argument(
            graphene.String,
            description="Name or ID of a saved filter to apply",
        )

    # Include filter
    arguments["include"] = graphene.Argument(
        graphene.List(graphene.ID),
        description="Include specific IDs regardless of other filters",
    )

    # Quick search from filter class
    if filter_class:
        if "quick" in getattr(filter_class, "base_filters", {}):
            arguments["quick"] = graphene.Argument(
                graphene.String,
                description="Quick search across multiple text fields",
            )

    # Pagination
    if include_pagination:
        if use_page_based:
            arguments["page"] = graphene.Int(
                description="Page number (1-based)",
                default_value=1,
            )
            arguments["per_page"] = graphene.Int(
                description="Number of records per page",
                default_value=settings.default_page_size,
            )
        else:
            arguments["offset"] = graphene.Int(description="Number of records to skip")
            arguments["limit"] = graphene.Int(description="Number of records to return")

    # Ordering
    if getattr(settings, "enable_ordering", True):
        order_desc = "Fields to order by (prefix with - for descending)"
        allowed = getattr(ordering_config, "allowed", None)
        if allowed:
            order_desc += f". Allowed: {', '.join(allowed)}"

        arguments["order_by"] = graphene.List(
            graphene.String,
            description=order_desc,
            default_value=get_default_ordering(ordering_config),
        )
        arguments["distinct_on"] = graphene.List(
            graphene.String,
            description="Distinct by fields (Postgres DISTINCT ON). Must match prefix of order_by.",
        )

    return arguments


# =============================================================================
# Filter Type Mapping Helper
# =============================================================================

def map_filter_to_graphql_type(filter_field, name: str):
    """
    Map a django-filter field to appropriate GraphQL type.

    Args:
        filter_field: django-filter field instance
        name: Field name

    Returns:
        GraphQL type for the argument
    """
    import graphene

    if name == "include":
        return graphene.List(graphene.ID)

    field_type = graphene.String  # Default

    # Check field class name for type hints
    class_name = filter_field.__class__.__name__

    if hasattr(filter_field, "field_class"):
        if "Number" in class_name or "Integer" in class_name:
            field_type = graphene.Float
        elif "Boolean" in class_name:
            field_type = graphene.Boolean
        elif "Date" in class_name:
            field_type = graphene.Date

    # Handle list filters
    if "ModelMultipleChoiceFilter" in class_name or name.endswith("__in"):
        if "Number" in class_name or "Integer" in class_name:
            field_type = graphene.List(graphene.Float)
        else:
            field_type = graphene.List(graphene.String)

    return field_type


# =============================================================================
# Default Ordering Config Factory
# =============================================================================

def create_default_ordering_config():
    """
    Create a default ordering configuration.

    Returns:
        Object with allowed and default attributes
    """
    return type("OrderingConfig", (), {"allowed": [], "default": []})()

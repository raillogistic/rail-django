# Query Generators Improvement Plan

This document outlines the technical implementation plan to fix bugs, improve performance, and enhance code quality in the Rail Django query generators.

---

## Table of Contents

1. [Critical Bug Fixes](#1-critical-bug-fixes)
2. [Code Deduplication](#2-code-deduplication)
3. [Performance Optimizations](#3-performance-optimizations)
4. [Security Hardening](#4-security-hardening)
5. [Code Quality Improvements](#5-code-quality-improvements)
6. [Implementation Order](#6-implementation-order)

---

## 1. Critical Bug Fixes

### 1.1 Fix Unbound Variable in Paginated Query

**File:** `rail_django/generators/queries_pagination.py`

**Problem:** `nested_filter_applicator` is used at line 121 before initialization at line 319.

**Fix:** Move filter initialization before the resolver definition.

```python
# BEFORE (broken):
def generate_paginated_query(...):
    # ... setup code ...

    @optimize_query()
    def resolver(root, info, **kwargs):
        # ...
        if saved_filter_name_or_id and nested_filter_applicator:  # ERROR: not defined yet!
            ...

    # Filter initialization happens AFTER resolver definition
    nested_filter_applicator = _get_nested_filter_applicator(self.schema_name)

# AFTER (fixed):
def generate_paginated_query(...):
    # ... setup code ...

    # Move filter initialization BEFORE resolver
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
    def resolver(root, info, **kwargs):
        # Now nested_filter_applicator is in scope via closure
        if saved_filter_name_or_id and nested_filter_applicator:
            ...
```

---

### 1.2 Fix Input Dictionary Mutation

**File:** `rail_django/generators/filter_inputs.py`

**Problem:** `pop()` mutates the caller's dictionary, causing issues if reused.

**Fix:** Work on a shallow copy.

```python
# BEFORE (mutates input):
def apply_where_filter(self, queryset, where_input, model=None, ...):
    if not where_input:
        return queryset

    include_ids = where_input.pop("include", None)  # Mutates!
    quick_value = where_input.pop("quick", None)
    search_input = where_input.pop("search", None)

# AFTER (safe):
def apply_where_filter(self, queryset, where_input, model=None, ...):
    if not where_input:
        return queryset

    # Work on a copy to avoid mutating caller's dict
    where_input = dict(where_input)

    include_ids = where_input.pop("include", None)
    quick_value = where_input.pop("quick", None)
    search_input = where_input.pop("search", None)
```

---

### 1.3 Fix Dead Code / Impossible Conditions

**Files:** `queries_list.py:148-149`, `queries_pagination.py:149-150`

**Problem:** Checking `if where is None` after `if where:` is always False.

**Fix:** Remove impossible branch.

```python
# BEFORE:
if where:
    if where is None:  # Impossible
        where = {}
    if not isinstance(where, dict):
        try:
            where = dict(where)
        except Exception:
            pass

# AFTER:
if where and not isinstance(where, dict):
    try:
        where = dict(where)
    except Exception:
        pass
```

---

### 1.4 Fix `_every` Filter Implementation

**File:** `rail_django/generators/filter_inputs.py`

**Problem:** `_every` has same logic as `_some`, but semantics require "ALL must match".

**Fix:** Implement proper `_every` semantics using subquery exclusion.

```python
# BEFORE (incorrect):
if field_name.endswith("_every"):
    base_field = field_name[:-6]
    sub_q = self._build_q_from_where(filter_value, model, f"{base_field}__")
    return sub_q  # Wrong: same as _some

# AFTER (correct):
if field_name.endswith("_every"):
    """
    _every means: ALL related objects must match the condition.
    Implementation: Exclude records where ANY related object does NOT match.

    SQL equivalent:
        NOT EXISTS (
            SELECT 1 FROM related_table
            WHERE related_table.fk = main.id
            AND NOT (condition)
        )
    """
    base_field = field_name[:-6]

    # Get the related model for subquery
    try:
        field = self._get_relation_field(model, base_field)
        if field is None:
            return Q()

        related_model = field.related_model
        reverse_name = field.remote_field.get_accessor_name() if hasattr(field, 'remote_field') else base_field

        # Build the negated condition
        negated_q = ~self._build_q_from_where(filter_value, related_model, "")

        # Build subquery for non-matching related objects
        from django.db.models import Exists, OuterRef

        # Get the FK field name pointing back to parent
        fk_field = self._get_fk_to_parent(related_model, model)
        if fk_field:
            non_matching = related_model.objects.filter(
                **{fk_field: OuterRef('pk')}
            ).filter(negated_q)

            # Exclude parents that have ANY non-matching children
            return ~Q(Exists(non_matching))
    except Exception as e:
        logger.debug(f"Could not build _every filter for {base_field}: {e}")

    # Fallback to _some behavior with warning
    logger.warning(f"_every filter for {base_field} falling back to _some semantics")
    return self._build_q_from_where(filter_value, model, f"{base_field}__")

def _get_relation_field(self, model, field_name):
    """Get the relation field from model."""
    try:
        return model._meta.get_field(field_name)
    except Exception:
        # Check reverse relations
        for rel in model._meta.related_objects:
            if rel.get_accessor_name() == field_name:
                return rel
        return None

def _get_fk_to_parent(self, related_model, parent_model):
    """Find the FK field in related_model pointing to parent_model."""
    for field in related_model._meta.get_fields():
        if hasattr(field, 'related_model') and field.related_model == parent_model:
            return field.name
    return None
```

---

### 1.5 Fix Property Ordering Total Count

**File:** `rail_django/generators/queries_pagination.py`

**Problem:** When property ordering is used, `total_count` uses capped `len(items)`.

**Fix:** Calculate total count before property ordering cap.

```python
# BEFORE:
if prop_specs:
    prop_limit = getattr(self.settings, "max_property_ordering_results", None)
    if prop_limit:
        max_items = min(prop_limit, page * per_page)
        queryset = queryset[:max_items]
    items = list(queryset)
    items = self._apply_property_ordering(items, prop_specs)

# Calculate pagination values
if items is not None:
    total_count = len(items)  # BUG: This is capped!
else:
    total_count = queryset.count()

# AFTER:
# Calculate total count BEFORE any capping
uncapped_total = None

if order_by:
    queryset, order_by = self._apply_count_annotations_for_ordering(queryset, model, order_by)
    db_specs, prop_specs = self._split_order_specs(model, order_by)

    if distinct_on:
        queryset = self._apply_distinct_on(queryset, distinct_on, db_specs)
    elif db_specs:
        queryset = queryset.order_by(*db_specs)

    if prop_specs:
        # Get true count before capping
        uncapped_total = queryset.count()

        prop_limit = getattr(self.settings, "max_property_ordering_results", None)
        if prop_limit:
            max_items = min(prop_limit, page * per_page)
            if max_items < uncapped_total:
                logger.warning(
                    "Property ordering on %s capped at %s results (total: %s).",
                    model.__name__, max_items, uncapped_total
                )
            queryset = queryset[:max_items]
        items = list(queryset)
        items = self._apply_property_ordering(items, prop_specs)

# Calculate pagination values
if uncapped_total is not None:
    total_count = uncapped_total
elif items is not None:
    total_count = len(items)
else:
    total_count = queryset.count()
```

---

### 1.6 Fix Empty Page Edge Case

**File:** `rail_django/generators/queries_pagination.py`

**Problem:** When `total_count = 0`, returns `current_page = 1, page_count = 0`.

**Fix:** Handle empty results consistently.

```python
# BEFORE:
page_count = (total_count + per_page - 1) // per_page
page = max(1, min(page, page_count))  # When page_count=0, this gives page=1

# AFTER:
page_count = (total_count + per_page - 1) // per_page if total_count > 0 else 0

# Handle empty results
if page_count == 0:
    page = 1  # Show page 1 even with no results (consistent UX)
    items = []
else:
    page = max(1, min(page, page_count))
    # ... normal pagination logic
```

---

## 2. Code Deduplication

### 2.1 Create Shared Query Builder Helper

**New File:** `rail_django/generators/queries_base.py`

Extract common logic from `queries_list.py` and `queries_pagination.py`.

```python
"""
Base query building utilities shared across list and paginated queries.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from django.db import models

logger = logging.getLogger(__name__)


@dataclass
class QueryContext:
    """Context object passed through query building pipeline."""
    model: Type[models.Model]
    queryset: models.QuerySet
    info: Any  # graphene.ResolveInfo
    kwargs: Dict[str, Any]
    graphql_meta: Any
    filter_applicator: Any
    filter_class: Any
    ordering_config: Any
    settings: Any


class QueryFilterPipeline:
    """
    Pipeline for applying filters to a queryset in correct order.

    Usage:
        pipeline = QueryFilterPipeline(context)
        queryset = pipeline.apply_all()
    """

    def __init__(self, context: QueryContext):
        self.context = context
        self._where = None

    def apply_all(self) -> models.QuerySet:
        """Apply all filters in the correct order."""
        queryset = self.context.queryset

        # 1. Apply saved filter (merges into where)
        self._apply_saved_filter()

        # 2. Apply presets (merges into where)
        self._apply_presets()

        # 3. Apply include IDs (merges into where)
        self._apply_include_ids()

        # 4. Apply where filter
        queryset = self._apply_where_filter(queryset)

        # 5. Apply basic filters
        queryset = self._apply_basic_filters(queryset)

        self.context.queryset = queryset
        return queryset

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
                self._where = self._merge_where(saved.filter_json, self._where)
        except Exception as e:
            logger.warning(f"Failed to apply saved filter '{saved_filter_id}': {e}")

    def _load_saved_filter(self, name_or_id: str):
        """Load saved filter by ID or name."""
        from ..saved_filter import SavedFilter

        # Try ID first
        if str(name_or_id).isdigit():
            saved = SavedFilter.objects.filter(pk=name_or_id).first()
            if saved:
                return saved

        # Try name
        user = getattr(self.context.info.context, "user", None)
        q = models.Q(name=name_or_id, model_name=self.context.model.__name__)

        if user and getattr(user, "is_authenticated", False):
            q &= models.Q(is_shared=True) | models.Q(created_by=user)
        else:
            q &= models.Q(is_shared=True)

        return SavedFilter.objects.filter(q).first()

    def _update_usage_stats(self, saved) -> None:
        """Update saved filter usage statistics."""
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
        """Apply the where filter to queryset."""
        where = self._get_current_where()
        if where and self.context.filter_applicator:
            return self.context.filter_applicator.apply_where_filter(
                queryset, where, self.context.model
            )
        return queryset

    def _apply_basic_filters(self, queryset: models.QuerySet) -> models.QuerySet:
        """Apply basic FilterSet filters."""
        excluded_keys = RESERVED_QUERY_ARGS
        basic_filters = {
            k: v for k, v in self.context.kwargs.items()
            if k not in excluded_keys and v is not None
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
        """Get current where dict, initializing from kwargs if needed."""
        if self._where is None:
            where = self.context.kwargs.get("where")
            if where is None:
                self._where = {}
            elif isinstance(where, dict):
                self._where = dict(where)  # Copy to avoid mutation
            else:
                try:
                    self._where = dict(where)
                except Exception:
                    self._where = {}
        return self._where

    def _merge_where(self, base: Dict, override: Optional[Dict]) -> Dict:
        """Deep merge two where dicts."""
        if not override:
            return dict(base)
        if not base:
            return dict(override)
        return self.context.filter_applicator._deep_merge(base, override)


# Constants for reserved argument names
RESERVED_QUERY_ARGS = frozenset([
    "where", "order_by", "offset", "limit", "page", "per_page",
    "include", "presets", "savedFilter", "distinct_on", "quick"
])


class QueryOrderingHelper:
    """Helper for applying ordering to querysets."""

    def __init__(self, query_generator, model, ordering_config, settings):
        self.qg = query_generator
        self.model = model
        self.ordering_config = ordering_config
        self.settings = settings

    def apply(
        self,
        queryset: models.QuerySet,
        order_by: Optional[List[str]],
        distinct_on: Optional[List[str]] = None,
    ) -> tuple[models.QuerySet, Optional[List[Any]], bool]:
        """
        Apply ordering to queryset.

        Returns:
            Tuple of (queryset, items_if_property_ordered, has_property_ordering)
        """
        items = None
        has_prop_ordering = False

        normalized = self.qg._normalize_ordering_specs(order_by, self.ordering_config)

        if not normalized:
            return queryset, None, False

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
            items = self._apply_property_ordering(queryset, prop_specs)

        return queryset, items, has_prop_ordering

    def _apply_property_ordering(
        self,
        queryset: models.QuerySet,
        prop_specs: List[str],
    ) -> List[Any]:
        """Apply property-based ordering (requires list materialization)."""
        prop_limit = getattr(self.settings, "max_property_ordering_results", None)

        if prop_limit:
            queryset = queryset[:prop_limit]

        items = list(queryset)
        return self.qg._apply_property_ordering(items, prop_specs)


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
        for name in ("quick",):
            if name in filter_class.base_filters:
                arguments[name] = graphene.Argument(
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
    if settings.enable_ordering:
        order_desc = "Fields to order by (prefix with - for descending)"
        if ordering_config and getattr(ordering_config, "allowed", None):
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

    return arguments
```

---

### 2.2 Refactor `queries_list.py` to Use Shared Code

```python
"""
Single and list query builders.
"""
import logging
from typing import Any, List, Optional, Type, Union

import graphene
from django.db import models

from ..core.meta import get_model_graphql_meta
from ..extensions.optimization import optimize_query
from .queries_base import (
    QueryContext,
    QueryFilterPipeline,
    QueryOrderingHelper,
    build_query_arguments,
)

logger = logging.getLogger(__name__)


def _get_nested_filter_generator(schema_name: str):
    from .filter_inputs import NestedFilterInputGenerator
    return NestedFilterInputGenerator(schema_name=schema_name)


def _get_nested_filter_applicator(schema_name: str):
    from .filter_inputs import NestedFilterApplicator
    return NestedFilterApplicator(schema_name=schema_name)


def generate_single_query(
    self, model: Type[models.Model], manager_name: str = "objects"
) -> graphene.Field:
    """Generate a single object query for a model."""
    model_type = self.type_generator.generate_object_type(model)
    graphql_meta = get_model_graphql_meta(model)

    def resolve_single(root, info, id):
        try:
            self._enforce_model_permission(info, model, "retrieve", graphql_meta)
            manager = getattr(model, manager_name)
            queryset = self._apply_tenant_scope(
                manager.all(), info, model, operation="retrieve"
            )
            instance = queryset.get(pk=id)
            self._enforce_tenant_access(instance, info, model, operation="retrieve")
            graphql_meta.ensure_operation_access("retrieve", info=info, instance=instance)
            return self._apply_field_masks(instance, info, model)
        except model.DoesNotExist:
            return None

    return graphene.Field(
        model_type,
        id=graphene.ID(required=True),
        resolver=resolve_single,
        description=f"Retrieve a single {model.__name__} by ID",
    )


def generate_list_query(
    self, model: Type[models.Model], manager_name: str = "objects"
) -> graphene.List:
    """Generate a list query with filtering, ordering, and pagination."""

    # Setup
    model_type = self.type_generator.generate_object_type(model)
    graphql_meta = get_model_graphql_meta(model)
    ordering_config = getattr(graphql_meta, "ordering_config", None) or _default_ordering_config()

    # Generate filters (before resolver to be in closure scope)
    filter_class = self.filter_generator.generate_filter_set(model)
    nested_where_input = None
    nested_filter_applicator = None

    try:
        nested_generator = _get_nested_filter_generator(self.schema_name)
        nested_where_input = nested_generator.generate_where_input(model)
        nested_filter_applicator = _get_nested_filter_applicator(self.schema_name)
    except Exception as e:
        logger.warning(f"Could not generate nested filter for {model.__name__}: {e}")

    # Build resolver
    @optimize_query()
    def resolver(root: Any, info: graphene.ResolveInfo, **kwargs) -> List[models.Model]:
        # Permission checks
        self._enforce_model_permission(info, model, "list", graphql_meta)
        graphql_meta.ensure_operation_access("list", info=info)

        # Get base queryset
        manager = getattr(model, manager_name)
        queryset = manager.all()
        queryset = self._apply_tenant_scope(queryset, info, model, operation="list")
        queryset = self.optimizer.optimize_queryset(queryset, info, model)

        # Apply filters via pipeline
        context = QueryContext(
            model=model,
            queryset=queryset,
            info=info,
            kwargs=kwargs,
            graphql_meta=graphql_meta,
            filter_applicator=nested_filter_applicator,
            filter_class=filter_class,
            ordering_config=ordering_config,
            settings=self.settings,
        )

        pipeline = QueryFilterPipeline(context)
        queryset = pipeline.apply_all()

        # Apply ordering
        ordering_helper = QueryOrderingHelper(self, model, ordering_config, self.settings)
        queryset, items, has_prop_ordering = ordering_helper.apply(
            queryset,
            kwargs.get("order_by"),
            kwargs.get("distinct_on"),
        )

        # Apply pagination
        if self.settings.enable_pagination:
            offset = kwargs.get("offset") or 0
            limit = kwargs.get("limit") or self.settings.default_page_size

            if items is not None:
                items = items[offset:offset + limit]
            else:
                queryset = queryset[offset:offset + limit]
                items = list(queryset)
        elif items is None:
            items = list(queryset)

        return self._apply_field_masks(items, info, model)

    # Build arguments
    arguments = build_query_arguments(
        settings=self.settings,
        ordering_config=ordering_config,
        nested_where_input=nested_where_input,
        filter_class=filter_class,
        include_pagination=self.settings.enable_pagination,
        use_page_based=False,
    )

    return graphene.List(
        model_type,
        args=arguments,
        resolver=resolver,
        description=f"Retrieve a list of {model.__name__.lower()} instances",
    )


def _default_ordering_config():
    """Create default ordering config."""
    return type("OrderingConfig", (), {"allowed": [], "default": []})()
```

---

## 3. Performance Optimizations

### 3.1 Singleton Pattern for Filter Generators

**File:** `rail_django/generators/filter_inputs.py`

```python
# Add registry for filter applicators
_filter_applicator_registry: Dict[str, "NestedFilterApplicator"] = {}
_filter_generator_registry: Dict[str, "NestedFilterInputGenerator"] = {}


def get_nested_filter_applicator(schema_name: str = "default") -> "NestedFilterApplicator":
    """Get or create a filter applicator for the schema."""
    if schema_name not in _filter_applicator_registry:
        _filter_applicator_registry[schema_name] = NestedFilterApplicator(schema_name)
    return _filter_applicator_registry[schema_name]


def get_nested_filter_generator(schema_name: str = "default") -> "NestedFilterInputGenerator":
    """Get or create a filter generator for the schema."""
    if schema_name not in _filter_generator_registry:
        _filter_generator_registry[schema_name] = NestedFilterInputGenerator(schema_name=schema_name)
    return _filter_generator_registry[schema_name]


def clear_filter_caches(schema_name: Optional[str] = None) -> None:
    """
    Clear filter caches. Call on schema reload or in tests.

    Args:
        schema_name: Specific schema to clear, or None for all
    """
    if schema_name:
        _filter_applicator_registry.pop(schema_name, None)
        _filter_generator_registry.pop(schema_name, None)
        # Also clear the class-level cache
        prefix = f"{schema_name}_"
        keys_to_remove = [k for k in NestedFilterInputGenerator._filter_input_cache if k.startswith(prefix)]
        for key in keys_to_remove:
            del NestedFilterInputGenerator._filter_input_cache[key]
    else:
        _filter_applicator_registry.clear()
        _filter_generator_registry.clear()
        NestedFilterInputGenerator._filter_input_cache.clear()
```

Update lazy imports in query files:
```python
# BEFORE:
def _get_nested_filter_applicator(schema_name: str):
    from .filter_inputs import NestedFilterApplicator
    return NestedFilterApplicator(schema_name=schema_name)  # New instance every time

# AFTER:
def _get_nested_filter_applicator(schema_name: str):
    from .filter_inputs import get_nested_filter_applicator
    return get_nested_filter_applicator(schema_name)  # Singleton
```

---

### 3.2 Instance-Level Cache for Filter Generator

Move cache from class-level to instance-level with bounded size:

```python
from functools import lru_cache

class NestedFilterInputGenerator:
    def __init__(self, ...):
        # Instance-level cache with bounded size
        self._filter_input_cache: Dict[str, Type[graphene.InputObjectType]] = {}
        self._cache_max_size = 100
        self._generation_stack: Set[str] = set()

    def generate_where_input(self, model, depth=0):
        cache_key = f"{model.__name__}_where_{depth}"

        if cache_key in self._filter_input_cache:
            return self._filter_input_cache[cache_key]

        # Evict oldest entries if cache is full
        if len(self._filter_input_cache) >= self._cache_max_size:
            # Remove first 10% of entries
            keys_to_remove = list(self._filter_input_cache.keys())[:self._cache_max_size // 10]
            for key in keys_to_remove:
                del self._filter_input_cache[key]

        # ... rest of generation logic
```

---

### 3.3 Avoid Double Count Query

When `distinct_on` is used, cache the count or use subquery:

```python
# In queries_pagination.py
def resolver(...):
    # ... filtering and ordering ...

    # For distinct_on, we need to count the distinct result
    if distinct_on and items is None:
        # Use subquery to count distinct results efficiently
        from django.db.models import Subquery, OuterRef

        distinct_pks = queryset.values('pk')
        total_count = model.objects.filter(pk__in=Subquery(distinct_pks)).count()
    elif items is not None:
        total_count = len(items)  # Already materialized
    else:
        total_count = queryset.count()
```

---

## 4. Security Hardening

### 4.1 Limit Regex Complexity

**File:** `rail_django/generators/filter_inputs.py`

```python
import re

# Configuration
MAX_REGEX_LENGTH = 500
REGEX_TIMEOUT_SECONDS = 1.0  # For engines that support timeout


def validate_regex_pattern(pattern: str) -> str:
    """
    Validate regex pattern for safety.

    Raises:
        ValueError: If pattern is invalid or potentially dangerous
    """
    if not pattern:
        return pattern

    # Length limit
    if len(pattern) > MAX_REGEX_LENGTH:
        raise ValueError(f"Regex pattern too long (max {MAX_REGEX_LENGTH} chars)")

    # Try to compile to check validity
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    # Check for known ReDoS patterns
    redos_patterns = [
        r'\(\.\*\)\+',  # (.*)+
        r'\(\.\+\)\+',  # (.+)+
        r'\([^)]*\|[^)]*\)\+',  # (a|b)+ patterns
        r'\(\[.*\]\+\)\+',  # ([abc]+)+
    ]

    for dangerous in redos_patterns:
        if re.search(dangerous, pattern):
            raise ValueError("Regex pattern contains potentially dangerous constructs")

    return pattern


# Update _build_field_q to validate regex:
def _build_field_q(self, field_name, filter_value, model, prefix=""):
    # ...
    for op, op_value in filter_value.items():
        if op in ("regex", "iregex"):
            try:
                op_value = validate_regex_pattern(op_value)
            except ValueError as e:
                logger.warning(f"Invalid regex filter: {e}")
                continue  # Skip this filter
        # ... rest of logic
```

---

### 4.2 Limit Filter Nesting Depth

```python
class NestedFilterApplicator:
    MAX_FILTER_DEPTH = 10

    def _build_q_from_where(self, where_input, model, prefix="", depth=0):
        """Build Q object with depth limiting."""
        if depth > self.MAX_FILTER_DEPTH:
            logger.warning(f"Filter depth limit ({self.MAX_FILTER_DEPTH}) exceeded")
            return Q()

        q = Q()

        for key, value in where_input.items():
            if value is None:
                continue

            if key == "AND" and isinstance(value, list):
                for item in value:
                    q &= self._build_q_from_where(item, model, prefix, depth + 1)

            elif key == "OR" and isinstance(value, list):
                or_q = Q()
                for item in value:
                    or_q |= self._build_q_from_where(item, model, prefix, depth + 1)
                q &= or_q

            elif key == "NOT" and isinstance(value, dict):
                q &= ~self._build_q_from_where(value, model, prefix, depth + 1)

            # ... rest of logic
```

---

### 4.3 Limit Total Filter Complexity

```python
class NestedFilterApplicator:
    MAX_FILTER_CLAUSES = 50

    def apply_where_filter(self, queryset, where_input, model=None, ...):
        # Count total clauses
        clause_count = self._count_filter_clauses(where_input)
        if clause_count > self.MAX_FILTER_CLAUSES:
            raise ValueError(
                f"Filter too complex: {clause_count} clauses (max {self.MAX_FILTER_CLAUSES})"
            )

        # ... rest of logic

    def _count_filter_clauses(self, where_input: Dict, count: int = 0) -> int:
        """Recursively count filter clauses."""
        for key, value in where_input.items():
            if value is None:
                continue

            count += 1

            if key in ("AND", "OR") and isinstance(value, list):
                for item in value:
                    count = self._count_filter_clauses(item, count)
            elif key == "NOT" and isinstance(value, dict):
                count = self._count_filter_clauses(value, count)
            elif isinstance(value, dict):
                count = self._count_filter_clauses(value, count)

        return count
```

---

## 5. Code Quality Improvements

### 5.1 Fix Encoding Issue

**File:** `rail_django/generators/queries_grouping.py`

```python
# BEFORE:
label_value = "Non renseignǸ"  # Corrupted encoding

# AFTER:
from django.utils.translation import gettext_lazy as _

# Define as translatable constant
EMPTY_GROUP_LABEL = _("Not specified")

# In the resolver:
if raw_value is None:
    label_value = str(EMPTY_GROUP_LABEL)
```

---

### 5.2 Use Constants for Magic Strings

**New File:** `rail_django/generators/constants.py`

```python
"""
Constants used across query generators.
"""

# Reserved argument names that should not be passed to FilterSet
RESERVED_QUERY_ARGS = frozenset([
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

# Default ordering when none specified
DEFAULT_ORDERING_FALLBACK = ["-id"]

# Maximum nesting depths
DEFAULT_MAX_NESTED_DEPTH = 3
MAX_ALLOWED_NESTED_DEPTH = 5
MAX_FILTER_DEPTH = 10
MAX_FILTER_CLAUSES = 50

# Pagination defaults (should match settings)
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# Property ordering limits
DEFAULT_MAX_PROPERTY_ORDERING_RESULTS = 1000

# Grouping limits
DEFAULT_MAX_GROUPING_BUCKETS = 200

# Security limits
MAX_REGEX_LENGTH = 500
```

---

### 5.3 Specific Exception Handling

```python
# BEFORE:
try:
    nested_generator = _get_nested_filter_generator(self.schema_name)
    nested_where_input = nested_generator.generate_where_input(model)
except Exception as e:  # Too broad
    logger.warning(f"Could not generate nested filter: {e}")

# AFTER:
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured

try:
    nested_generator = _get_nested_filter_generator(self.schema_name)
    nested_where_input = nested_generator.generate_where_input(model)
except (FieldDoesNotExist, ImproperlyConfigured, AttributeError) as e:
    logger.warning(f"Could not generate nested filter for {model.__name__}: {e}")
except Exception:
    logger.exception(f"Unexpected error generating nested filter for {model.__name__}")
```

---

### 5.4 Historical Model Detection Improvement

**File:** `rail_django/generators/queries.py`

```python
# BEFORE (fragile name-based detection):
def _is_historical_model(self, model):
    name = getattr(model, "__name__", "")
    if name.startswith("Historical"):
        return True
    if "simple_history" in getattr(model, "__module__", ""):
        return True
    return False

# AFTER (attribute-based detection):
def _is_historical_model(self, model: Type[models.Model]) -> bool:
    """
    Check if model is a django-simple-history historical model.

    Detection based on actual model attributes rather than naming conventions.
    """
    # Check for simple_history specific fields
    required_fields = ("history_id", "history_date", "history_type", "history_user")

    try:
        model_fields = {f.name for f in model._meta.get_fields()}
        if all(f in model_fields for f in required_fields):
            return True
    except Exception:
        pass

    # Fallback: check for HistoricalRecords manager
    try:
        if hasattr(model, "history") and hasattr(model.history, "model"):
            return True
    except Exception:
        pass

    # Final fallback: naming convention
    name = getattr(model, "__name__", "")
    module = getattr(model, "__module__", "")

    return name.startswith("Historical") or "simple_history" in module
```

---

## 6. Implementation Order

### Phase 1: Critical Bug Fixes (Immediate)

1. ✅ Fix unbound `nested_filter_applicator` variable in `queries_pagination.py`
2. ✅ Fix input dictionary mutation in `filter_inputs.py`
3. ✅ Fix dead code / impossible conditions
4. ✅ Fix property ordering total count bug

**Estimated Impact:** Prevents runtime errors, data corruption

### Phase 2: Correctness Fixes (High Priority)

5. Fix `_every` filter implementation
6. Fix empty page edge case in pagination
7. Fix encoding issue in grouping query

**Estimated Impact:** Correct query semantics

### Phase 3: Code Quality (Medium Priority)

8. Create `queries_base.py` with shared code
9. Refactor `queries_list.py` to use shared code
10. Refactor `queries_pagination.py` to use shared code
11. Add constants file
12. Improve exception handling

**Estimated Impact:** Maintainability, reduced code duplication

### Phase 4: Performance (Medium Priority)

13. Implement singleton pattern for filter generators
14. Add bounded cache for filter inputs
15. Optimize distinct count query

**Estimated Impact:** Reduced memory, faster queries

### Phase 5: Security Hardening (Lower Priority)

16. Add regex validation
17. Add filter depth limiting
18. Add filter complexity limiting

**Estimated Impact:** Protection against DoS attacks

---

## Testing Checklist

After implementing fixes, verify:

- [ ] `savedFilter` argument works in paginated queries
- [ ] `presets` argument works in paginated queries
- [ ] Input dictionaries are not mutated after filtering
- [ ] `_every` filter correctly excludes non-matching records
- [ ] Pagination shows correct total_count with property ordering
- [ ] Empty results show page=1, page_count=0 consistently
- [ ] Grouping query shows "Not specified" for null values
- [ ] Regex filters reject dangerous patterns
- [ ] Deeply nested filters are rejected
- [ ] Filter generators are reused across requests
- [ ] Filter caches don't grow unbounded

---

## Migration Notes

### Breaking Changes

None expected. All fixes maintain backward compatibility.

### Deprecations

- Direct instantiation of `NestedFilterApplicator` - use `get_nested_filter_applicator()` instead
- Direct instantiation of `NestedFilterInputGenerator` - use `get_nested_filter_generator()` instead

### New Dependencies

None required.

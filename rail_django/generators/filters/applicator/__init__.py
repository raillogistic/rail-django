"""
Nested filter applicator package.

This package provides the NestedFilterApplicator class for applying nested
filter inputs to Django querysets. The implementation is split across multiple
modules for maintainability:

- base.py: Core applicator logic and main entry point
- field_applicator.py: Field-level filter application methods
- relation_applicator.py: Relation filter application methods
- aggregation_applicator.py: Aggregation filter application methods

Usage:
    from rail_django.generators.filters.applicator import NestedFilterApplicator

    applicator = NestedFilterApplicator(schema_name="default")
    queryset = applicator.apply_where_filter(queryset, where_input, model)
"""

from typing import Any

from .aggregation_applicator import AggregationFilterApplicatorMixin
from .base import BaseFilterApplicatorMixin
from .field_applicator import FieldFilterApplicatorMixin
from .relation_applicator import RelationFilterApplicatorMixin


class NestedFilterApplicator(
    FieldFilterApplicatorMixin,
    RelationFilterApplicatorMixin,
    AggregationFilterApplicatorMixin,
    BaseFilterApplicatorMixin,
):
    """
    Applies nested filter inputs to Django querysets.

    Converts the nested filter input structure into Django Q objects
    for queryset filtering. Includes support for:

    - Basic field filters (eq, gt, contains, etc.)
    - Relation filters (_rel, _some, _every, _none)
    - Aggregation filters (_agg, _cond_agg)
    - Count filters (_count)
    - Quick filter (multi-field search)
    - Include filter (ID union)
    - Historical model filters
    - Full-text search
    - Window function filters
    - Subquery and exists filters
    - Date truncation and extraction filters
    - Field comparison filters

    The class inherits from multiple mixins to organize the functionality:

    - BaseFilterApplicatorMixin: Core logic, initialization, Q construction
    - FieldFilterApplicatorMixin: Field-level filter methods
    - RelationFilterApplicatorMixin: Relation and advanced filter methods
    - AggregationFilterApplicatorMixin: Aggregation filter methods

    Example:
        applicator = NestedFilterApplicator(schema_name="default")

        # Apply a where filter
        filtered_qs = applicator.apply_where_filter(
            queryset=Product.objects.all(),
            where_input={
                "name": {"icontains": "widget"},
                "price": {"gte": 10, "lte": 100},
                "category": {
                    "name": {"eq": "Electronics"}
                }
            },
            model=Product
        )

        # Apply with presets
        where_with_presets = applicator.apply_presets(
            where_input=user_filters,
            presets=["active", "in_stock"],
            model=Product
        )
    """

    def __init__(self, schema_name: str = "default"):
        """
        Initialize the NestedFilterApplicator.

        Args:
            schema_name: Name of the schema for loading filter settings.
                        Defaults to "default".
        """
        # Initialize the base mixin which sets up all shared state
        BaseFilterApplicatorMixin.__init__(self, schema_name)


def apply_where_filter(
    queryset: Any,
    where_input: Any,
    model: Any = None,
    schema_name: str = "default",
) -> Any:
    """
    Helper function to apply a where filter using default settings.
    
    Args:
        queryset: Django QuerySet
        where_input: Where filter input
        model: Django model class (optional, derived from queryset if None)
        schema_name: Schema name for multi-schema support
        
    Returns:
        Filtered QuerySet
    """
    from ..security import get_nested_filter_applicator
    applicator = get_nested_filter_applicator(schema_name=schema_name)
    return applicator.apply_where_filter(queryset, where_input, model)


__all__ = [
    "NestedFilterApplicator",
    "BaseFilterApplicatorMixin",
    "FieldFilterApplicatorMixin",
    "RelationFilterApplicatorMixin",
    "AggregationFilterApplicatorMixin",
    "apply_where_filter",
]

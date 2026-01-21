"""
Aggregation filter applicator methods.

This module provides aggregation-level filter application functionality including:
- Basic aggregation filters (sum, avg, min, max, count)
- Conditional aggregation filters
- Aggregation annotation collection and construction
"""

import logging
from typing import Any, Dict, Optional, Type

from django.db import models
from django.db.models import Avg, Count, Max, Min, Q, Sum

logger = logging.getLogger(__name__)


class AggregationFilterApplicatorMixin:
    """
    Mixin for aggregation-level filter application.

    Provides methods for building Q objects and annotations for aggregation
    filters, including both simple aggregations (sum, avg, min, max, count)
    and conditional aggregations.
    """

    def _aggregation_annotation_name(
        self,
        relation_path: str,
        target_field: str,
        agg_type: str,
    ) -> str:
        """
        Build a stable annotation name for aggregation filters.

        Creates a consistent naming pattern for aggregation annotations
        to ensure they can be referenced correctly in Q objects.

        Args:
            relation_path: Path to the relation being aggregated
            target_field: Field being aggregated
            agg_type: Type of aggregation (sum, avg, etc.)

        Returns:
            Annotation name string
        """
        safe_relation = relation_path.replace("__", "_")
        safe_target = (target_field or "id").replace("__", "_")
        return f"{safe_relation}_agg_{safe_target}_{agg_type}"

    def _build_aggregation_q(
        self,
        field_path: str,
        agg_filter: Dict[str, Any],
    ) -> Q:
        """
        Build Q object for aggregation filters.

        Constructs Q objects that filter on pre-computed aggregation
        annotations.

        Args:
            field_path: Relation path for the aggregation
            agg_filter: Aggregation filter configuration

        Returns:
            Django Q object
        """
        q = Q()
        target_field = agg_filter.get("field") or "id"

        for agg_type in ("sum", "avg", "min", "max", "count", "count_distinct"):
            agg_value = agg_filter.get(agg_type)
            if not isinstance(agg_value, dict):
                continue
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, agg_type
            )
            q &= self._build_numeric_q(annotation_name, agg_value)

        return q

    def prepare_queryset_for_aggregation_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
    ) -> models.QuerySet:
        """
        Prepare queryset with annotations for aggregation filters.

        Traverses the where input to find all aggregation filters and
        adds the necessary annotations to the queryset.

        Args:
            queryset: Django queryset
            where_input: Where input dictionary

        Returns:
            Queryset with necessary aggregation annotations
        """
        annotations = self._collect_aggregation_annotations(where_input)

        if annotations:
            queryset = queryset.annotate(**annotations)

        return queryset

    def _collect_aggregation_annotations(
        self,
        where_input: Dict[str, Any],
        annotations: Optional[Dict[str, Any]] = None,
        prefix: str = "",
    ) -> Dict[str, Any]:
        """
        Collect all aggregation annotations needed.

        Recursively traverses the where input to find all _agg filters
        and builds the corresponding annotation dictionary.

        Args:
            where_input: Where input dictionary
            annotations: Accumulated annotations dictionary
            prefix: Current field path prefix

        Returns:
            Dictionary of annotation names to aggregation expressions
        """
        if annotations is None:
            annotations = {}

        for key, value in where_input.items():
            if value is None:
                continue

            if key in ("AND", "OR") and isinstance(value, list):
                for item in value:
                    self._collect_aggregation_annotations(item, annotations, prefix)
                continue

            if key == "NOT" and isinstance(value, dict):
                self._collect_aggregation_annotations(value, annotations, prefix)
                continue

            if not isinstance(value, dict):
                continue

            if key.endswith("_rel"):
                base_field = key[:-4]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            if key.endswith("_some"):
                base_field = key[:-5]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            if key.endswith("_every"):
                base_field = key[:-6]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            if key.endswith("_none"):
                base_field = key[:-5]
                self._collect_aggregation_annotations(
                    value, annotations, f"{prefix}{base_field}__"
                )
                continue

            # Skip conditional aggregation filters - they're handled separately
            if key.endswith("_cond_agg"):
                continue

            if key.endswith("_agg"):
                base_field = key[:-4]
                full_field_path = f"{prefix}{base_field}" if prefix else base_field
                annotations.update(
                    self._build_aggregation_annotations(full_field_path, value)
                )

        return annotations

    def _build_aggregation_annotations(
        self,
        field_path: str,
        agg_filter: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build annotations for aggregation filters.

        Creates Django aggregation expressions (Sum, Avg, Min, Max, Count)
        for each aggregation type specified in the filter.

        Args:
            field_path: Relation path for the aggregation
            agg_filter: Aggregation filter configuration

        Returns:
            Dictionary of annotation names to aggregation expressions
        """
        annotations: Dict[str, Any] = {}
        target_field = agg_filter.get("field") or "id"

        if target_field:
            lookup_path = f"{field_path}__{target_field}"
        else:
            lookup_path = field_path

        if agg_filter.get("sum") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "sum"
            )
            annotations[annotation_name] = Sum(lookup_path)

        if agg_filter.get("avg") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "avg"
            )
            annotations[annotation_name] = Avg(lookup_path)

        if agg_filter.get("min") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "min"
            )
            annotations[annotation_name] = Min(lookup_path)

        if agg_filter.get("max") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "max"
            )
            annotations[annotation_name] = Max(lookup_path)

        if agg_filter.get("count") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "count"
            )
            annotations[annotation_name] = Count(lookup_path)

        if agg_filter.get("count_distinct") is not None:
            annotation_name = self._aggregation_annotation_name(
                field_path, target_field, "count_distinct"
            )
            annotations[annotation_name] = Count(lookup_path, distinct=True)

        return annotations

    # =========================================================================
    # Conditional Aggregation Filter Methods
    # =========================================================================

    def prepare_queryset_for_conditional_aggregation_filters(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
    ) -> models.QuerySet:
        """
        Prepare queryset with conditional aggregation annotations.

        Conditional aggregations allow filtering the rows included in
        the aggregation calculation.

        Args:
            queryset: Django queryset
            where_input: Where input dictionary

        Returns:
            Queryset with conditional aggregation annotations
        """
        annotations = self._collect_conditional_aggregation_annotations(where_input)
        if annotations:
            queryset = queryset.annotate(**annotations)
        return queryset

    def _collect_conditional_aggregation_annotations(
        self,
        where_input: Dict[str, Any],
        annotations: Optional[Dict[str, Any]] = None,
        prefix: str = "",
    ) -> Dict[str, Any]:
        """
        Collect all conditional aggregation annotations needed.

        Recursively traverses the where input to find all _cond_agg filters
        and builds the corresponding annotation dictionary.

        Args:
            where_input: Where input dictionary
            annotations: Accumulated annotations dictionary
            prefix: Current field path prefix

        Returns:
            Dictionary of annotation names to conditional aggregation expressions
        """
        if annotations is None:
            annotations = {}

        for key, value in where_input.items():
            if value is None:
                continue

            if key in ("AND", "OR") and isinstance(value, list):
                for item in value:
                    self._collect_conditional_aggregation_annotations(
                        item, annotations, prefix
                    )
                continue

            if key == "NOT" and isinstance(value, dict):
                self._collect_conditional_aggregation_annotations(
                    value, annotations, prefix
                )
                continue

            if not isinstance(value, dict):
                continue

            if key.endswith("_cond_agg"):
                base_field = key[:-9]
                full_field_path = f"{prefix}{base_field}" if prefix else base_field
                annotations.update(
                    self._build_conditional_aggregation_annotations(
                        full_field_path, value
                    )
                )

        return annotations

    def _build_conditional_aggregation_annotations(
        self,
        field_path: str,
        cond_agg_filter: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build annotations for conditional aggregation filters.

        Creates Django aggregation expressions with filter conditions,
        allowing aggregation over a subset of related records.

        Args:
            field_path: Relation path for the aggregation
            cond_agg_filter: Conditional aggregation filter configuration

        Returns:
            Dictionary of annotation names to conditional aggregation expressions
        """
        import json

        annotations: Dict[str, Any] = {}
        target_field = cond_agg_filter.get("field") or "id"
        condition_json = cond_agg_filter.get("filter")

        # Parse the filter condition JSON
        condition_q = Q()
        if condition_json:
            try:
                if isinstance(condition_json, str):
                    condition_dict = json.loads(condition_json)
                else:
                    condition_dict = condition_json
                # Build Q object from the condition (simple key-value for now)
                for k, v in condition_dict.items():
                    if isinstance(v, dict):
                        for op, op_val in v.items():
                            lookup = self._get_lookup_for_operator(op)
                            if lookup:
                                condition_q &= Q(
                                    **{f"{field_path}__{k}__{lookup}": op_val}
                                )
                    else:
                        condition_q &= Q(**{f"{field_path}__{k}": v})
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.debug(f"Failed to parse conditional filter: {e}")

        lookup_path = f"{field_path}__{target_field}"

        if cond_agg_filter.get("sum") is not None:
            annotation_name = f"{field_path.replace('__', '_')}_cond_sum"
            annotations[annotation_name] = Sum(lookup_path, filter=condition_q)

        if cond_agg_filter.get("avg") is not None:
            annotation_name = f"{field_path.replace('__', '_')}_cond_avg"
            annotations[annotation_name] = Avg(lookup_path, filter=condition_q)

        if cond_agg_filter.get("count") is not None:
            annotation_name = f"{field_path.replace('__', '_')}_cond_count"
            annotations[annotation_name] = Count(lookup_path, filter=condition_q)

        return annotations

    def _build_conditional_aggregation_q(
        self,
        field_path: str,
        cond_agg_filter: Dict[str, Any],
    ) -> Q:
        """
        Build Q object for conditional aggregation filters.

        Constructs Q objects that filter on pre-computed conditional
        aggregation annotations.

        Args:
            field_path: Relation path for the aggregation
            cond_agg_filter: Conditional aggregation filter configuration

        Returns:
            Django Q object
        """
        q = Q()

        for agg_type in ("sum", "avg", "count"):
            agg_value = cond_agg_filter.get(agg_type)
            if not isinstance(agg_value, dict):
                continue
            annotation_name = f"{field_path.replace('__', '_')}_cond_{agg_type}"
            q &= self._build_numeric_q(annotation_name, agg_value)

        return q

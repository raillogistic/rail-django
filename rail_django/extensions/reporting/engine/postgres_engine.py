"""
PostgreSQL-specific reporting extensions.
"""
from typing import Any, Dict, List, Optional, Tuple, Set

from django.contrib.postgres.aggregates import ArrayAgg, StringAgg, JSONBAgg
from django.contrib.postgres.search import SearchVector, SearchQuery
from django.db.models import StdDev, Variance, Count
from django.db import models

from ..types import (
    MetricSpec,
    ReportingError,
    FilterSpec,
    AGGREGATION_MAP as BASE_AGGREGATION_MAP
)

from .core import DatasetExecutionEngine

# Extended aggregation map for Postgres
PSQL_AGGREGATION_MAP = BASE_AGGREGATION_MAP.copy()
PSQL_AGGREGATION_MAP.update({
    "stddev": lambda expr, *, filter_q=None: StdDev(expr, filter=filter_q),
    "variance": lambda expr, *, filter_q=None: Variance(expr, filter=filter_q),
    "list": lambda expr, *, filter_q=None: ArrayAgg(expr, filter=filter_q, distinct=True),
    "concat": lambda expr, *, filter_q=None: StringAgg(expr, delimiter=", ", filter=filter_q, distinct=True),
})

class PostgresDatasetExecutionEngine(DatasetExecutionEngine):
    """
    Enhanced execution engine that leverages PostgreSQL features.
    """

    def _build_annotations(
        self,
        metrics: list[MetricSpec],
        *,
        allowed_where_fields: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        annotations: dict[str, Any] = {}
        for metric in metrics:
            agg_name = (metric.aggregation or "sum").lower()
            
            # Special handling for parameterized aggregates (e.g. percentile:0.95)
            agg_params = {}
            if ":" in agg_name:
                parts = agg_name.split(":", 1)
                agg_name = parts[0]
                try:
                    agg_params["param"] = float(parts[1]) 
                except ValueError:
                    agg_params["param"] = parts[1]

            expr_field = metric.field
            if agg_name in {"count", "distinct_count"} and (
                not expr_field or expr_field == "*"
            ):
                expr_field = "pk"

            filter_q = None
            if metric.filter:
                filter_q, _, _ = self._compile_filter_tree(
                    metric.filter,
                    quick_search="",
                    allowed_fields=allowed_where_fields,
                )

            if agg_name == "count":
                annotations[metric.name] = Count(expr_field, filter=filter_q)
                continue
            
            if agg_name == "percentile":
                from django.contrib.postgres.aggregates import PercentileCont
                p = agg_params.get("param", 0.5)
                # PercentileCont requires an ordering argument in Django
                annotations[metric.name] = PercentileCont(p, ordering=expr_field, filter=filter_q) 
                continue

            agg_factory = PSQL_AGGREGATION_MAP.get(agg_name)
            if not agg_factory:
                # Fallback to parent map/error logic handled by parent if we called super(),
                # but we are reimplementing the loop to intercept names.
                raise ReportingError(f"Agregation non supportee (Postgres): {agg_name}")
            
            annotations[metric.name] = agg_factory(expr_field, filter_q=filter_q)
        return annotations

    def _apply_where(
        self,
        queryset: models.QuerySet,
        *,
        where: Any,
        quick_search: str,
        allowed_fields: Optional[set[str]] = None,
    ) -> tuple[models.QuerySet, list[FilterSpec], list[str]]:
        """
        Override to use SearchVector for quick_search.
        """
        # Call parent with empty quick_search to skip the slow OR loop
        q, flat, warnings = self._compile_filter_tree(
            where,
            quick_search="", 
            allowed_fields=allowed_fields,
        )
        
        if q is not None:
            queryset = queryset.filter(q)

        # Apply optimized quick search if present
        if quick_search:
            quick_fields = self._get_quick_fields()
            if quick_fields:
                # We rely on Django to handle the join for related fields in SearchVector
                vector = SearchVector(*quick_fields)
                query = SearchQuery(quick_search)
                queryset = queryset.annotate(search=vector).filter(search=query)

        return queryset, flat, warnings

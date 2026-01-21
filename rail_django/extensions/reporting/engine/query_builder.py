"""
Query building mixin for DatasetExecutionEngine.

This module contains methods for building Django ORM queries including
dimension expressions, filter compilation, and queryset manipulation.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from django.db import connection, models
from django.db.models import Count, F, Q
from django.db.models.functions import (
    ExtractDay,
    ExtractMonth,
    ExtractQuarter,
    ExtractWeek,
    ExtractWeekDay,
    ExtractYear,
    Lower,
    TruncDate,
    TruncDay,
    TruncHour,
    TruncMonth,
    TruncQuarter,
    TruncWeek,
    TruncYear,
    Upper,
)
from django.contrib.postgres.aggregates import (
    ArrayAgg,
    BitAnd,
    BitOr,
    BitXor,
    BoolAnd,
    BoolOr,
    JSONBAgg,
    StringAgg,
)

from ..types import (
    ComputedFieldSpec,
    DimensionSpec,
    FilterSpec,
    MetricSpec,
    ReportingError,
    AGGREGATION_MAP,
    POSTGRES_AGGREGATIONS,
)
from ..utils import _combine_q, _to_filter_list, _to_ordering


class QueryBuilderMixin:
    """
    Mixin providing query building methods for the execution engine.

    These methods handle dimension expressions, filter compilation,
    annotation building, and queryset manipulation.
    """

    def _build_dimension_values(
        self, dimensions: list[DimensionSpec]
    ) -> tuple[dict, list[str]]:
        """
        Build `values()` kwargs for dimensions.

        Returns (values_kwargs, ordering_aliases), where ordering aliases maps
        original field paths to their dimension names when required.
        """

        values_kwargs: dict = {}
        ordering_aliases: list[str] = []
        for dim in dimensions:
            if not dim.field:
                continue
            expr = self._dimension_expression(dim)
            if dim.transform or dim.name != dim.field:
                values_kwargs[dim.name] = expr
                ordering_aliases.append(dim.field)
            else:
                values_kwargs[dim.field] = expr
        return values_kwargs, ordering_aliases

    def _dimension_expression(self, dim: DimensionSpec) -> Any:
        base = F(dim.field)
        transform = (dim.transform or "").strip().lower()
        if not transform:
            return base

        if transform == "lower":
            return Lower(base)
        if transform == "upper":
            return Upper(base)
        if transform == "date":
            return TruncDate(base)

        if transform.startswith("trunc:"):
            grain = transform.split(":", 1)[1].strip()
            trunc_map = {
                "hour": TruncHour,
                "day": TruncDay,
                "week": TruncWeek,
                "month": TruncMonth,
                "quarter": TruncQuarter,
                "year": TruncYear,
            }
            trunc = trunc_map.get(grain)
            if not trunc:
                raise ReportingError(f"Grain temporel non supporte: {grain}")
            return trunc(base)

        extract_map = {
            "year": ExtractYear,
            "quarter": ExtractQuarter,
            "month": ExtractMonth,
            "day": ExtractDay,
            "week": ExtractWeek,
            "weekday": ExtractWeekDay,
        }
        extractor = extract_map.get(transform)
        if extractor:
            return extractor(base)

        raise ReportingError(f"Transformation non supportee: {transform}")

    def _build_postgres_aggregation(
        self,
        agg_name: str,
        expr_field: str,
        *,
        filter_q: Optional[Q],
        options: Optional[dict],
    ) -> Any:
        if connection.vendor != "postgresql":
            raise ReportingError(
                f"Agregation '{agg_name}' requiert PostgreSQL."
            )

        options = options or {}
        ordering = _to_ordering(
            options.get("ordering") or options.get("order_by") or options.get("order")
        )
        extra: dict[str, Any] = {}
        if filter_q is not None:
            extra["filter"] = filter_q
        if options.get("distinct"):
            extra["distinct"] = True
        if ordering:
            extra["ordering"] = ordering
        if "default" in options:
            extra["default"] = options.get("default")

        if agg_name == "string_agg":
            delimiter = options.get("delimiter", ", ")
            return StringAgg(expr_field, delimiter, **extra)
        if agg_name == "array_agg":
            return ArrayAgg(expr_field, **extra)
        if agg_name == "jsonb_agg":
            return JSONBAgg(expr_field, **extra)
        if agg_name == "bool_and":
            return BoolAnd(expr_field, **extra)
        if agg_name == "bool_or":
            return BoolOr(expr_field, **extra)
        if agg_name == "bit_and":
            return BitAnd(expr_field, **extra)
        if agg_name == "bit_or":
            return BitOr(expr_field, **extra)
        if agg_name == "bit_xor":
            return BitXor(expr_field, **extra)

        raise ReportingError(f"Agregation non supportee: {agg_name}")

    def _build_annotations(
        self,
        metrics: list[MetricSpec],
        *,
        allowed_where_fields: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        annotations: dict[str, Any] = {}
        for metric in metrics:
            agg_name = (metric.aggregation or "sum").lower()
            expr_field = metric.field
            if agg_name in {"count", "distinct_count"} and (
                not expr_field or expr_field == "*"
            ):
                expr_field = "pk"

            options = metric.options or {}
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

            if agg_name in POSTGRES_AGGREGATIONS:
                if not expr_field:
                    raise ReportingError(
                        f"Agregation '{agg_name}' requiert un champ."
                    )
                annotations[metric.name] = self._build_postgres_aggregation(
                    agg_name, expr_field, filter_q=filter_q, options=options
                )
                continue

            agg_factory = AGGREGATION_MAP.get(agg_name)
            if not agg_factory:
                raise ReportingError(f"Agregation non supportee: {agg_name}")
            annotations[metric.name] = agg_factory(expr_field, filter_q=filter_q)
        return annotations

    def _get_quick_fields(self) -> list[str]:
        meta_quick = (self.dataset.metadata or {}).get("quick_fields") or []
        if meta_quick:
            return [str(field) for field in meta_quick]
        if self.dimensions:
            return [dim.field for dim in self.dimensions[:3]]
        return []

    def _compile_filter_specs(
        self,
        specs: Sequence[FilterSpec],
        *,
        warnings: list[str],
        allowed_fields: set[str],
        allowed_lookups: set[str],
    ) -> Optional[Q]:
        combined: Optional[Q] = None
        for spec in specs:
            lookup = (spec.lookup or "exact").lower()
            if lookup not in allowed_lookups or "__" in lookup:
                warnings.append(f"Lookup non autorise: {lookup}")
                continue

            field_path = str(spec.field)
            if field_path not in allowed_fields and not self._is_allowed_where_field(
                field_path
            ):
                warnings.append(f"Champ non autorise: {field_path}")
                continue

            try:
                condition = Q(**{f"{field_path}__{lookup}": spec.value})
            except Exception as exc:
                warnings.append(f"Filtre ignore ({field_path}): {exc}")
                continue

            if spec.negate:
                condition = ~condition

            if combined is None:
                combined = condition
            else:
                combined = (
                    (combined | condition)
                    if spec.connector == "or"
                    else (combined & condition)
                )
        return combined

    def _flatten_filter_tree(self, raw: Any) -> list[FilterSpec]:
        if raw is None:
            return []
        if isinstance(raw, FilterSpec):
            return [raw]
        if isinstance(raw, list):
            flattened: list[FilterSpec] = []
            for item in raw:
                flattened.extend(self._flatten_filter_tree(item))
            return flattened
        if isinstance(raw, dict):
            if "items" in raw:
                return self._flatten_filter_tree(raw.get("items") or [])
            if "field" in raw:
                return _to_filter_list([raw])
        return []

    def _compile_filter_tree(
        self,
        raw_filters: Any,
        *,
        quick_search: str,
        allowed_fields: Optional[set[str]] = None,
        allowed_lookups: Optional[set[str]] = None,
    ) -> tuple[Optional[Q], list[FilterSpec], list[str]]:
        warnings: list[str] = []
        allowed_fields = allowed_fields or self._allowed_where_fields()
        allowed_lookups = allowed_lookups or self._allowed_lookups()

        compiled = self._compile_filter_node(
            raw_filters,
            warnings=warnings,
            allowed_fields=allowed_fields,
            allowed_lookups=allowed_lookups,
        )

        quick_fields = self._get_quick_fields()
        if quick_search and quick_fields:
            quick_q = Q()
            for field_name in quick_fields:
                quick_q |= Q(**{f"{field_name}__icontains": quick_search})
            compiled = quick_q if compiled is None else (compiled & quick_q)

        return compiled, self._flatten_filter_tree(raw_filters), warnings

    def _compile_filter_node(
        self,
        node: Any,
        *,
        warnings: list[str],
        allowed_fields: set[str],
        allowed_lookups: set[str],
    ) -> Optional[Q]:
        if node is None:
            return None
        if isinstance(node, FilterSpec):
            return self._compile_filter_specs(
                [node],
                warnings=warnings,
                allowed_fields=allowed_fields,
                allowed_lookups=allowed_lookups,
            )
        if isinstance(node, list):
            if all(isinstance(item, FilterSpec) for item in node):
                return self._compile_filter_specs(
                    node,
                    warnings=warnings,
                    allowed_fields=allowed_fields,
                    allowed_lookups=allowed_lookups,
                )
            if all(isinstance(item, dict) and "field" in item for item in node):
                return self._compile_filter_specs(
                    _to_filter_list(node),
                    warnings=warnings,
                    allowed_fields=allowed_fields,
                    allowed_lookups=allowed_lookups,
                )
            compiled_children = [
                child
                for child in (
                    self._compile_filter_node(
                        item,
                        warnings=warnings,
                        allowed_fields=allowed_fields,
                        allowed_lookups=allowed_lookups,
                    )
                    for item in node
                )
                if child is not None
            ]
            return _combine_q(compiled_children, op="and")
        if isinstance(node, dict):
            if "items" in node:
                op = str(node.get("op") or node.get("connector") or "and").lower()
                negate = bool(node.get("negate") or node.get("not"))
                compiled_children = [
                    child
                    for child in (
                        self._compile_filter_node(
                            item,
                            warnings=warnings,
                            allowed_fields=allowed_fields,
                            allowed_lookups=allowed_lookups,
                        )
                        for item in (node.get("items") or [])
                    )
                    if child is not None
                ]
                compiled = _combine_q(compiled_children, op=op)
                return (~compiled) if (negate and compiled is not None) else compiled
            if "field" in node:
                specs = _to_filter_list([node])
                return self._compile_filter_specs(
                    specs,
                    warnings=warnings,
                    allowed_fields=allowed_fields,
                    allowed_lookups=allowed_lookups,
                )
        return None

    def _apply_where(
        self,
        queryset: models.QuerySet,
        *,
        where: Any,
        quick_search: str,
        allowed_fields: Optional[set[str]] = None,
    ) -> tuple[models.QuerySet, list[FilterSpec], list[str]]:
        q, flat, warnings = self._compile_filter_tree(
            where,
            quick_search=quick_search,
            allowed_fields=allowed_fields,
        )
        if q is None:
            return queryset, flat, warnings
        return queryset.filter(q), flat, warnings

    def _apply_computed_fields(self, rows: list[dict[str, Any]]) -> None:
        from ..utils import _safe_formula_eval

        computed_post = [
            computed for computed in self.computed_fields if computed.stage != "query"
        ]
        if not computed_post:
            return

        for row in rows:
            context = {key: row.get(key, 0) for key in row.keys()}
            for computed in computed_post:
                try:
                    row[computed.name] = _safe_formula_eval(
                        computed.formula, dict(context)
                    )
                except ReportingError as exc:
                    row[computed.name] = None
                    row.setdefault("_warnings", []).append(str(exc))

    def describe_columns_for(
        self,
        dimensions: list[DimensionSpec],
        metrics: list[MetricSpec],
        computed_fields: list[ComputedFieldSpec],
    ) -> list[dict[str, Any]]:
        columns: list[dict[str, Any]] = []
        for dim in dimensions:
            columns.append(
                {
                    "name": dim.name,
                    "label": dim.label or dim.name,
                    "kind": "dimension",
                    "help_text": dim.help_text,
                    "field": dim.field,
                    "transform": dim.transform,
                }
            )
        for metric in metrics:
            columns.append(
                {
                    "name": metric.name,
                    "label": metric.label or metric.name,
                    "kind": "metric",
                    "help_text": metric.help_text,
                    "format": metric.format,
                    "field": metric.field,
                    "aggregation": metric.aggregation,
                    "options": metric.options,
                }
            )
        for computed in computed_fields:
            columns.append(
                {
                    "name": computed.name,
                    "label": computed.label or computed.name,
                    "kind": "computed",
                    "help_text": computed.help_text,
                    "stage": computed.stage,
                }
            )
        return columns

    def describe_columns(self) -> list[dict[str, Any]]:
        return self.describe_columns_for(
            self.dimensions, self.metrics, self.computed_fields
        )


__all__ = ["QueryBuilderMixin"]

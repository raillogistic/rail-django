"""
Aggregation resolution mixin for DatasetExecutionEngine.

This module contains resolution methods for dimensions, metrics, computed fields,
annotation filter compilation, and the basic run() method.
"""

from __future__ import annotations

from typing import Any, Optional

from django.db.models import Q

from ..types import (
    ComputedFieldSpec,
    DimensionSpec,
    FilterSpec,
    MetricSpec,
    ReportingError,
)
from ..utils import (
    _coerce_int,
    _combine_q,
    _json_sanitize,
    _safe_formula_eval,
    _safe_identifier,
    _safe_query_expression,
    _to_filter_list,
    _to_ordering,
)


class AggregationMixin:
    """
    Mixin providing aggregation resolution methods for the execution engine.

    These methods handle dimension/metric/computed field resolution,
    annotation filter compilation, and the basic run() operation.
    """

    def run(
        self,
        *,
        runtime_filters: Optional[Any] = None,
        limit: Optional[int] = None,
        ordering: Optional[list[str]] = None,
        quick_search: str = "",
    ) -> dict[str, Any]:
        queryset = self.model.objects.all()
        default_filters_raw: Any = self.dataset.default_filters or []
        runtime_filters_raw: Any = runtime_filters or []
        if isinstance(runtime_filters_raw, list) and all(
            isinstance(item, FilterSpec) for item in runtime_filters_raw
        ):
            runtime_filters_raw = [item.__dict__ for item in runtime_filters_raw]
        where = (
            default_filters_raw
            if not runtime_filters_raw
            else {"op": "and", "items": [default_filters_raw, runtime_filters_raw]}
        )
        queryset, applied_filters, warnings = self._apply_where(
            queryset,
            where=where,
            quick_search=quick_search,
        )

        simple_dimension_fields = [
            dim.field
            for dim in self.dimensions
            if dim.field and not dim.transform and dim.name == dim.field
        ]
        alias_dimensions = [
            dim
            for dim in self.dimensions
            if dim.field and (dim.transform or dim.name != dim.field)
        ]
        alias_exprs = {
            dim.name: self._dimension_expression(dim) for dim in alias_dimensions
        }
        alias_map = {dim.field: dim.name for dim in alias_dimensions}

        annotations = self._build_annotations(
            self.metrics,
            allowed_where_fields={dim.field for dim in self.dimensions if dim.field}
            | {metric.field for metric in self.metrics if metric.field},
        )

        if simple_dimension_fields or alias_exprs:
            queryset = queryset.values(*simple_dimension_fields, **alias_exprs)
        elif not annotations:
            fallback_fields = (self.dataset.metadata or {}).get("fields") or [
                self._default_pk_field()
            ]
            queryset = queryset.values(*fallback_fields)

        if annotations:
            queryset = queryset.annotate(**annotations)

        computed_query = [
            computed for computed in self.computed_fields if computed.stage == "query"
        ]
        if computed_query:
            allowed_names = (
                set(simple_dimension_fields)
                | set(alias_exprs.keys())
                | set(annotations.keys())
            )
            computed_annotations: dict[str, Any] = {}
            for computed in computed_query:
                try:
                    computed_annotations[computed.name] = _safe_query_expression(
                        computed.formula, allowed_names=allowed_names
                    )
                except ReportingError as exc:
                    warnings.append(str(exc))
            if computed_annotations:
                queryset = queryset.annotate(**computed_annotations)

        applied_ordering = _to_ordering(ordering) or _to_ordering(self.dataset.ordering)
        resolved_ordering: list[str] = []
        for token in applied_ordering:
            desc = token.startswith("-")
            name = token[1:] if desc else token
            resolved = alias_map.get(name, name)
            resolved_ordering.append(f"-{resolved}" if desc else resolved)
        if applied_ordering:
            queryset = queryset.order_by(*resolved_ordering)

        bounded_limit = None
        if limit is not None:
            limit_value = _coerce_int(limit, default=0)
            if limit_value < 0:
                warnings.append(f"Limite negative ignoree: {limit}")
                limit_value = 0
            bounded_limit = min(limit_value, self._max_limit())
            queryset = queryset[:bounded_limit]

        rows = list(queryset)
        self._apply_computed_fields(rows)

        payload = {
            "rows": rows,
            "columns": self.describe_columns(),
            "dimensions": [dim.__dict__ for dim in self.dimensions],
            "metrics": [metric.__dict__ for metric in self.metrics],
            "computed_fields": [comp.__dict__ for comp in self.computed_fields],
            "applied_filters": [spec.__dict__ for spec in applied_filters],
            "warnings": warnings,
            "ordering": resolved_ordering,
            "limit": bounded_limit if bounded_limit is not None else limit,
            "source": {
                "app_label": self.dataset.source_app_label,
                "model": self.dataset.source_model,
            },
        }
        return _json_sanitize(payload)

    def _resolve_dimensions(self, raw: Any) -> tuple[list[DimensionSpec], list[str]]:
        warnings: list[str] = []
        if raw is None:
            return list(self.dimensions), warnings

        if not isinstance(raw, list):
            warnings.append("Dimensions invalides: liste attendue.")
            return list(self.dimensions), warnings

        by_name = {dim.name: dim for dim in self.dimensions}
        by_field = {dim.field: dim for dim in self.dimensions if dim.field}
        resolved: list[DimensionSpec] = []

        for entry in raw:
            if isinstance(entry, str):
                dim = by_name.get(entry) or by_field.get(entry)
                if not dim:
                    warnings.append(f"Dimension inconnue: {entry}")
                    continue
                resolved.append(dim)
                continue

            if isinstance(entry, dict):
                field_path = entry.get("field")
                raw_name = entry.get("name") or field_path
                transform = entry.get("transform")
                if not field_path:
                    warnings.append("Dimension incomplete: champ manquant.")
                    continue
                if not self._allow_ad_hoc() and raw_name not in by_name:
                    warnings.append(f"Dimension ad-hoc refusee: {raw_name}")
                    continue
                name = (
                    _safe_identifier(
                        raw_name, fallback=_safe_identifier(field_path, fallback="dim")
                    )
                    if (transform or (raw_name and raw_name != field_path))
                    else raw_name
                )
                resolved.append(
                    DimensionSpec(
                        name=name,
                        field=field_path,
                        label=entry.get("label") or raw_name or field_path,
                        transform=transform,
                        help_text=entry.get("help_text", ""),
                    )
                )
                continue

            warnings.append("Dimension invalide: string/dict attendu.")

        return resolved, warnings

    def _resolve_metrics(self, raw: Any) -> tuple[list[MetricSpec], list[str]]:
        warnings: list[str] = []
        if raw is None:
            return list(self.metrics), warnings

        if not isinstance(raw, list):
            warnings.append("Mesures invalides: liste attendue.")
            return list(self.metrics), warnings

        by_name = {metric.name: metric for metric in self.metrics}
        resolved: list[MetricSpec] = []
        for entry in raw:
            if isinstance(entry, str):
                metric = by_name.get(entry)
                if not metric:
                    warnings.append(f"Mesure inconnue: {entry}")
                    continue
                resolved.append(metric)
                continue

            if isinstance(entry, dict):
                field_path = entry.get("field")
                raw_name = entry.get("name") or field_path
                if not raw_name:
                    warnings.append("Mesure incomplete: nom manquant.")
                    continue
                if not field_path and (entry.get("aggregation") or "").lower() not in {
                    "count"
                }:
                    warnings.append(f"Mesure incomplete ({raw_name}): champ manquant.")
                    continue
                if not self._allow_ad_hoc() and raw_name not in by_name:
                    warnings.append(f"Mesure ad-hoc refusee: {raw_name}")
                    continue
                resolved.append(
                    MetricSpec(
                        name=_safe_identifier(raw_name, fallback="metric"),
                        field=field_path or "pk",
                        aggregation=entry.get("aggregation") or "sum",
                        label=entry.get("label") or raw_name,
                        help_text=entry.get("help_text", ""),
                        format=entry.get("format"),
                        filter=entry.get("filter"),
                        options=entry.get("options")
                        if isinstance(entry.get("options"), dict)
                        else None,
                    )
                )
                continue

            warnings.append("Mesure invalide: string/dict attendu.")

        return resolved, warnings

    def _resolve_computed_fields(
        self, raw: Any
    ) -> tuple[list[ComputedFieldSpec], list[str]]:
        warnings: list[str] = []
        if raw is None:
            return list(self.computed_fields), warnings

        if not isinstance(raw, list):
            warnings.append("Champs calcules invalides: liste attendue.")
            return list(self.computed_fields), warnings

        by_name = {computed.name: computed for computed in self.computed_fields}
        resolved: list[ComputedFieldSpec] = []
        for entry in raw:
            if isinstance(entry, str):
                computed = by_name.get(entry)
                if not computed:
                    warnings.append(f"Champ calcule inconnu: {entry}")
                    continue
                resolved.append(computed)
                continue

            if isinstance(entry, dict):
                name = entry.get("name")
                formula = entry.get("formula")
                if not name or not formula:
                    warnings.append("Champ calcule incomplet: name/formula requis.")
                    continue
                stage = str(entry.get("stage") or "post").lower()
                resolved.append(
                    ComputedFieldSpec(
                        name=_safe_identifier(name, fallback="computed")
                        if stage == "query"
                        else name,
                        formula=formula,
                        label=entry.get("label") or name,
                        help_text=entry.get("help_text", ""),
                        stage=stage,
                    )
                )
                continue

            warnings.append("Champ calcule invalide: string/dict attendu.")

        return resolved, warnings

    def _compile_annotation_filter_specs(
        self,
        specs: list[FilterSpec],
        *,
        warnings: list[str],
        allowed_names: set[str],
        allowed_lookups: set[str],
    ) -> Optional[Q]:
        combined: Optional[Q] = None
        for spec in specs:
            lookup = (spec.lookup or "exact").lower()
            if lookup not in allowed_lookups or "__" in lookup:
                warnings.append(f"Lookup non autorise: {lookup}")
                continue

            name = str(spec.field)
            if name not in allowed_names:
                warnings.append(f"Champ non autorise: {name}")
                continue

            try:
                condition = Q(**{f"{name}__{lookup}": spec.value})
            except Exception as exc:
                warnings.append(f"Filtre ignore ({name}): {exc}")
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

    def _compile_annotation_filter_tree(
        self,
        raw_filters: Any,
        *,
        allowed_names: set[str],
        allowed_lookups: Optional[set[str]] = None,
    ) -> tuple[Optional[Q], list[str]]:
        warnings: list[str] = []
        allowed_lookups = allowed_lookups or self._allowed_lookups()

        if raw_filters is None:
            return None, warnings

        if isinstance(raw_filters, list) and all(
            isinstance(item, dict) and "field" in item for item in raw_filters
        ):
            q = self._compile_annotation_filter_specs(
                _to_filter_list(raw_filters),
                warnings=warnings,
                allowed_names=allowed_names,
                allowed_lookups=allowed_lookups,
            )
            return q, warnings

        if isinstance(raw_filters, dict) and "items" in raw_filters:
            op = str(
                raw_filters.get("op") or raw_filters.get("connector") or "and"
            ).lower()
            negate = bool(raw_filters.get("negate") or raw_filters.get("not"))
            compiled_children: list[Q] = []
            for item in raw_filters.get("items") or []:
                child_q, child_warnings = self._compile_annotation_filter_tree(
                    item,
                    allowed_names=allowed_names,
                    allowed_lookups=allowed_lookups,
                )
                warnings.extend(child_warnings)
                if child_q is not None:
                    compiled_children.append(child_q)
            q = _combine_q(compiled_children, op=op)
            return ((~q) if (negate and q is not None) else q), warnings

        if isinstance(raw_filters, dict) and "field" in raw_filters:
            q = self._compile_annotation_filter_specs(
                _to_filter_list([raw_filters]),
                warnings=warnings,
                allowed_names=allowed_names,
                allowed_lookups=allowed_lookups,
            )
            return q, warnings

        warnings.append("Filtres HAVING invalides.")
        return None, warnings

    def _apply_computed_fields_runtime(
        self, rows: list[dict[str, Any]], computed_fields: list[ComputedFieldSpec]
    ) -> None:
        computed_post = [
            computed for computed in computed_fields if computed.stage != "query"
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


__all__ = ["AggregationMixin"]

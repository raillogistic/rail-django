"""
Execution mixin for DatasetExecutionEngine.

This module contains the run_query() method and its helpers including
_run_records_mode, _run_aggregate_mode, and describe_dataset.
"""

from __future__ import annotations

from typing import Any, Optional

from django.core.cache import cache

from ..types import ReportingError
from ..utils import (
    _coerce_int,
    _hash_query_payload,
    _json_sanitize,
    _safe_query_expression,
    _to_ordering,
)


class ExecutionMixin:
    """
    Mixin providing dynamic query execution methods for the execution engine.

    These methods handle the run_query() operation, including records mode,
    aggregate mode, caching, and dataset description.
    """

    def run_query(self, spec: Optional[dict] = None) -> dict[str, Any]:
        """
        Execute a dynamic query (semantic layer) for dashboards.

        Spec (JSON) keys:
        - `mode`: "aggregate" (default) or "records"
        - `dimensions` / `metrics` / `computed_fields`: list of names or dict specs
        - `filters`: filter tree (WHERE)
        - `having`: filter tree (HAVING) applied on metric/computed aliases
        - `ordering`: list or string (e.g. ["-total_cost"])
        - `limit`, `offset`, `quick`
        - `pivot`: {index, columns, values} (optional)
        - `cache`: bool (optional, defaults to true)
        """

        spec = dict(spec or {})
        mode = str(spec.get("mode") or "aggregate").lower()
        quick_search = str(spec.get("quick") or "")
        limit = _coerce_int(spec.get("limit"), default=self.dataset.preview_limit)
        offset = _coerce_int(spec.get("offset"), default=0)
        ordering = _to_ordering(spec.get("ordering")) or _to_ordering(
            self.dataset.ordering
        )
        where = spec.get("filters") if "filters" in spec else spec.get("where")
        having = spec.get("having")
        where = self._merge_default_filters(where)

        cache_enabled = spec.get("cache", True)
        ttl = self._cache_ttl_seconds()
        cache_key = None
        if cache_enabled and ttl > 0:
            cache_key = (
                f"rail_django:reporting:{self.dataset.id}:{self.dataset.updated_at.isoformat()}:"
                f"{_hash_query_payload(spec)}"
            )
            cached = cache.get(cache_key)
            if cached:
                payload = dict(cached)
                payload["cache"] = {"hit": True, "key": cache_key, "ttl_seconds": ttl}
                return payload

        warnings: list[str] = []

        if mode == "records":
            return self._run_records_mode(
                spec=spec,
                where=where,
                quick_search=quick_search,
                ordering=ordering,
                limit=limit,
                offset=offset,
                warnings=warnings,
                cache_key=cache_key,
                ttl=ttl,
            )

        return self._run_aggregate_mode(
            spec=spec,
            where=where,
            having=having,
            quick_search=quick_search,
            ordering=ordering,
            limit=limit,
            offset=offset,
            warnings=warnings,
            cache_key=cache_key,
            ttl=ttl,
        )

    def _run_records_mode(
        self,
        *,
        spec: dict,
        where: Any,
        quick_search: str,
        ordering: list[str],
        limit: int,
        offset: int,
        warnings: list[str],
        cache_key: Optional[str],
        ttl: int,
    ) -> dict[str, Any]:
        queryset = self.model.objects.all()
        queryset, applied_filters, where_warnings = self._apply_where(
            queryset,
            where=where,
            quick_search=quick_search,
        )
        warnings.extend(where_warnings)

        meta_fields = self._meta().get("fields") or []
        if isinstance(meta_fields, str):
            meta_fields = [meta_fields]
        if not isinstance(meta_fields, list):
            meta_fields = []

        fields_specified = "fields" in spec
        pk_field = self._default_pk_field()
        fields = (
            spec.get("fields")
            if fields_specified
            else (meta_fields or [pk_field])
        )
        if isinstance(fields, str):
            fields = [fields]
        if not isinstance(fields, list):
            fields = [pk_field]

        allowed_record_fields = self._record_field_allowlist()
        selected_fields = self._normalize_field_list(
            fields,
            warnings=warnings,
            allowlist=allowed_record_fields,
            label="Champ",
        )
        if not selected_fields and fields_specified and meta_fields:
            selected_fields = self._normalize_field_list(
                meta_fields,
                warnings=warnings,
                allowlist=allowed_record_fields,
                label="Champ",
            )
        if not selected_fields:
            if allowed_record_fields is None or pk_field in (
                allowed_record_fields or set()
            ):
                selected_fields = [pk_field]
            else:
                raise ReportingError(
                    "Aucun champ autorise pour le mode records."
                )

        resolved_ordering: list[str] = []
        for token in ordering:
            name = token.lstrip("-")
            if not self._validate_field_path(name):
                warnings.append(f"Tri invalide: {token}")
                continue
            if allowed_record_fields is not None and name not in allowed_record_fields:
                warnings.append(f"Tri non autorise: {token}")
                continue
            resolved_ordering.append(token)
        if resolved_ordering:
            queryset = queryset.order_by(*resolved_ordering)

        bounded_limit = min(int(limit), self._max_limit())
        if offset:
            queryset = queryset[offset : offset + bounded_limit]
        else:
            queryset = queryset[:bounded_limit]

        payload = {
            "mode": "records",
            "rows": list(queryset.values(*selected_fields)),
            "fields": selected_fields,
            "applied_filters": [spec.__dict__ for spec in applied_filters],
            "ordering": resolved_ordering,
            "limit": bounded_limit,
            "offset": offset,
            "warnings": warnings,
            "source": {
                "app_label": self.dataset.source_app_label,
                "model": self.dataset.source_model,
            },
            "query": spec,
            "dataset": {
                "id": getattr(self.dataset, "id", None),
                "code": self.dataset.code,
                "title": self.dataset.title,
            },
        }
        if cache_key:
            cache.set(cache_key, payload, ttl)
            payload["cache"] = {"hit": False, "key": cache_key, "ttl_seconds": ttl}
        return _json_sanitize(payload)

    def _run_aggregate_mode(
        self,
        *,
        spec: dict,
        where: Any,
        having: Any,
        quick_search: str,
        ordering: list[str],
        limit: int,
        offset: int,
        warnings: list[str],
        cache_key: Optional[str],
        ttl: int,
    ) -> dict[str, Any]:
        dimensions, dim_warnings = self._resolve_dimensions(spec.get("dimensions"))
        metrics, metric_warnings = self._resolve_metrics(spec.get("metrics"))
        computed_fields, computed_warnings = self._resolve_computed_fields(
            spec.get("computed_fields")
        )
        warnings.extend(dim_warnings + metric_warnings + computed_warnings)

        queryset = self.model.objects.all()
        allowed_where_fields = {dim.field for dim in dimensions if dim.field} | {
            metric.field for metric in metrics if metric.field
        }
        queryset, applied_filters, where_warnings = self._apply_where(
            queryset,
            where=where,
            quick_search=quick_search,
            allowed_fields=allowed_where_fields,
        )
        warnings.extend(where_warnings)

        simple_dimension_fields = [
            dim.field
            for dim in dimensions
            if dim.field and not dim.transform and dim.name == dim.field
        ]
        alias_dimensions = [
            dim
            for dim in dimensions
            if dim.field and (dim.transform or dim.name != dim.field)
        ]
        alias_exprs = {
            dim.name: self._dimension_expression(dim) for dim in alias_dimensions
        }
        alias_map = {dim.field: dim.name for dim in alias_dimensions}

        annotations = self._build_annotations(
            metrics, allowed_where_fields=allowed_where_fields
        )

        fallback_fields: list[str] = []
        if simple_dimension_fields or alias_exprs:
            queryset = queryset.values(*simple_dimension_fields, **alias_exprs)
        elif not annotations:
            fallback_fields = self._normalize_field_list(
                self._meta().get("fields") or [self._default_pk_field()],
                warnings=warnings,
                allowlist=None,
                label="Champ",
            )
            if not fallback_fields:
                fallback_fields = [self._default_pk_field()]
            queryset = queryset.values(*fallback_fields)

        if annotations:
            queryset = queryset.annotate(**annotations)

        computed_query = [
            computed for computed in computed_fields if computed.stage == "query"
        ]
        if computed_query:
            allowed_names = (
                set(simple_dimension_fields)
                | set(alias_exprs.keys())
                | set(annotations.keys())
                | set(fallback_fields)
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

        allowed_having_names = set(annotations.keys()) | {
            comp.name for comp in computed_query
        }
        having_q, having_warnings = self._compile_annotation_filter_tree(
            having, allowed_names=allowed_having_names
        )
        warnings.extend(having_warnings)
        if having_q is not None:
            queryset = queryset.filter(having_q)

        resolved_ordering: list[str] = []
        allowed_ordering_names = (
            set(simple_dimension_fields)
            | set(alias_exprs.keys())
            | set(annotations.keys())
            | {comp.name for comp in computed_query}
        )
        for token in ordering:
            desc = token.startswith("-")
            name = token[1:] if desc else token
            resolved = alias_map.get(name, name)
            if resolved not in allowed_ordering_names:
                warnings.append(f"Tri ignore: {token}")
                continue
            resolved_ordering.append(f"-{resolved}" if desc else resolved)

        if resolved_ordering:
            queryset = queryset.order_by(*resolved_ordering)

        bounded_limit = min(int(limit), self._max_limit())
        if offset:
            queryset = queryset[offset : offset + bounded_limit]
        else:
            queryset = queryset[:bounded_limit]

        rows = list(queryset)
        self._apply_computed_fields_runtime(rows, computed_fields)

        payload: dict[str, Any] = {
            "mode": "aggregate",
            "rows": rows,
            "columns": self.describe_columns_for(dimensions, metrics, computed_fields),
            "dimensions": [dim.__dict__ for dim in dimensions],
            "metrics": [metric.__dict__ for metric in metrics],
            "computed_fields": [comp.__dict__ for comp in computed_fields],
            "applied_filters": [spec.__dict__ for spec in applied_filters],
            "ordering": resolved_ordering,
            "limit": bounded_limit,
            "offset": offset,
            "warnings": warnings,
            "source": {
                "app_label": self.dataset.source_app_label,
                "model": self.dataset.source_model,
            },
            "query": spec,
            "dataset": {
                "id": getattr(self.dataset, "id", None),
                "code": self.dataset.code,
                "title": self.dataset.title,
            },
        }

        pivot = spec.get("pivot")
        if isinstance(pivot, dict):
            pivot_index = pivot.get("index")
            pivot_columns = pivot.get("columns")
            pivot_values = pivot.get("values")
            if isinstance(pivot_values, str):
                pivot_values = [pivot_values]
            if (
                isinstance(pivot_index, str)
                and isinstance(pivot_columns, str)
                and isinstance(pivot_values, list)
            ):
                payload["pivot"] = self._pivot_rows(
                    rows,
                    index=pivot_index,
                    columns=pivot_columns,
                    values=[str(value) for value in pivot_values if value],
                )

        if cache_key:
            cache.set(cache_key, payload, ttl)
            payload["cache"] = {"hit": False, "key": cache_key, "ttl_seconds": ttl}

        return _json_sanitize(payload)

    def describe_dataset(
        self,
        *,
        include_model_fields: bool = True,
    ) -> dict[str, Any]:
        """
        Return a description payload used by dashboard builders.

        The payload exposes the dataset semantic layer plus an optional snapshot
        of the underlying Django model fields.
        """

        meta = self._meta()
        payload: dict[str, Any] = {
            "dataset": {
                "id": getattr(self.dataset, "id", None),
                "code": self.dataset.code,
                "title": self.dataset.title,
                "description": self.dataset.description,
                "source_kind": self.dataset.source_kind,
                "source": {
                    "app_label": self.dataset.source_app_label,
                    "model": self.dataset.source_model,
                },
                "ui": meta,
            },
            "semantic_layer": {
                "dimensions": [dim.__dict__ for dim in self.dimensions],
                "metrics": [metric.__dict__ for metric in self.metrics],
                "computed_fields": [
                    computed.__dict__ for computed in self.computed_fields
                ],
                "allowed_lookups": sorted(self._allowed_lookups()),
                "allow_ad_hoc": self._allow_ad_hoc(),
                "allowed_fields": sorted(self._allowed_ad_hoc_fields()),
                "max_limit": self._max_limit(),
                "cache_ttl_seconds": self._cache_ttl_seconds(),
            },
        }

        if not include_model_fields:
            return _json_sanitize(payload)

        fields: list[dict[str, Any]] = []
        for field in self.model._meta.get_fields():
            if getattr(field, "auto_created", False) and not getattr(
                field, "concrete", False
            ):
                continue
            if getattr(field, "many_to_many", False) and getattr(
                field, "auto_created", False
            ):
                continue
            related_model = getattr(field, "related_model", None)
            info: dict[str, Any] = {
                "name": getattr(field, "name", None),
                "verbose_name": str(getattr(field, "verbose_name", "")),
                "type": field.__class__.__name__,
                "internal_type": getattr(field, "get_internal_type", lambda: "")(),
                "is_relation": bool(getattr(field, "is_relation", False)),
                "many_to_many": bool(getattr(field, "many_to_many", False)),
                "many_to_one": bool(getattr(field, "many_to_one", False)),
                "one_to_one": bool(getattr(field, "one_to_one", False)),
                "null": bool(getattr(field, "null", False)),
                "blank": bool(getattr(field, "blank", False)),
            }
            if related_model is not None:
                info["related_model"] = (
                    f"{related_model._meta.app_label}.{related_model.__name__}"
                )
            choices = getattr(field, "choices", None)
            if choices:
                info["choices"] = [
                    {"value": _json_sanitize(value), "label": _json_sanitize(label)}
                    for value, label in choices[:50]
                ]
            fields.append(info)

        payload["model_fields"] = fields
        return _json_sanitize(payload)


__all__ = ["ExecutionMixin"]

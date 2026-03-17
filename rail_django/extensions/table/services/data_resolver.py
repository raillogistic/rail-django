"""Rows resolver for table v3."""

from __future__ import annotations

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from graphql import GraphQLError

from ..cache.keys import table_rows_key
from ..cache.store import get_cache, set_cache
from ..cache.strategies import stale_while_revalidate
from ..performance.monitoring import record_metric
from ..performance.optimization import build_query_hints
from ..performance.profiling import profile_block
from ..security.access import (
    can_read_table_model,
    get_table_permissions,
    get_visible_table_fields,
    resolve_table_model,
)
from ..security.field_masking import apply_field_masking
from ..security.input_validator import sanitize_text


_ALLOWED_FILTER_LOOKUPS = {
    "exact",
    "iexact",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "in",
    "isnull",
    "gt",
    "gte",
    "lt",
    "lte",
    "range",
}


def _to_json_safe(value):
    """Normalize nested payload values to JSON-safe primitives."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _table_user_scope(user) -> str:
    user_id = getattr(user, "id", None)
    return f"user:{user_id}" if user_id is not None else "anon"


def _normalize_ordering(ordering: list[str], allowed_fields: set[str]) -> list[str]:
    normalized: list[str] = []
    for token in ordering:
        raw = str(token or "").strip()
        if not raw:
            continue
        field_name = raw.lstrip("-")
        if field_name not in allowed_fields:
            continue
        normalized.append(f"-{field_name}" if raw.startswith("-") else field_name)
    return normalized


def _normalize_filters(where: dict, allowed_fields: set[str]) -> dict:
    normalized: dict[str, object] = {}
    for raw_key, value in where.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        parts = key.split("__", 1)
        field_name = parts[0]
        lookup = parts[1] if len(parts) == 2 else "exact"
        if field_name not in allowed_fields or lookup not in _ALLOWED_FILTER_LOOKUPS:
            continue
        normalized_key = field_name if lookup == "exact" else f"{field_name}__{lookup}"
        if isinstance(value, str):
            normalized[normalized_key] = sanitize_text(value)
        elif lookup == "in" and isinstance(value, (list, tuple)):
            normalized[normalized_key] = list(value)
        else:
            normalized[normalized_key] = value
    return normalized


def resolve_table_rows(input_data: dict, *, info=None) -> dict:
    app = input_data["app"]
    model = input_data["model"]
    page = max(int(input_data.get("page") or 1), 1)
    page_size = max(min(int(input_data.get("pageSize") or 25), 200), 1)
    ordering = input_data.get("ordering") or ["-id"]
    quick_search = (input_data.get("quickSearch") or "").strip()
    where = input_data.get("where") or {}
    distinct_on = input_data.get("distinctOn")
    presets = input_data.get("presets") or []
    user = getattr(getattr(info, "context", None), "user", None)
    schema_name = getattr(getattr(info, "context", None), "schema_name", "default")

    model_cls = resolve_table_model(app, model)
    permissions = get_table_permissions(user, model_cls)
    if not can_read_table_model(
        user,
        model_cls,
        schema_name=schema_name,
        operation="list",
        permission_snapshot=permissions,
    ):
        raise GraphQLError("Permission denied.")

    visible_fields, _editable_fields, masked_fields = get_visible_table_fields(
        user,
        model_cls,
    )
    allowed_fields = set(visible_fields)
    if not allowed_fields:
        raise GraphQLError("No readable fields are available for this table.")

    normalized_where = _normalize_filters(
        where if isinstance(where, dict) else {},
        allowed_fields,
    )
    normalized_ordering = _normalize_ordering(
        ordering if isinstance(ordering, list) else ["-id"],
        allowed_fields,
    )
    if not normalized_ordering:
        fallback_field = "id" if "id" in allowed_fields else sorted(allowed_fields)[0]
        normalized_ordering = [f"-{fallback_field}"]

    cache_payload = {
        "page": page,
        "page_size": page_size,
        "ordering": normalized_ordering,
        "quick_search": quick_search,
        "where": normalized_where,
        "distinct_on": distinct_on,
        "presets": presets,
        "fields": sorted(allowed_fields),
    }
    cache_key = table_rows_key(
        app,
        model,
        user_scope=_table_user_scope(user),
        payload=cache_payload,
    )
    cached = get_cache(cache_key)
    if isinstance(cached, dict):
        return cached

    qs = model_cls.objects.all()

    if quick_search:
        text_fields = [
            f.name
            for f in model_cls._meta.fields
            if f.name in allowed_fields
            and f.get_internal_type() in {"CharField", "TextField"}
        ]
        if text_fields:
            query = Q()
            for name in text_fields:
                query |= Q(**{f"{name}__icontains": quick_search})
            qs = qs.filter(query)

    if normalized_where:
        qs = qs.filter(**normalized_where)

    if isinstance(presets, list):
        for preset in presets:
            if isinstance(preset, dict) and preset.get("field") and "value" in preset:
                field = str(preset["field"])
                if field in allowed_fields:
                    qs = qs.filter(**{field: preset["value"]})

    with profile_block(record_metric, "table.rows.resolve.seconds"):
        qs = qs.order_by(*normalized_ordering)
        if distinct_on and isinstance(distinct_on, str) and distinct_on in allowed_fields:
            qs = qs.distinct(distinct_on)
        elif distinct_on:
            qs = qs.distinct()
        total_count = qs.count()
        offset = (page - 1) * page_size
        rows = list(qs[offset : offset + page_size].values(*visible_fields))

    masked_rows = [apply_field_masking(row, masked_fields) for row in rows]
    safe_rows = _to_json_safe(masked_rows)
    page_count = (total_count + page_size - 1) // page_size if total_count else 1

    payload = {
        "pageInfo": {
            "totalCount": total_count,
            "pageCount": page_count,
            "currentPage": page,
            "hasNextPage": page < page_count,
            "hasPreviousPage": page > 1,
            "prefetchNextPage": page < page_count,
        },
        "items": safe_rows,
        "etag": f"{app}:{model}:{total_count}:{page}:{page_size}",
        "cacheControl": stale_while_revalidate(),
        "aggregate": build_query_hints(page_size),
    }
    set_cache(cache_key, payload, ttl_seconds=30)
    return payload

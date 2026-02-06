"""Rows resolver for table v3."""

from __future__ import annotations

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.apps import apps
from django.db.models import Q

from ..cache.keys import table_rows_key
from ..cache.store import get_cache, set_cache
from ..cache.strategies import stale_while_revalidate
from ..performance.optimization import build_query_hints
from ..performance.profiling import profile_block
from ..performance.monitoring import record_metric
from ..security.field_masking import apply_field_masking
from ..security.input_validator import sanitize_text


def _to_json_safe(value):
    """
    Normalize nested payload values to JSON-safe primitives.
    This avoids Graphene JSONString serialization errors (e.g. Decimal).
    """
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def resolve_table_rows(input_data: dict) -> dict:
    app = input_data["app"]
    model = input_data["model"]
    page = max(int(input_data.get("page") or 1), 1)
    page_size = max(min(int(input_data.get("pageSize") or 25), 200), 1)
    ordering = input_data.get("ordering") or ["-id"]
    quick_search = (input_data.get("quickSearch") or "").strip()
    where = input_data.get("where") or {}
    distinct_on = input_data.get("distinctOn")
    presets = input_data.get("presets") or []

    cache_key = table_rows_key(app, model, page, page_size)
    cached = get_cache(cache_key)
    if isinstance(cached, dict):
        return cached

    model_cls = apps.get_model(app, model)
    qs = model_cls.objects.all()

    if quick_search:
        text_fields = [
            f.name
            for f in model_cls._meta.fields
            if f.get_internal_type() in {"CharField", "TextField"}
        ]
        if text_fields:
            query = Q()
            for name in text_fields:
                query |= Q(**{f"{name}__icontains": quick_search})
            qs = qs.filter(query)

    if isinstance(where, dict):
        safe_filters = {}
        for key, value in where.items():
            if isinstance(value, str):
                safe_filters[key] = sanitize_text(value)
            else:
                safe_filters[key] = value
        if safe_filters:
            qs = qs.filter(**safe_filters)

    if isinstance(presets, list):
        for preset in presets:
            if isinstance(preset, dict) and preset.get("field") and "value" in preset:
                field = str(preset["field"])
                qs = qs.filter(**{field: preset["value"]})

    with profile_block(record_metric, "table.rows.resolve.seconds"):
        qs = qs.order_by(*ordering)
        if distinct_on:
            qs = qs.distinct(distinct_on) if isinstance(distinct_on, str) else qs.distinct()
        total_count = qs.count()
        offset = (page - 1) * page_size
        rows = list(qs[offset : offset + page_size].values())

    masked_rows = [apply_field_masking(row, set()) for row in rows]
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

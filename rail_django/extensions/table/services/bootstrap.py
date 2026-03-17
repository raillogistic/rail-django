"""Bootstrap resolver service for table v3."""

from __future__ import annotations

import hashlib
import json

from graphql import GraphQLError

from ..cache.keys import table_bootstrap_key
from ..cache.store import get_cache, set_cache
from ..extraction.table_config_extractor import extract_table_config
from ..security.access import (
    can_read_table_model,
    get_table_permissions,
    get_visible_table_fields,
    resolve_table_model,
)
from .user_state import DEFAULT_TABLE_PAGE_SIZE, resolve_user_table_state


def _hash_payload(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _table_user_scope(user) -> str:
    user_id = getattr(user, "id", None)
    return f"user:{user_id}" if user_id is not None else "anon"


def _resolve_default_ordering(table_config: dict) -> list[str]:
    resolved: list[str] = []
    for entry in table_config.get("defaultSort", []) or []:
        if not isinstance(entry, dict):
            continue
        field = str(entry.get("field") or "").strip()
        if not field:
            continue
        direction = str(entry.get("direction") or "ASC").strip().upper()
        resolved.append(f"-{field}" if direction == "DESC" else field)
    return resolved


def build_table_bootstrap_payload(
    app: str,
    model: str,
    *,
    user=None,
    persistence_key: str | None = None,
    schema_name: str = "default",
) -> dict:
    normalized_persistence_key = str(persistence_key or "").strip() or None
    cache_key = table_bootstrap_key(
        app,
        model,
        user_scope=_table_user_scope(user),
        persistence_scope=normalized_persistence_key,
    )
    cached = get_cache(cache_key)
    if isinstance(cached, dict):
        return cached

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

    visible_fields, editable_fields, _masked_fields = get_visible_table_fields(
        user,
        model_cls,
    )
    table_config = extract_table_config(
        model_cls,
        visible_fields=visible_fields,
        editable_fields=editable_fields,
    )
    table_config["app"] = app
    table_config["model"] = model

    default_ordering = _resolve_default_ordering(table_config)
    initial_page_size = (
        int(table_config.get("pagination", {}).get("defaultPageSize") or 0)
        or DEFAULT_TABLE_PAGE_SIZE
    )
    user_table_state = resolve_user_table_state(
        user,
        persistence_key=normalized_persistence_key,
    )
    if isinstance(user_table_state, dict):
        initial_page_size = int(user_table_state.get("perPage") or initial_page_size)
        if user_table_state.get("ordering"):
            default_ordering = list(user_table_state["ordering"])

    config_version = _hash_payload(table_config)
    model_schema_version = _hash_payload(
        {"fields": [field.name for field in model_cls._meta.fields]}
    )
    initial_state = {
        "page": 1,
        "pageSize": initial_page_size,
        "ordering": default_ordering,
    }
    if isinstance(user_table_state, dict):
        for key in (
            "columnOrder",
            "columnVisibility",
            "columnWidths",
            "density",
            "wrapCells",
            "visibilityVersion",
            "persistenceKey",
        ):
            if key in user_table_state:
                initial_state[key] = user_table_state[key]

    payload = {
        "configVersion": config_version,
        "modelSchemaVersion": model_schema_version,
        "deployVersion": "v3",
        "tableConfig": table_config,
        "initialState": initial_state,
        "permissions": {
            "canView": permissions.can_view,
            "canCreate": permissions.can_create,
            "canExport": permissions.can_export,
        },
    }
    set_cache(cache_key, payload, ttl_seconds=120)
    return payload

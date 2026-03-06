"""Bootstrap resolver service for table v3."""

from __future__ import annotations

import hashlib
import json

from graphql import GraphQLError

from ..cache.keys import table_bootstrap_key
from ..cache.store import get_cache, set_cache
from ..extraction.table_config_extractor import extract_table_config
from ..security.access import (
    get_table_permissions,
    get_visible_table_fields,
    resolve_table_model,
)


def _hash_payload(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _table_user_scope(user) -> str:
    user_id = getattr(user, "id", None)
    return f"user:{user_id}" if user_id is not None else "anon"


def build_table_bootstrap_payload(app: str, model: str, *, user=None) -> dict:
    cache_key = table_bootstrap_key(app, model, user_scope=_table_user_scope(user))
    cached = get_cache(cache_key)
    if isinstance(cached, dict):
        return cached

    model_cls = resolve_table_model(app, model)
    permissions = get_table_permissions(user, model_cls)
    if not permissions.can_view:
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

    config_version = _hash_payload(table_config)
    model_schema_version = _hash_payload(
        {"fields": [field.name for field in model_cls._meta.fields]}
    )
    payload = {
        "configVersion": config_version,
        "modelSchemaVersion": model_schema_version,
        "deployVersion": "v3",
        "tableConfig": table_config,
        "initialState": {
            "page": 1,
            "pageSize": 25,
            "ordering": ["-id"] if any(
                column.get("id") == "id" for column in table_config.get("columns", [])
            ) else [],
        },
        "permissions": {
            "canView": permissions.can_view,
            "canCreate": permissions.can_create,
            "canExport": permissions.can_export,
        },
    }
    set_cache(cache_key, payload, ttl_seconds=120)
    return payload

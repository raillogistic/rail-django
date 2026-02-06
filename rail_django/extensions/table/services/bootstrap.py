"""Bootstrap resolver service for table v3."""

from __future__ import annotations

import hashlib
import json

from django.apps import apps

from ..cache.keys import table_bootstrap_key
from ..cache.store import get_cache, set_cache
from ..extraction.table_config_extractor import extract_table_config


def _hash_payload(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build_table_bootstrap_payload(app: str, model: str) -> dict:
    cache_key = table_bootstrap_key(app, model)
    cached = get_cache(cache_key)
    if isinstance(cached, dict):
        return cached

    model_cls = apps.get_model(app, model)
    table_config = extract_table_config(model_cls)
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
        "initialState": {"page": 1, "pageSize": 25, "ordering": ["-id"]},
        "permissions": {"canView": True, "canCreate": True, "canExport": True},
    }
    set_cache(cache_key, payload, ttl_seconds=120)
    return payload

"""
Form API configuration settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from django.conf import settings as django_settings

from ...core.meta import get_model_graphql_meta

DEFAULT_FORM_ERROR_KEY = "__all__"
DEFAULT_BULK_ROW_PATH_PREFIX = "items"


@dataclass(frozen=True)
class FormSettings:
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600
    generated_form_metadata_key: str = "generated_form"
    generated_form_excluded_models: tuple[str, ...] = field(default_factory=tuple)
    initial_data_relation_limit: int = 200


def _as_model_identifier(model: Any) -> str:
    return f"{model._meta.app_label}.{model.__name__}"


@lru_cache(maxsize=1)
def get_form_settings() -> FormSettings:
    raw = getattr(django_settings, "RAIL_DJANGO_FORM", {}) or {}
    excluded_models = raw.get("generated_form_excluded_models") or []
    return FormSettings(
        enable_cache=bool(raw.get("enable_cache", True)),
        cache_ttl_seconds=int(raw.get("cache_ttl_seconds", 3600)),
        generated_form_metadata_key=str(
            raw.get("generated_form_metadata_key", "generated_form")
        ),
        generated_form_excluded_models=tuple(str(item) for item in excluded_models),
        initial_data_relation_limit=max(int(raw.get("initial_data_relation_limit", 200)), 0),
    )


def get_generated_form_metadata(model: Any) -> dict[str, Any]:
    graphql_meta = get_model_graphql_meta(model)
    metadata = getattr(graphql_meta, "custom_metadata", None) or {}
    form_settings = get_form_settings()
    by_key = metadata.get(form_settings.generated_form_metadata_key)
    by_alias = metadata.get("generatedForm")
    candidate = by_key if isinstance(by_key, dict) else by_alias
    return candidate if isinstance(candidate, dict) else {}


def is_generated_form_enabled(model: Any) -> bool:
    metadata = get_generated_form_metadata(model)
    if "enabled" in metadata:
        return bool(metadata.get("enabled"))

    form_settings = get_form_settings()
    return _as_model_identifier(model) not in set(
        form_settings.generated_form_excluded_models
    )


def get_generated_form_overrides(model: Any, mode: str | None = None) -> dict[str, Any]:
    metadata = get_generated_form_metadata(model)
    overrides = metadata.get("overrides") if isinstance(metadata, dict) else None
    if not isinstance(overrides, dict):
        return {}
    if mode is None:
        return overrides
    mode_key = str(mode or "").upper()
    mode_overrides = overrides.get(mode_key) or overrides.get(mode_key.lower())
    return mode_overrides if isinstance(mode_overrides, dict) else overrides


def get_generated_form_relation_policy(model: Any) -> dict[str, Any]:
    metadata = get_generated_form_metadata(model)
    policy = metadata.get("relation_policy") or metadata.get("relationPolicy")
    if isinstance(policy, dict):
        return policy
    return {}

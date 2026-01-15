"""Configuration helpers for webhook delivery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings as django_settings

from ..config_proxy import get_settings_proxy
from ..defaults import LIBRARY_DEFAULTS, merge_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookEndpoint:
    name: str
    url: str
    enabled: bool = True
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 5
    signing_secret: Optional[str] = None
    signing_header: str = "X-Rail-Signature"
    signature_prefix: str = "sha256="
    event_header: str = "X-Rail-Event"
    id_header: str = "X-Rail-Event-Id"
    include_models: list[str] = field(default_factory=list)
    exclude_models: list[str] = field(default_factory=list)
    auth_token_path: Optional[str] = None
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    auth_url: Optional[str] = None
    auth_payload: dict[str, Any] = field(default_factory=dict)
    auth_headers: dict[str, str] = field(default_factory=dict)
    auth_timeout_seconds: int = 5
    auth_token_field: str = "access_token"


@dataclass(frozen=True)
class WebhookSettings:
    enabled: bool = False
    endpoints: list[WebhookEndpoint] = field(default_factory=list)
    events: dict[str, bool] = field(default_factory=dict)
    include_models: list[str] = field(default_factory=list)
    exclude_models: list[str] = field(default_factory=list)
    include_fields: dict[str, list[str]] = field(default_factory=dict)
    exclude_fields: dict[str, list[str]] = field(default_factory=dict)
    redact_fields: list[str] = field(default_factory=list)
    redact_fields_by_model: dict[str, list[str]] = field(default_factory=dict)
    redaction_mask: str = "***REDACTED***"
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 5
    signing_secret: Optional[str] = None
    signing_header: str = "X-Rail-Signature"
    signature_prefix: str = "sha256="
    event_header: str = "X-Rail-Event"
    id_header: str = "X-Rail-Event-Id"
    async_backend: str = "thread"
    async_task_path: Optional[str] = None
    max_workers: int = 4
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0
    retry_backoff_factor: float = 2.0
    retry_jitter_seconds: float = 0.5
    retry_statuses: list[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )


def webhooks_enabled(settings: WebhookSettings) -> bool:
    return bool(settings.enabled and settings.endpoints)


def get_webhook_settings() -> WebhookSettings:
    defaults = LIBRARY_DEFAULTS.get("webhook_settings", {})
    proxy = get_settings_proxy()
    base_config = proxy.get("webhook_settings", {}) or {}
    merged = merge_settings(defaults, base_config)

    external = getattr(django_settings, "RAIL_DJANGO_WEBHOOKS", None)
    if isinstance(external, dict):
        merged = merge_settings(merged, external)

    return _build_settings(merged)


def _build_settings(config: dict[str, Any]) -> WebhookSettings:
    events = _normalize_events(
        config.get("events"),
        LIBRARY_DEFAULTS.get("webhook_settings", {}).get("events", {}),
    )
    include_models = _normalize_list(config.get("include_models"))
    exclude_models = _normalize_list(config.get("exclude_models"))
    include_fields = _normalize_field_map(config.get("include_fields"))
    exclude_fields = _normalize_field_map(config.get("exclude_fields"))
    redact_fields, redact_by_model = _normalize_redact_fields(
        config.get("redact_fields")
    )

    endpoints = _normalize_endpoints(config)

    return WebhookSettings(
        enabled=bool(config.get("enabled", False)),
        endpoints=endpoints,
        events=events,
        include_models=include_models,
        exclude_models=exclude_models,
        include_fields=include_fields,
        exclude_fields=exclude_fields,
        redact_fields=redact_fields,
        redact_fields_by_model=redact_by_model,
        redaction_mask=str(config.get("redaction_mask", "***REDACTED***")),
        headers=_normalize_headers(config.get("headers")),
        timeout_seconds=int(config.get("timeout_seconds", 5) or 5),
        signing_secret=_coerce_optional_str(config.get("signing_secret")),
        signing_header=str(config.get("signing_header", "X-Rail-Signature")),
        signature_prefix=str(config.get("signature_prefix", "sha256=")),
        event_header=str(config.get("event_header", "X-Rail-Event")),
        id_header=str(config.get("id_header", "X-Rail-Event-Id")),
        async_backend=str(config.get("async_backend", "thread")),
        async_task_path=_coerce_optional_str(config.get("async_task_path")),
        max_workers=int(config.get("max_workers", 4) or 4),
        max_retries=int(config.get("max_retries", 3) or 0),
        retry_backoff_seconds=float(config.get("retry_backoff_seconds", 2.0) or 0),
        retry_backoff_factor=float(config.get("retry_backoff_factor", 2.0) or 1.0),
        retry_jitter_seconds=float(config.get("retry_jitter_seconds", 0.0) or 0.0),
        retry_statuses=_normalize_int_list(config.get("retry_statuses")),
    )


def _normalize_events(raw_events: Any, default_events: dict[str, Any]) -> dict[str, bool]:
    if not isinstance(default_events, dict) or not default_events:
        default_events = {"created": True, "updated": True, "deleted": True}
    normalized = {str(key).lower(): bool(value) for key, value in default_events.items()}

    if isinstance(raw_events, dict):
        for key, value in raw_events.items():
            if not key:
                continue
            normalized[str(key).lower()] = bool(value)
        return normalized

    if isinstance(raw_events, (list, tuple, set)):
        enabled = {str(item).lower() for item in raw_events if item}
        return {key: key in enabled for key in normalized}

    if isinstance(raw_events, str) and raw_events:
        enabled = {raw_events.lower()}
        return {key: key in enabled for key in normalized}

    return normalized


def _normalize_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]
    normalized: list[str] = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        normalized.append(text.lower())
    return normalized


def _normalize_field_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, fields in value.items():
        if not key:
            continue
        key_text = str(key).strip().lower()
        if not key_text:
            continue
        normalized[key_text] = _normalize_list(fields)
    return normalized


def _normalize_redact_fields(value: Any) -> tuple[list[str], dict[str, list[str]]]:
    if isinstance(value, dict):
        global_fields = _normalize_list(value.get("*"))
        per_model = {
            str(key).strip().lower(): _normalize_list(fields)
            for key, fields in value.items()
            if key and str(key).strip() != "*"
        }
        return global_fields, per_model
    return _normalize_list(value), {}


def _normalize_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    headers: dict[str, str] = {}
    for key, val in value.items():
        if not key:
            continue
        headers[str(key)] = str(val)
    return headers


def _normalize_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _normalize_int_list(value: Any) -> list[int]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]
    normalized: list[int] = []
    for item in items:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue
    return normalized


def _coerce_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_endpoints(config: dict[str, Any]) -> list[WebhookEndpoint]:
    raw_endpoints = config.get("endpoints") or []
    endpoints: list[WebhookEndpoint] = []

    items: Iterable
    if isinstance(raw_endpoints, dict):
        items = raw_endpoints.items()
    elif isinstance(raw_endpoints, (list, tuple)):
        items = enumerate(raw_endpoints, start=1)
    else:
        return endpoints

    default_headers = _normalize_headers(config.get("headers"))
    default_timeout = int(config.get("timeout_seconds", 5) or 5)
    default_signing_secret = _coerce_optional_str(config.get("signing_secret"))
    default_signing_header = str(config.get("signing_header", "X-Rail-Signature"))
    default_signature_prefix = str(config.get("signature_prefix", "sha256="))
    default_event_header = str(config.get("event_header", "X-Rail-Event"))
    default_id_header = str(config.get("id_header", "X-Rail-Event-Id"))
    default_include_models = _normalize_list(config.get("include_models"))
    default_exclude_models = _normalize_list(config.get("exclude_models"))
    default_auth_token_path = _coerce_optional_str(config.get("auth_token_path"))
    default_auth_header = str(config.get("auth_header", "Authorization"))
    default_auth_scheme = str(config.get("auth_scheme", "Bearer"))
    default_auth_url = _coerce_optional_str(config.get("auth_url"))
    default_auth_payload = _normalize_payload(config.get("auth_payload"))
    default_auth_headers = _normalize_headers(config.get("auth_headers"))
    default_auth_timeout = int(
        config.get("auth_timeout_seconds", default_timeout) or default_timeout
    )
    default_auth_token_field = str(config.get("auth_token_field", "access_token"))

    for idx, entry in items:
        name = None
        data: dict[str, Any]

        if isinstance(entry, dict):
            data = dict(entry)
            name = data.get("name")
        elif isinstance(entry, str):
            data = {"url": entry}
        else:
            continue

        if isinstance(idx, str) and not name:
            name = idx
        if not name:
            name = f"endpoint_{idx}"

        url = data.get("url")
        if not url:
            logger.warning("Webhook endpoint '%s' missing url; skipping", name)
            continue

        headers = dict(default_headers)
        headers.update(_normalize_headers(data.get("headers")))
        auth_headers = dict(default_auth_headers)
        auth_headers.update(_normalize_headers(data.get("auth_headers")))

        include_models = (
            _normalize_list(data.get("include_models"))
            if "include_models" in data
            else list(default_include_models)
        )
        exclude_models = (
            _normalize_list(data.get("exclude_models"))
            if "exclude_models" in data
            else list(default_exclude_models)
        )

        endpoint = WebhookEndpoint(
            name=str(name),
            url=str(url),
            enabled=bool(data.get("enabled", True)),
            headers=headers,
            timeout_seconds=int(data.get("timeout_seconds", default_timeout) or default_timeout),
            signing_secret=_coerce_optional_str(
                data.get("signing_secret", default_signing_secret)
            ),
            signing_header=str(data.get("signing_header", default_signing_header)),
            signature_prefix=str(
                data.get("signature_prefix", default_signature_prefix)
            ),
            event_header=str(data.get("event_header", default_event_header)),
            id_header=str(data.get("id_header", default_id_header)),
            include_models=include_models,
            exclude_models=exclude_models,
            auth_token_path=_coerce_optional_str(
                data.get("auth_token_path", default_auth_token_path)
            ),
            auth_header=str(data.get("auth_header", default_auth_header)),
            auth_scheme=str(data.get("auth_scheme", default_auth_scheme)),
            auth_url=_coerce_optional_str(data.get("auth_url", default_auth_url)),
            auth_payload=_normalize_payload(
                data.get("auth_payload", default_auth_payload)
            ),
            auth_headers=auth_headers,
            auth_timeout_seconds=int(
                data.get("auth_timeout_seconds", default_auth_timeout) or default_auth_timeout
            ),
            auth_token_field=str(
                data.get("auth_token_field", default_auth_token_field)
            ),
        )
        endpoints.append(endpoint)

    return endpoints

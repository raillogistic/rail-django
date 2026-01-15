"""Webhook dispatcher for model lifecycle events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import random
import threading
import time
import uuid
from typing import Any, Dict, Iterable, Optional

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.module_loading import import_string

from .config import WebhookEndpoint, WebhookSettings, get_webhook_settings, webhooks_enabled

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional dependency guard
    requests = None

logger = logging.getLogger(__name__)

_EXECUTOR = None
_EXECUTOR_LOCK = threading.Lock()


def dispatch_model_event(instance: Any, event: str, update_fields: Optional[Iterable[str]] = None) -> None:
    settings = get_webhook_settings()
    if not webhooks_enabled(settings):
        return

    event_name = str(event or "").lower()
    if not settings.events.get(event_name, False):
        return

    eligible_endpoints = [
        endpoint
        for endpoint in settings.endpoints
        if endpoint.enabled and _endpoint_allows_model(instance, settings, endpoint)
    ]
    if not eligible_endpoints:
        return

    payload = _build_payload(instance, event_name, settings, update_fields)

    for endpoint in eligible_endpoints:
        _enqueue_delivery(endpoint, payload, settings)


def _endpoint_allows_model(
    instance: Any, settings: WebhookSettings, endpoint: WebhookEndpoint
) -> bool:
    model_label = _get_model_label_lower(instance)
    app_label = _get_app_label(instance)

    allowlist = _get_allowlist(settings.include_models, endpoint.include_models)
    if allowlist is not None:
        if not allowlist or not _matches_any(allowlist, model_label, app_label):
            return False

    blocklist = _merge_blocklist(settings.exclude_models, endpoint.exclude_models)
    if blocklist and _matches_any(blocklist, model_label, app_label):
        return False

    return True


def _matches_any(selectors: Iterable[str], model_label: str, app_label: str) -> bool:
    for selector in selectors:
        if _selector_matches(selector, model_label, app_label):
            return True
    return False


def _get_allowlist(
    global_list: Iterable[str], endpoint_list: Iterable[str]
) -> Optional[Iterable[str]]:
    global_set = {item for item in global_list if item}
    endpoint_set = {item for item in endpoint_list if item}
    if global_set or endpoint_set:
        if global_set and endpoint_set:
            return sorted(global_set.intersection(endpoint_set))
        if endpoint_set:
            return sorted(endpoint_set)
        return sorted(global_set)
    return None


def _merge_blocklist(
    global_list: Iterable[str], endpoint_list: Iterable[str]
) -> Iterable[str]:
    merged = {item for item in global_list if item}
    merged.update({item for item in endpoint_list if item})
    return sorted(merged)


def _selector_matches(selector: str, model_label: str, app_label: str) -> bool:
    if selector == "*":
        return True
    if "." in selector:
        return selector == model_label
    return selector == app_label


def _build_payload(
    instance: Any,
    event: str,
    settings: WebhookSettings,
    update_fields: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    model = instance.__class__
    timestamp = timezone.now()
    model_label = model._meta.label
    model_label_lower = model._meta.label_lower

    payload: dict[str, Any] = {
        "event_id": uuid.uuid4().hex,
        "event_type": event,
        "event_source": "model",
        "timestamp": timestamp.isoformat(),
        "model": model_label,
        "model_label": model_label_lower,
        "app_label": model._meta.app_label,
        "model_name": model._meta.model_name,
        "pk": getattr(instance, "pk", None),
        "data": _serialize_instance(instance, settings, model_label_lower),
    }

    if update_fields:
        payload["update_fields"] = sorted({str(field) for field in update_fields if field})

    return payload


def _serialize_instance(
    instance: Any,
    settings: WebhookSettings,
    model_label_lower: str,
) -> dict[str, Any]:
    model = instance.__class__
    fields = list(getattr(model._meta, "concrete_fields", []))
    include_fields = set(settings.include_fields.get(model_label_lower, []))
    exclude_fields = set(settings.exclude_fields.get(model_label_lower, []))
    redact_fields = set(settings.redact_fields)
    redact_fields.update(settings.redact_fields_by_model.get(model_label_lower, []))
    redaction_mask = settings.redaction_mask

    payload: dict[str, Any] = {}
    for field in fields:
        field_names = {field.name, getattr(field, "attname", field.name)}
        field_names_lower = {name.lower() for name in field_names}

        if include_fields and not field_names_lower.intersection(include_fields):
            continue
        if exclude_fields and field_names_lower.intersection(exclude_fields):
            continue

        key = _select_field_key(field)
        value = field.value_from_object(instance)

        if redact_fields and field_names_lower.intersection(redact_fields):
            payload[key] = redaction_mask
            continue

        payload[key] = _coerce_value(value)

    return payload


def _select_field_key(field: Any) -> str:
    if getattr(field, "is_relation", False) and (
        getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False)
    ):
        return getattr(field, "attname", field.name)
    return field.name


def _coerce_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()
    if hasattr(value, "url"):
        try:
            return value.url
        except Exception:
            pass
    if hasattr(value, "name"):
        try:
            name = value.name
            if name:
                return name
        except Exception:
            pass
    return value


def _enqueue_delivery(
    endpoint: WebhookEndpoint, payload: dict[str, Any], settings: WebhookSettings
) -> None:
    backend = (settings.async_backend or "thread").lower()
    if backend == "sync":
        _deliver_payload(endpoint, payload, settings)
        return

    if backend != "thread":
        handler = _resolve_async_handler(settings)
        if handler is not None:
            try:
                handler(endpoint, payload, settings)
                return
            except Exception as exc:
                logger.warning(
                    "Webhook async handler failed for '%s': %s", endpoint.name, exc
                )
        else:
            logger.warning(
                "Webhook async backend '%s' unavailable; falling back to thread",
                backend,
            )

    executor = _get_executor(settings)
    if executor is None:
        _deliver_payload(endpoint, payload, settings)
        return
    executor.submit(_deliver_payload, endpoint, payload, settings)


def _resolve_async_handler(settings: WebhookSettings):
    task_path = settings.async_task_path
    if not task_path:
        return None
    try:
        return import_string(task_path)
    except Exception as exc:
        logger.warning("Failed to import webhook async handler '%s': %s", task_path, exc)
        return None


def _get_executor(settings: WebhookSettings):
    global _EXECUTOR
    if _EXECUTOR is not None:
        return _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is not None:
            return _EXECUTOR
        try:
            from concurrent.futures import ThreadPoolExecutor

            _EXECUTOR = ThreadPoolExecutor(max_workers=settings.max_workers or 1)
        except Exception as exc:
            logger.warning("Failed to start webhook executor: %s", exc)
            _EXECUTOR = None
    return _EXECUTOR


def _deliver_payload(
    endpoint: WebhookEndpoint, payload: dict[str, Any], settings: WebhookSettings
) -> None:
    if requests is None:
        logger.warning("requests is unavailable; skipping webhook delivery")
        return

    payload_json = _encode_payload(payload)
    headers = _build_headers(endpoint, payload, payload_json)
    timeout = endpoint.timeout_seconds or settings.timeout_seconds

    attempt = 0
    max_attempts = max(1, settings.max_retries + 1)

    while attempt < max_attempts:
        attempt += 1
        try:
            response = requests.post(
                endpoint.url,
                data=payload_json,
                headers=headers,
                timeout=timeout,
            )
            if response.ok:
                return

            if _should_retry(response.status_code, settings) and attempt < max_attempts:
                _sleep_before_retry(attempt, settings)
                continue

            logger.warning(
                "Webhook delivery failed for '%s' (status %s)",
                endpoint.name,
                response.status_code,
            )
            return
        except Exception as exc:
            if attempt < max_attempts:
                _sleep_before_retry(attempt, settings)
                continue
            logger.warning(
                "Webhook delivery failed for '%s' after %s attempts: %s",
                endpoint.name,
                attempt,
                exc,
            )


def _encode_payload(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, cls=DjangoJSONEncoder)
    except TypeError:
        sanitized = _stringify_payload(payload)
        return json.dumps(sanitized, cls=DjangoJSONEncoder)


def _stringify_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _stringify_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stringify_payload(item) for item in value]
    try:
        json.dumps(value, cls=DjangoJSONEncoder)
        return value
    except TypeError:
        return str(value)


def _build_headers(
    endpoint: WebhookEndpoint, payload: dict[str, Any], payload_json: str
) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    headers.update(endpoint.headers)

    event_name = payload.get("event_type")
    if endpoint.event_header and event_name:
        headers[endpoint.event_header] = str(event_name)
    if endpoint.id_header and payload.get("event_id"):
        headers[endpoint.id_header] = str(payload.get("event_id"))

    secret = endpoint.signing_secret
    if secret:
        signature = _sign_payload(secret, payload_json, endpoint.signature_prefix)
        headers[endpoint.signing_header] = signature

    token = _get_auth_token(endpoint, payload, payload_json)
    if token:
        header_name = endpoint.auth_header or "Authorization"
        scheme = endpoint.auth_scheme or ""
        if scheme:
            headers[header_name] = f"{scheme} {token}"
        else:
            headers[header_name] = token

    return headers


def _sign_payload(secret: str, payload_json: str, prefix: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{prefix}{digest}"


def _get_auth_token(
    endpoint: WebhookEndpoint, payload: dict[str, Any], payload_json: str
) -> Optional[str]:
    if not endpoint.auth_token_path:
        return None
    try:
        provider = import_string(endpoint.auth_token_path)
    except Exception as exc:
        logger.warning("Webhook auth provider import failed: %s", exc)
        return None
    try:
        token = _invoke_auth_provider(provider, endpoint, payload, payload_json)
    except Exception as exc:
        logger.warning("Webhook auth provider failed for '%s': %s", endpoint.name, exc)
        return None
    if not token:
        return None
    return str(token)


def _invoke_auth_provider(provider, endpoint, payload, payload_json):
    try:
        return provider(endpoint, payload, payload_json)
    except TypeError:
        try:
            return provider(endpoint, payload)
        except TypeError:
            try:
                return provider(endpoint)
            except TypeError:
                return provider()


def _should_retry(status_code: int, settings: WebhookSettings) -> bool:
    if not settings.retry_statuses:
        return status_code >= 500
    return status_code in settings.retry_statuses


def _sleep_before_retry(attempt: int, settings: WebhookSettings) -> None:
    base = settings.retry_backoff_seconds
    factor = settings.retry_backoff_factor
    jitter = settings.retry_jitter_seconds

    sleep_seconds = max(0.0, base * (factor ** max(attempt - 1, 0)))
    if jitter:
        sleep_seconds += random.uniform(0, jitter)

    if sleep_seconds:
        time.sleep(sleep_seconds)


def _get_model_label_lower(instance: Any) -> str:
    return str(instance.__class__._meta.label_lower)


def _get_app_label(instance: Any) -> str:
    return str(instance.__class__._meta.app_label)

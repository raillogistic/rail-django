# Webhooks

This document describes the full webhook implementation for Rail Django.

## Overview

Webhook delivery is triggered by Django model lifecycle events:

- `created`: model `post_save` when `created=True`
- `updated`: model `post_save` when `created=False`
- `deleted`: model `post_delete`

Events are dispatched after the DB transaction commits via
`transaction.on_commit`. Raw saves (`raw=True`) are ignored.

## Payload

Every webhook request is a JSON payload with this structure:

```json
{
  "event_id": "9b1b2c...",
  "event_type": "created",
  "event_source": "model",
  "timestamp": "2026-01-13T20:10:01.123456+00:00",
  "model": "shop.Order",
  "model_label": "shop.order",
  "app_label": "shop",
  "model_name": "order",
  "pk": 42,
  "data": {
    "id": 42,
    "status": "paid",
    "total": "129.00"
  },
  "update_fields": ["status", "total"]
}
```

Notes:

- `update_fields` is present only for update operations when provided by Django.
- `data` is built from model concrete fields (no reverse relations).
- For FK/one-to-one fields, the `attname` (e.g. `customer_id`) is used.
- Bytes are decoded to UTF-8 (fallback to hex). File fields use `url` or `name`.

## Model filtering

Filtering happens at two levels:

1. Global allow/block lists.
2. Per-endpoint allow/block lists.

Selectors accept:

- `app.Model` (full label)
- `app` (app label)
- `*` (match all)

Rules:

- If both global and endpoint allowlists are set, the effective allowlist is
  the intersection.
- Blocklists are merged (union).
- Filters are case-insensitive (normalized to lowercase).

## Field filtering and redaction

Field filters are per model:

- `include_fields`: allowlist of field names
- `exclude_fields`: blocklist of field names
- `redact_fields`: either a list (global) or a dict with per-model entries

Matching is case-insensitive and uses both field name and `attname` for checks.
Redacted values are replaced with `redaction_mask`.

Example:

```python
RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": {
        "include_fields": {"shop.order": ["id", "status", "total"]},
        "exclude_fields": {"shop.order": ["internal_note"]},
        "redact_fields": ["email", "token"],
    }
}
```

## Endpoint configuration

Endpoints are configured under `webhook_settings.endpoints`. Each endpoint may
override global defaults:

- `name`: identifier for logging.
- `url`: target URL.
- `enabled`: endpoint toggle.
- `headers`: extra headers for delivery.
- `timeout_seconds`: HTTP timeout.
- `include_models` / `exclude_models`: per-endpoint model routing.
- `signing_secret`, `signing_header`, `signature_prefix`: HMAC signing.
- `event_header`, `id_header`: headers for event name and id.
- `auth_token_path`, `auth_header`, `auth_scheme`: token provider settings.
- `auth_url`, `auth_payload`, `auth_headers`, `auth_timeout_seconds`,
  `auth_token_field`: parameters for built-in token fetcher.

## Signing

If `signing_secret` is set, the payload is signed using HMAC SHA256 and the
signature is sent in `signing_header` (default `X-Rail-Signature`) with the
prefix defined by `signature_prefix` (default `sha256=`).

## Authentication tokens

If `auth_token_path` is set, the provider is called before delivery and the
token is injected into `auth_header` (default `Authorization`) with
`auth_scheme` (default `Bearer`).

Provider call signature:

```
provider(endpoint, payload, payload_json)
```

Providers may accept fewer args; the dispatcher retries with shorter
signatures.

Built-in helper:

- `rail_django.webhooks.auth.fetch_auth_token`

It calls `endpoint.auth_url` with `auth_payload` and returns
`auth_token_field` from the JSON response.

## Async delivery

Delivery is async by default using a thread pool.

Options:

- `async_backend = "thread"`: in-process thread pool
- `async_backend = "sync"`: send synchronously in the request thread
- `async_backend = "custom"`: call `async_task_path` to enqueue delivery

`async_task_path` should point to a callable:

```
def enqueue_webhook(endpoint, payload, settings) -> None:
    ...
```

## Retries

Retries are in-process only (no persistence). After all attempts, the event is
logged and dropped.

Settings:

- `max_retries`: number of retries (default 3)
- `retry_statuses`: status codes that trigger retry
- `retry_backoff_seconds`: base delay
- `retry_backoff_factor`: exponential factor
- `retry_jitter_seconds`: random jitter

## Configuration sources

Settings are merged in this order:

1. `RAIL_DJANGO_GRAPHQL["webhook_settings"]`
2. `RAIL_DJANGO_WEBHOOKS` (optional override, used by project template)
3. `rail_django.defaults.LIBRARY_DEFAULTS["webhook_settings"]`

Project template:

- `root/webhooks.py` defines `RAIL_DJANGO_WEBHOOKS`
- `root/settings/base.py` wires it into `webhook_settings`

## Examples

Per-endpoint routing:

```python
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    "endpoints": [
        {
            "name": "orders",
            "url": "https://example.com/webhooks/orders",
            "include_models": ["shop.Order"],
        },
        {
            "name": "customers",
            "url": "https://example.com/webhooks/customers",
            "include_models": ["crm.Customer"],
        },
    ],
}
```

Token helper (built-in provider):

```python
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    "endpoints": [
        {
            "name": "orders",
            "url": "https://example.com/webhooks/orders",
            "include_models": ["shop.Order"],
            "auth_token_path": "rail_django.webhooks.auth.fetch_auth_token",
            "auth_url": "https://example.com/oauth/token",
            "auth_payload": {"client_id": "id", "client_secret": "secret"},
            "auth_token_field": "access_token",
        },
    ],
}
```

## Failure behavior

If an endpoint is down or times out, delivery retries according to the retry
settings. After final failure, the event is logged and dropped.

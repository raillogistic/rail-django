"""Helpers for webhook authentication."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import WebhookEndpoint

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional dependency guard
    requests = None

logger = logging.getLogger(__name__)


def fetch_auth_token(
    endpoint: WebhookEndpoint, payload: Any, payload_json: str
) -> Optional[str]:
    """Fetch a bearer token from an auth endpoint defined on the webhook endpoint."""
    if requests is None:
        logger.warning("requests is unavailable; cannot fetch webhook auth token")
        return None
    if not endpoint.auth_url:
        return None

    try:
        response = requests.post(
            endpoint.auth_url,
            json=endpoint.auth_payload or {},
            headers=endpoint.auth_headers or {},
            timeout=endpoint.auth_timeout_seconds or endpoint.timeout_seconds,
        )
    except Exception as exc:
        logger.warning("Webhook auth request failed for '%s': %s", endpoint.name, exc)
        return None

    if not response.ok:
        logger.warning(
            "Webhook auth request failed for '%s' (status %s)",
            endpoint.name,
            response.status_code,
        )
        return None

    try:
        data = response.json()
    except ValueError:
        logger.warning("Webhook auth response is not JSON for '%s'", endpoint.name)
        return None

    token_field = endpoint.auth_token_field or "access_token"
    token = data.get(token_field)
    if not token:
        logger.warning("Webhook auth token missing '%s' for '%s'", token_field, endpoint.name)
        return None
    return str(token)

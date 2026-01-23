"""
Unit tests for webhook configuration and payload building.
"""

import pytest
from django.test import override_settings

from test_app.models import Client

from rail_django.webhooks.config import WebhookEndpoint, get_webhook_settings
from rail_django.webhooks.dispatcher import _build_headers, _build_payload, dispatch_model_event

pytestmark = pytest.mark.unit


def token_provider(endpoint, payload, payload_json):
    return "token-123"


def test_webhook_settings_external_override():
    with override_settings(
        RAIL_DJANGO_GRAPHQL={"webhook_settings": {"enabled": False}},
        RAIL_DJANGO_WEBHOOKS={
            "enabled": True,
            "endpoints": [{"url": "https://example.com/webhooks"}],
        },
    ):
        settings = get_webhook_settings()
        assert settings.enabled is True
        assert settings.endpoints
        assert settings.endpoints[0].url == "https://example.com/webhooks"


def test_webhook_payload_filters_and_redacts_fields():
    with override_settings(
        RAIL_DJANGO_GRAPHQL={
            "webhook_settings": {
                "enabled": True,
                "endpoints": [{"url": "https://example.com/webhooks"}],
                "include_fields": {"test_app.client": ["name", "email"]},
                "exclude_fields": {"test_app.client": ["email"]},
                "redact_fields": ["name"],
            }
        }
    ):
        settings = get_webhook_settings()
        instance = Client(name="Acme", email="acme@example.com")
        payload = _build_payload(instance, "created", settings)

        data = payload["data"]
        assert data["name"] == settings.redaction_mask
        assert "email" not in data


def test_webhook_endpoint_filters_by_model():
    with override_settings(
        RAIL_DJANGO_GRAPHQL={
            "webhook_settings": {
                "enabled": True,
                "endpoints": [
                    {
                        "name": "clients",
                        "url": "https://example.com/clients",
                        "include_models": ["test_app.Client"],
                    },
                    {
                        "name": "posts",
                        "url": "https://example.com/posts",
                        "include_models": ["test_app.Post"],
                    },
                ],
            }
        }
    ):
        instance = Client(name="Acme", email="acme@example.com")
        delivered = []

        def _capture(endpoint, payload, settings):
            delivered.append(endpoint.name)

        from unittest.mock import patch

        with patch("rail_django.webhooks.dispatcher._enqueue_delivery", _capture):
            dispatch_model_event(instance, "created", update_fields=None)

        assert delivered == ["clients"]


def test_webhook_auth_token_provider_sets_header():
    endpoint = WebhookEndpoint(
        name="auth",
        url="https://example.com/webhooks",
        auth_token_path="tests.unit.test_webhooks.token_provider",
        auth_header="Authorization",
        auth_scheme="Bearer",
    )
    payload = {"event_type": "created", "event_id": "1"}
    payload_json = "{}"
    headers = _build_headers(endpoint, payload, payload_json)
    assert headers["Authorization"] == "Bearer token-123"


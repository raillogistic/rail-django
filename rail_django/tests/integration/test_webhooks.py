"""
Integration tests for webhook signal delivery.
"""

import json
from unittest.mock import patch

import pytest
from django.test import override_settings

from test_app.models import Client

from rail_django.webhooks import dispatcher
from rail_django.webhooks.signals import ensure_webhook_signals

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_webhook_fires_on_model_create():
    if dispatcher.requests is None:
        pytest.skip("requests is unavailable")

    settings = {
        "webhook_settings": {
            "enabled": True,
            "endpoints": [{"url": "https://example.com/webhooks"}],
            "async_backend": "sync",
            "include_models": ["test_app.Client"],
        }
    }

    with override_settings(RAIL_DJANGO_GRAPHQL=settings):
        with patch(
            "rail_django.webhooks.signals.transaction.on_commit",
            side_effect=lambda func: func(),
        ):
            with patch("rail_django.webhooks.dispatcher.requests.post") as post:
                post.return_value.ok = True
                ensure_webhook_signals()
                Client.objects.create(name="Acme", email="acme@example.com")

                assert post.called
                payload_json = post.call_args.kwargs["data"]
                payload = json.loads(payload_json)
                assert payload["event_type"] == "created"
                assert payload["model_label"] == "test_app.client"


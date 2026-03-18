"""Unit tests for security signal wiring during app startup."""

from importlib import import_module
from unittest.mock import Mock, patch

import pytest

from rail_django.security.apps import SecurityConfig

pytestmark = pytest.mark.unit


def test_security_app_ready_connects_permission_cache_signals(monkeypatch):
    connect_mock = Mock()
    monkeypatch.setattr(
        "rail_django.security.signals.connect_permission_cache_signals",
        connect_mock,
    )

    with patch("rail_django.security.apps.post_migrate.connect") as post_migrate_connect:
        config = SecurityConfig("rail_django.security", import_module("rail_django.security"))
        config.ready()

    connect_mock.assert_called_once()
    post_migrate_connect.assert_called_once()
    _, kwargs = post_migrate_connect.call_args
    assert "sender" not in kwargs
    assert kwargs["dispatch_uid"] == "rail_django.security.sync_roles_to_groups"

import importlib

import pytest

from rail_django.config.defaults import LIBRARY_DEFAULTS
import rail_django.config.framework_settings as framework_settings

pytestmark = pytest.mark.unit


def _reload_framework_settings(monkeypatch, env):
    for key in (
        "DJANGO_ALLOWED_HOSTS",
        "CORS_ALLOWED_ORIGINS",
        "CORS_ALLOW_ALL_ORIGINS",
        "RAIL_MAX_FILTER_DEPTH",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(framework_settings)


def test_allowed_hosts_trimmed(monkeypatch):
    module = _reload_framework_settings(
        monkeypatch, {"DJANGO_ALLOWED_HOSTS": "example.com, www.example.com, ,"}
    )
    assert module.ALLOWED_HOSTS == ["example.com", "www.example.com"]


def test_cors_allowed_origins_trimmed(monkeypatch):
    module = _reload_framework_settings(
        monkeypatch,
        {"CORS_ALLOWED_ORIGINS": "https://a.com, https://b.com, ,"},
    )
    assert module.CORS_ALLOWED_ORIGINS == ["https://a.com", "https://b.com"]


def test_invalid_rail_max_filter_depth_does_not_override(monkeypatch):
    module = _reload_framework_settings(
        monkeypatch, {"RAIL_MAX_FILTER_DEPTH": "not-a-number"}
    )
    assert (
        module.RAIL_DJANGO_GRAPHQL["filtering_settings"]["max_filter_depth"]
        == LIBRARY_DEFAULTS["filtering_settings"]["max_filter_depth"]
    )


def test_valid_rail_max_filter_depth_overrides(monkeypatch):
    module = _reload_framework_settings(monkeypatch, {"RAIL_MAX_FILTER_DEPTH": "12"})
    assert module.RAIL_DJANGO_GRAPHQL["filtering_settings"]["max_filter_depth"] == 12

import pytest
from django.test import override_settings

from rail_django.extensions.form.config import get_form_settings
from rail_django.extensions.form.utils import cache as form_cache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clear_form_settings_cache():
    get_form_settings.cache_clear()
    yield
    get_form_settings.cache_clear()


@override_settings(RAIL_DJANGO_FORM={"enable_cache": False})
def test_set_cached_config_is_noop_when_form_cache_disabled(monkeypatch):
    captured: list[tuple[str, object, int | None]] = []

    def _fake_cache_set(key, value, timeout=None):
        captured.append((key, value, timeout))

    monkeypatch.setattr(form_cache.cache, "set", _fake_cache_set)
    form_cache.set_cached_config("test_app", "Product", {"id": "x"})
    assert captured == []


@override_settings(RAIL_DJANGO_FORM={"cache_ttl_seconds": 123})
def test_set_cached_config_uses_form_cache_ttl(monkeypatch):
    captured: list[tuple[str, object, int | None]] = []

    def _fake_cache_set(key, value, timeout=None):
        captured.append((key, value, timeout))

    monkeypatch.setattr(form_cache.cache, "set", _fake_cache_set)
    form_cache.set_cached_config("test_app", "Product", {"id": "x"})

    assert captured
    assert any(timeout == 123 for _, _, timeout in captured)


def test_invalidate_form_cache_rotates_model_version():
    version_before = form_cache.get_form_version("test_app", "Product")
    version_after = form_cache.invalidate_form_cache("test_app", "Product")

    assert version_after
    assert version_after != version_before
    assert form_cache.get_form_version("test_app", "Product") == version_after

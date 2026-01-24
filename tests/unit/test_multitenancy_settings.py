import pytest

from rail_django.extensions.multitenancy import settings as mt_settings

pytestmark = pytest.mark.unit


def test_multitenancy_coerce_bool_strings(monkeypatch):
    values = {
        "multitenancy_settings.enabled": "0",
        "multitenancy_settings.allow_cross_tenant_superuser": "False",
        "multitenancy_settings.require_tenant": "no",
        "multitenancy_settings.tenant_subdomain": "yes",
        "multitenancy_settings.reject_mismatched_tenant_input": "off",
    }

    def fake_get_setting(key, default, schema_name=None):
        return values.get(key, default)

    monkeypatch.setattr(mt_settings, "get_setting", fake_get_setting)
    result = mt_settings.get_multitenancy_settings()

    assert result.enabled is False
    assert result.allow_cross_tenant_superuser is False
    assert result.require_tenant is False
    assert result.tenant_subdomain is True
    assert result.reject_mismatched_tenant_input is False

import pytest

from rail_django.extensions.multitenancy.resolver import resolve_tenant_id
from rail_django.generators.types import TypeGenerator
from rail_django.testing import build_request, override_rail_settings
from tests.models import TenantProject

pytestmark = pytest.mark.unit


def test_resolve_tenant_id_is_schema_aware():
    schema_settings = {
        "schema_a": {"multitenancy_settings": {"tenant_header": "X-Tenant-A"}},
        "schema_b": {"multitenancy_settings": {"tenant_header": "X-Tenant-B"}},
    }
    with override_rail_settings(schema_settings=schema_settings):
        request = build_request(
            schema_name="schema_a",
            headers={"X-Tenant-A": "tenant-a", "X-Tenant-B": "tenant-b"},
            data={},
        )
        tenant_a = resolve_tenant_id(request, schema_name="schema_a")
        tenant_b = resolve_tenant_id(request, schema_name="schema_b")

        assert tenant_a == "tenant-a"
        assert tenant_b == "tenant-b"


def test_type_generator_tenant_filter_uses_settings():
    schema_settings = {
        "tenant_test": {
            "multitenancy_settings": {
                "enabled": True,
                "tenant_header": "X-Tenant-ID",
                "default_tenant_field": "organization",
                "require_tenant": True,
            }
        }
    }
    with override_rail_settings(schema_settings=schema_settings):
        context = build_request(
            schema_name="tenant_test",
            headers={"X-Tenant-ID": "123"},
            data={},
        )
        type_gen = TypeGenerator(schema_name="tenant_test")
        tenant_field, tenant_id, settings = type_gen._get_tenant_filter_for_model(
            context, TenantProject
        )

        assert tenant_field == "organization"
        assert tenant_id == "123"
        assert settings is not None and settings.enabled is True

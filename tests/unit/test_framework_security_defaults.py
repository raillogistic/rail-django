import pytest

from rail_django.config import framework_settings


@pytest.mark.unit
def test_schema_api_requires_auth_by_default():
    assert framework_settings.GRAPHQL_SCHEMA_API_AUTH_REQUIRED is True


@pytest.mark.unit
def test_abac_defaults_to_deny_when_no_policy_matches():
    assert (
        framework_settings.RAIL_DJANGO_GRAPHQL["security_settings"]["abac_default_effect"]
        == "deny"
    )

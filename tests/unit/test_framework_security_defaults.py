import pytest

from rail_django.config import framework_settings


@pytest.mark.unit
def test_schema_api_requires_auth_by_default():
    assert framework_settings.GRAPHQL_SCHEMA_API_AUTH_REQUIRED is True

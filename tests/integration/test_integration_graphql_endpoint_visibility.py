import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.http import JsonResponse
from django.test import override_settings

from tests.integration.test_helpers_graphql_endpoint import graphql_test_endpoint

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _enabled_schema(name: str = "gql") -> SimpleNamespace:
    return SimpleNamespace(name=name, enabled=True, settings={})


@override_settings(
    ROOT_URLCONF="rail_django.urls",
    ENVIRONMENT="development",
    RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=True,
)
@patch("graphene_django.views.GraphQLView.dispatch")
@patch("rail_django.core.registry.schema_registry")
def test_test_endpoint_available_in_non_production(
    mock_registry,
    mock_graphql_dispatch,
    client,
):
    mock_registry.discover_schemas.return_value = None
    mock_registry.get_schema.return_value = _enabled_schema()
    mock_graphql_dispatch.return_value = JsonResponse({"data": {"ok": True}})

    response = client.post(
        graphql_test_endpoint(),
        data=json.dumps({"query": "query { __typename }"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert json.loads(response.content.decode("utf-8")) == {"data": {"ok": True}}


@override_settings(
    ROOT_URLCONF="rail_django.urls",
    ENVIRONMENT="production",
    RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=None,
)
@patch("rail_django.core.registry.schema_registry")
def test_test_endpoint_blocked_in_production(mock_registry, client):
    response = client.post(
        graphql_test_endpoint(),
        data=json.dumps({"query": "query { __typename }"}),
        content_type="application/json",
    )

    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 404
    assert payload["errors"][0]["extensions"]["code"] == "SCHEMA_NOT_FOUND"
    mock_registry.get_schema.assert_not_called()

import json

import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_detail_v2_relations", apps=["test_app"])
    User = get_user_model()
    admin = User.objects.create_superuser(
        username="detail_relations_admin",
        email="detail_relations_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema,
        schema_name="test_detail_v2_relations",
        user=admin,
    )


def test_detail_contract_maps_reverse_relations_with_pagination_metadata(gql_client):
    query = """
    query($input: DetailContractInputType!) {
      modelDetailContract(input: $input) {
        ok
        reason
        contract {
          relationDataSources {
            id
            relationName
            direction
            mode
            loadStrategy
            queryName
            lookupField
            pagination
            cacheKey
          }
        }
      }
    }
    """

    payload = gql_client.execute(
        query,
        variables={
            "input": {
                "app": "test_app",
                "model": "Product",
            }
        },
    )

    assert payload.get("errors") is None
    result = payload["data"]["modelDetailContract"]
    assert result["ok"] is True

    sources = result["contract"]["relationDataSources"]
    reverse_source = next(
        (source for source in sources if source["relationName"] == "orderItems"),
        None,
    )
    assert reverse_source is not None
    assert reverse_source["direction"] == "REVERSE"
    assert reverse_source["mode"] == "TABLE"
    assert reverse_source["loadStrategy"] == "LAZY"
    assert reverse_source["queryName"].endswith("Page")
    assert reverse_source["cacheKey"] == "test_app.Product:orderItems"

    pagination = reverse_source["pagination"]
    if isinstance(pagination, str):
        pagination = json.loads(pagination)
    assert isinstance(pagination, dict)
    assert pagination["page_arg"] == "page"
    assert pagination["per_page_arg"] == "perPage"
    assert pagination["default_per_page"] == 20
    assert pagination["cycle_guard_enabled"] is True
    assert pagination["max_depth"] >= 1

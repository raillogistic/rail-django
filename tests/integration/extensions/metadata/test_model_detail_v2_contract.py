import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_detail_v2_contract", apps=["test_app"])
    User = get_user_model()
    admin = User.objects.create_superuser(
        username="detail_contract_admin",
        email="detail_contract_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema,
        schema_name="test_detail_v2_contract",
        user=admin,
    )


def test_detail_contract_includes_readable_scalar_and_forward_fields(gql_client):
    query = """
    query($input: DetailContractInputType!) {
      modelDetailContract(input: $input) {
        ok
        reason
        contract {
          modelName
          defaultIncludeFields
          layoutNodes {
            id
            type
            fields {
              name
              title
              type
            }
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

    contract = result["contract"]
    include_fields = set(contract["defaultIncludeFields"])
    assert "name" in include_fields
    assert "price" in include_fields
    assert "category" in include_fields

    section_nodes = [
        node for node in contract["layoutNodes"] if node["type"] == "SECTION"
    ]
    assert section_nodes
    section_field_names = {
        field["name"] for field in section_nodes[0]["fields"] if field.get("name")
    }
    assert "name" in section_field_names
    assert "price" in section_field_names
    assert "category" in section_field_names


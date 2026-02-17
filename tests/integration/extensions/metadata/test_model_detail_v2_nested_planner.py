import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(
        schema_name="test_detail_v2_nested_planner",
        apps=["test_app"],
    )
    User = get_user_model()
    admin = User.objects.create_superuser(
        username="detail_nested_admin",
        email="detail_nested_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema,
        schema_name="test_detail_v2_nested_planner",
        user=admin,
    )


QUERY = """
query($input: DetailContractInputType!) {
  modelDetailContract(input: $input) {
    ok
    reason
    contract {
      layoutNodes {
        id
        type
        relationSourceId
        fields {
          name
        }
      }
      relationDataSources {
        relationName
        mode
        loadStrategy
      }
    }
  }
}
"""


def test_nested_to_one_relation_builds_section_node(gql_client):
    payload = gql_client.execute(
        QUERY,
        variables={
            "input": {
                "app": "test_app",
                "model": "Product",
                "nested": ["category"],
            }
        },
    )

    assert payload.get("errors") is None
    result = payload["data"]["modelDetailContract"]
    assert result["ok"] is True

    contract = result["contract"]
    relation_section = next(
        (
            node
            for node in contract["layoutNodes"]
            if node.get("relationSourceId") == "category"
        ),
        None,
    )
    assert relation_section is not None
    assert relation_section["type"] == "SECTION"
    assert any(field["name"] == "name" for field in relation_section["fields"])

    order_items_source = next(
        (
            source
            for source in contract["relationDataSources"]
            if source["relationName"] == "orderItems"
        ),
        None,
    )
    assert order_items_source is not None
    assert order_items_source["mode"] == "SECTION"
    assert order_items_source["loadStrategy"] == "PRIMARY"


def test_nested_to_many_relation_builds_table_node(gql_client):
    payload = gql_client.execute(
        QUERY,
        variables={
            "input": {
                "app": "test_app",
                "model": "Product",
                "nested": ["order_items"],
            }
        },
    )

    assert payload.get("errors") is None
    result = payload["data"]["modelDetailContract"]
    assert result["ok"] is True

    contract = result["contract"]
    relation_table = next(
        (
            node
            for node in contract["layoutNodes"]
            if node.get("relationSourceId") == "orderItems"
        ),
        None,
    )
    assert relation_table is not None
    assert relation_table["type"] == "TABLE"
    assert relation_table["fields"]
    table_field_names = {field["name"] for field in relation_table["fields"]}
    assert "id" in table_field_names
    assert "product" not in table_field_names
    assert "quantity" in table_field_names

    order_items_source = next(
        (
            source
            for source in contract["relationDataSources"]
            if source["relationName"] == "orderItems"
        ),
        None,
    )
    assert order_items_source is not None
    assert order_items_source["mode"] == "TABLE"
    assert order_items_source["loadStrategy"] == "LAZY"


def test_nested_supports_multiple_relations(gql_client):
    payload = gql_client.execute(
        QUERY,
        variables={
            "input": {
                "app": "test_app",
                "model": "Product",
                "nested": ["category", "orderItems"],
            }
        },
    )

    assert payload.get("errors") is None
    result = payload["data"]["modelDetailContract"]
    assert result["ok"] is True

    contract = result["contract"]
    default_section = next(
        (node for node in contract["layoutNodes"] if node.get("id") == "default-section"),
        None,
    )
    assert default_section is not None
    default_names = {field["name"] for field in default_section["fields"]}
    assert "category" not in default_names
    assert "orderItems" not in default_names

    category_node = next(
        (
            node
            for node in contract["layoutNodes"]
            if node.get("relationSourceId") == "category"
        ),
        None,
    )
    assert category_node is not None
    assert category_node["type"] == "SECTION"

    order_items_node = next(
        (
            node
            for node in contract["layoutNodes"]
            if node.get("relationSourceId") == "orderItems"
        ),
        None,
    )
    assert order_items_node is not None
    assert order_items_node["type"] == "TABLE"
    assert order_items_node["fields"]
    order_items_field_names = {field["name"] for field in order_items_node["fields"]}
    assert "product" not in order_items_field_names
    assert "quantity" in order_items_field_names

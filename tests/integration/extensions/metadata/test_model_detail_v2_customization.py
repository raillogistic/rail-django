import pytest
from django.contrib.auth import get_user_model
import json

from rail_django.testing import RailGraphQLTestClient, build_schema
from rail_django.extensions.metadata.utils import invalidate_metadata_cache
from rail_django.extensions.metadata.extractor import ModelSchemaExtractor

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_detail_v2_customization", apps=["test_app"])
    User = get_user_model()
    admin = User.objects.create_superuser(
        username="detail_customization_admin",
        email="detail_customization_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema,
        schema_name="test_detail_v2_customization",
        user=admin,
    )


def test_detail_contract_propagates_group_ordering_and_template_hints(gql_client, monkeypatch):
    patched_groups = [
        {
            "key": "identity",
            "label": "Identity",
            "description": "Identity fields",
            "fields": ["name"],
            "collapsed": False,
        },
        {
            "key": "pricing",
            "label": "Pricing",
            "description": "Pricing fields",
            "fields": ["price", "costPrice"],
            "collapsed": True,
        },
    ]
    monkeypatch.setattr(
        ModelSchemaExtractor,
        "_extract_field_groups",
        lambda _self, _model, _meta: patched_groups,
    )
    invalidate_metadata_cache("test_app", "Product")

    try:
        query = """
        query($input: DetailContractInputType!) {
          modelDetailContract(input: $input) {
            ok
            reason
            contract {
              layoutNodes {
                id
                title
                order
                visibilityRule
                fields {
                  name
                }
              }
            }
          }
        }
        """
        payload = gql_client.execute(
            query,
            variables={"input": {"app": "test_app", "model": "Product"}},
        )

        assert payload.get("errors") is None
        result = payload["data"]["modelDetailContract"]
        assert result["ok"] is True

        nodes = result["contract"]["layoutNodes"]
        assert len(nodes) >= 2
        assert nodes[0]["id"] == "identity"
        assert nodes[0]["order"] == 0
        assert nodes[0]["title"] == "Identity"
        assert any(field["name"] == "name" for field in nodes[0]["fields"])
        node0_visibility = nodes[0]["visibilityRule"]
        if isinstance(node0_visibility, str):
            node0_visibility = json.loads(node0_visibility)
        assert node0_visibility["group"]["description"] == "Identity fields"

        assert nodes[1]["id"] == "pricing"
        assert nodes[1]["order"] == 1
        assert nodes[1]["title"] == "Pricing"
        assert any(field["name"] == "price" for field in nodes[1]["fields"])
        node1_visibility = nodes[1]["visibilityRule"]
        if isinstance(node1_visibility, str):
            node1_visibility = json.loads(node1_visibility)
        assert node1_visibility["group"]["collapsed"] is True
        assert "templates" in node1_visibility
    finally:
        invalidate_metadata_cache("test_app", "Product")

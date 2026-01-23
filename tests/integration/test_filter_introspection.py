"""
Integration tests for filter introspection.
"""

import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    """GraphQL client."""
    harness = build_schema(schema_name="test_introspection", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="intro_admin",
        email="intro@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(harness.schema, schema_name="test_introspection", user=user)


class TestFilterIntrospection:
    """Test filter introspection API."""

    def test_filter_schema_query(self, gql_client):
        """Test filterSchema query returns correct metadata."""
        query = """
        query {
            filterSchema(model: "Product") {
                model
                supportsFts
                supportsAggregation
                fields {
                    fieldName
                    fieldLabel
                    options {
                        name
                        lookupExpr
                        filterType
                    }
                }
                presets {
                    name
                    filterJson
                }
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        schema = result["data"]["filterSchema"]
        
        assert schema["model"] == "Product"
        # Check for expected fields
        field_names = [f["fieldName"] for f in schema["fields"]]
        assert "name" in field_names
        assert "price" in field_names
        # assert "cost_price" in field_names # Added in previous phase
        
        # Check options for a field (e.g. name string field)
        name_field = next(f for f in schema["fields"] if f["fieldName"] == "name")
        ops = [o["name"] for o in name_field["options"]]
        assert "eq" in ops
        assert "icontains" in ops
        
        # Check presets (defined in previous phase)
        preset_names = [p["name"] for p in schema["presets"]]
        assert "expensive" in preset_names
        assert "out_of_stock" in preset_names

    def test_filter_schema_unknown_model(self, gql_client):
        """Test query with unknown model returns null."""
        query = """
        query {
            filterSchema(model: "UnknownModel") {
                model
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        assert result["data"]["filterSchema"] is None


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
        """Test metadata extension filterSchema query returns correct metadata."""
        query = """
        query {
            filterSchema(app: "test_app", model: "Product") {
                name
                fieldName
                fieldLabel
                options {
                    name
                    lookup
                }
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        schema = result["data"]["filterSchema"]

        assert isinstance(schema, list)
        assert len(schema) > 0

        # Check for expected fields
        field_names = [f["fieldName"] for f in schema]
        assert "name" in field_names
        assert "price" in field_names

        name_field = next(f for f in schema if f["fieldName"] == "name")
        ops = [o["name"] for o in name_field["options"]]
        assert "eq" in ops
        assert "icontains" in ops

    def test_filter_schema_unknown_model(self, gql_client):
        """Test query with unknown model returns an empty list."""
        query = """
        query {
            filterSchema(app: "test_app", model: "UnknownModel") {
                name
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        assert result["data"]["filterSchema"] == []


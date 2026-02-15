"""
Integration tests for filter introspection.
"""

import pytest
from django.contrib.auth import get_user_model

from rail_django.generators.filters import clear_filter_caches
from rail_django.generators.introspector import ModelIntrospector
from rail_django.testing import RailGraphQLTestClient, build_schema
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


def test_property_filters_follow_property_return_type():
    original_property = getattr(Product, "name_bucket", None)

    @property
    def name_bucket(self) -> str:
        value = str(getattr(self, "name", "") or "").lower()
        return "premium" if value.startswith("pro") else "standard"

    try:
        Product.name_bucket = name_bucket
        if hasattr(Product, "_graphql_meta_instance"):
            del Product._graphql_meta_instance
        ModelIntrospector.clear_cache()
        clear_filter_caches(schema_name="test_property_filters")

        harness = build_schema(schema_name="test_property_filters", apps=["test_app"])
        User = get_user_model()
        user = User.objects.create_superuser(
            username="property_filter_admin",
            email="property-filter@example.com",
            password="pass12345",
        )
        gql_client = RailGraphQLTestClient(
            harness.schema,
            schema_name="test_property_filters",
            user=user,
        )

        Product.objects.create(name="Pro Desk", price=100.00, cost_price=80.00)
        Product.objects.create(name="Basic Chair", price=50.00, cost_price=20.00)

        schema_query = """
        query {
            filterSchema(app: "test_app", model: "Product") {
                fieldName
                baseType
                options {
                    name
                }
            }
        }
        """
        schema_result = gql_client.execute(schema_query)
        assert schema_result.get("errors") is None
        schema_rows = schema_result["data"]["filterSchema"]
        property_filter = next(
            (row for row in schema_rows if row["fieldName"] == "name_bucket"),
            None,
        )
        assert property_filter is not None
        assert property_filter["baseType"] == "String"
        property_ops = {option["name"] for option in property_filter["options"]}
        assert {"eq", "icontains"}.issubset(property_ops)

        filter_query = """
        query($where: ProductWhereInput) {
            productList(where: $where) {
                name
            }
        }
        """
        filter_result = gql_client.execute(
            filter_query,
            variables={"where": {"nameBucket": {"eq": "premium"}}},
        )
        assert filter_result.get("errors") is None
        names = [row["name"] for row in filter_result["data"]["productList"]]
        assert names == ["Pro Desk"]
    finally:
        if original_property is None and hasattr(Product, "name_bucket"):
            delattr(Product, "name_bucket")
        elif original_property is not None:
            Product.name_bucket = original_property

        if hasattr(Product, "_graphql_meta_instance"):
            del Product._graphql_meta_instance
        ModelIntrospector.clear_cache()
        clear_filter_caches(schema_name="test_property_filters")


import pytest
from django.contrib.auth import get_user_model

from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta
from rail_django.extensions.metadata.utils import invalidate_metadata_cache
from rail_django.generators.introspector import ModelIntrospector
from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_model_schema", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="metadata_admin",
        email="metadata@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema, schema_name="test_model_schema", user=user
    )


def test_model_schema_query_is_available_by_default(gql_client):
    query = """
    query {
      modelSchema(app: "test_app", model: "Product") {
        app
        model
        metadataVersion
        fields {
          name
        }
      }
    }
    """

    result = gql_client.execute(query)

    assert result.get("errors") is None
    data = result["data"]["modelSchema"]
    assert data["app"] == "test_app"
    assert data["model"] == "Product"
    assert isinstance(data["metadataVersion"], str)
    assert any(field["name"] == "name" for field in data["fields"])


def test_model_schema_exposes_model_properties(gql_client):
    original_property = getattr(Product, "inventory_value", None)
    original_meta = getattr(Product, "GraphQLMeta", None)

    class PatchedMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(read_only=["date_creation"])

    @property
    def inventory_value(self) -> int:
        return int((self.price or 0) * (self.inventory_count or 0))

    Product.GraphQLMeta = PatchedMeta
    Product.inventory_value = inventory_value
    if hasattr(Product, "_graphql_meta_instance"):
        del Product._graphql_meta_instance
    ModelIntrospector.clear_cache()
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      modelSchema(app: "test_app", model: "Product") {
        fields {
          fieldName
          fieldType
          isComputed
          writable
          graphqlType
        }
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None

        fields = result["data"]["modelSchema"]["fields"]
        property_field = next(
            (field for field in fields if field["fieldName"] == "inventory_value"),
            None,
        )

        assert property_field is not None
        assert property_field["fieldType"] == "Property"
        assert property_field["isComputed"] is True
        assert property_field["writable"] is False
        assert property_field["graphqlType"] == "Int"
    finally:
        if original_meta is None and hasattr(Product, "GraphQLMeta"):
            delattr(Product, "GraphQLMeta")
        elif original_meta is not None:
            Product.GraphQLMeta = original_meta

        if original_property is None and hasattr(Product, "inventory_value"):
            delattr(Product, "inventory_value")
        elif original_property is not None:
            Product.inventory_value = original_property

        if hasattr(Product, "_graphql_meta_instance"):
            del Product._graphql_meta_instance
        ModelIntrospector.clear_cache()
        invalidate_metadata_cache(app="test_app", model="Product")

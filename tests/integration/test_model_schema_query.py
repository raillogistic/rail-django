import pytest
from django.contrib.auth import get_user_model

from rail_django.core.decorators import mutation
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta
from rail_django.extensions.templating import model_pdf_template
from rail_django.extensions.templating.registry import (
    _register_model_templates,
    template_registry,
)
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


def test_custom_mutation_query_returns_custom_mutation_metadata(gql_client):
    original_method = getattr(Product, "mark_featured", None)

    @mutation(description="Mark this product as featured")
    def mark_featured(self, note: str = "manual") -> bool:
        return True

    Product.mark_featured = mark_featured
    if hasattr(Product, "_graphql_meta_instance"):
        del Product._graphql_meta_instance
    ModelIntrospector.clear_cache()
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      customMutation(app: "test_app", model: "Product", functionName: "mark_featured") {
        name
        operation
        methodName
        mutationType
        description
        inputFields {
          fieldName
          required
          graphqlType
        }
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None
        payload = result["data"]["customMutation"]
        assert payload is not None
        assert payload["operation"] == "custom"
        assert payload["methodName"] == "mark_featured"
        assert payload["mutationType"] == "custom"
        assert payload["description"] == "Mark this product as featured"
        assert any(field["fieldName"] == "note" for field in payload["inputFields"])
    finally:
        if original_method is None and hasattr(Product, "mark_featured"):
            delattr(Product, "mark_featured")
        elif original_method is not None:
            Product.mark_featured = original_method

        if hasattr(Product, "_graphql_meta_instance"):
            del Product._graphql_meta_instance
        ModelIntrospector.clear_cache()
        invalidate_metadata_cache(app="test_app", model="Product")


def test_model_template_query_returns_model_template_metadata(gql_client):
    original_method = getattr(Product, "print_summary", None)
    original_templates = template_registry.all()

    @model_pdf_template(content="pdf/product_summary.html")
    def print_summary(self):
        return {"id": self.pk}

    Product.print_summary = print_summary
    _register_model_templates(Product)
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      modelTemplate(app: "test_app", model: "Product", functionName: "print_summary") {
        key
        templateType
        title
        endpoint
        urlPath
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None
        payload = result["data"]["modelTemplate"]
        assert payload is not None
        assert payload["templateType"] == "pdf"
        assert payload["urlPath"].endswith("/print_summary")
        assert payload["endpoint"].endswith(
            "/templates/test_app/product/print_summary/<pk>/"
        )
    finally:
        if original_method is None and hasattr(Product, "print_summary"):
            delattr(Product, "print_summary")
        elif original_method is not None:
            Product.print_summary = original_method

        template_registry._templates = dict(original_templates)
        invalidate_metadata_cache(app="test_app", model="Product")

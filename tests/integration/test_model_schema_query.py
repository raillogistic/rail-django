import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from rail_django.core.decorators import custom_mutation_name, mutation
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
    @custom_mutation_name("publishProduct")
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
        assert payload["name"] == "publishProduct"
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


def test_custom_mutations_query_returns_all_custom_mutation_metadata(gql_client):
    original_featured = getattr(Product, "mark_featured", None)
    original_archived = getattr(Product, "archive_product", None)

    @mutation(description="Mark this product as featured")
    def mark_featured(self, note: str = "manual") -> bool:
        return True

    @mutation(description="Archive this product")
    def archive_product(self, reason: str = "cleanup") -> bool:
        return True

    Product.mark_featured = mark_featured
    Product.archive_product = archive_product
    if hasattr(Product, "_graphql_meta_instance"):
        del Product._graphql_meta_instance
    ModelIntrospector.clear_cache()
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      customMutations(app: "test_app", model: "Product") {
        name
        operation
        methodName
        description
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None
        payload = result["data"]["customMutations"]
        method_names = {item["methodName"] for item in payload}
        assert "mark_featured" in method_names
        assert "archive_product" in method_names
        assert all(item["operation"] == "custom" for item in payload)
    finally:
        if original_featured is None and hasattr(Product, "mark_featured"):
            delattr(Product, "mark_featured")
        elif original_featured is not None:
            Product.mark_featured = original_featured

        if original_archived is None and hasattr(Product, "archive_product"):
            delattr(Product, "archive_product")
        elif original_archived is not None:
            Product.archive_product = original_archived

        if hasattr(Product, "_graphql_meta_instance"):
            del Product._graphql_meta_instance
        ModelIntrospector.clear_cache()
        invalidate_metadata_cache(app="test_app", model="Product")


def test_custom_mutations_query_filters_out_denied_mutations(gql_client):
    original_public = getattr(Product, "mark_featured", None)
    original_admin = getattr(Product, "admin_publish", None)

    @mutation(description="Mark this product as featured")
    def mark_featured(self, note: str = "manual") -> bool:
        return True

    @mutation(
        description="Publish product to the storefront",
        permissions=["test_app.change_product"],
    )
    def admin_publish(self) -> bool:
        return True

    Product.mark_featured = mark_featured
    Product.admin_publish = admin_publish
    if hasattr(Product, "_graphql_meta_instance"):
        del Product._graphql_meta_instance
    ModelIntrospector.clear_cache()
    invalidate_metadata_cache(app="test_app", model="Product")

    User = get_user_model()
    limited_user = User.objects.create_user(
        username="metadata_limited",
        password="pass12345",
    )
    limited_user.user_permissions.add(
        Permission.objects.get(
            codename="view_product",
            content_type__app_label="test_app",
        )
    )

    query = """
    query {
      customMutations(app: "test_app", model: "Product") {
        methodName
      }
      gated: customMutation(
        app: "test_app"
        model: "Product"
        functionName: "admin_publish"
      ) {
        methodName
      }
    }
    """

    try:
        result = gql_client.execute(query, user=limited_user)
        assert result.get("errors") is None
        payload = result["data"]["customMutations"]
        method_names = {item["methodName"] for item in payload}
        assert "mark_featured" in method_names
        assert "admin_publish" not in method_names
        assert result["data"]["gated"] is None
    finally:
        if original_public is None and hasattr(Product, "mark_featured"):
            delattr(Product, "mark_featured")
        elif original_public is not None:
            Product.mark_featured = original_public

        if original_admin is None and hasattr(Product, "admin_publish"):
            delattr(Product, "admin_publish")
        elif original_admin is not None:
            Product.admin_publish = original_admin

        if hasattr(Product, "_graphql_meta_instance"):
            del Product._graphql_meta_instance
        ModelIntrospector.clear_cache()
        invalidate_metadata_cache(app="test_app", model="Product")


def test_custom_mutations_query_ignores_undecorated_helper_methods(gql_client):
    original_helper = getattr(Product, "recalculate_inventory", None)
    original_action = getattr(Product, "mark_featured", None)

    def recalculate_inventory(self, factor: int = 1) -> int:
        return factor

    @mutation(description="Mark this product as featured")
    def mark_featured(self, note: str = "manual") -> bool:
        return True

    Product.recalculate_inventory = recalculate_inventory
    Product.mark_featured = mark_featured
    if hasattr(Product, "_graphql_meta_instance"):
        del Product._graphql_meta_instance
    ModelIntrospector.clear_cache()
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      customMutations(app: "test_app", model: "Product") {
        name
        methodName
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None
        payload = result["data"]["customMutations"]
        method_names = {item["methodName"] for item in payload}
        assert "mark_featured" in method_names
        assert "recalculate_inventory" not in method_names
    finally:
        if original_helper is None and hasattr(Product, "recalculate_inventory"):
            delattr(Product, "recalculate_inventory")
        elif original_helper is not None:
            Product.recalculate_inventory = original_helper

        if original_action is None and hasattr(Product, "mark_featured"):
            delattr(Product, "mark_featured")
        elif original_action is not None:
            Product.mark_featured = original_action

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


def test_model_templates_query_returns_all_model_template_metadata(gql_client):
    original_summary = getattr(Product, "print_summary", None)
    original_label = getattr(Product, "print_label", None)
    original_templates = template_registry.all()

    @model_pdf_template(content="pdf/product_summary.html")
    def print_summary(self):
        return {"id": self.pk}

    @model_pdf_template(content="pdf/product_label.html")
    def print_label(self):
        return {"id": self.pk}

    Product.print_summary = print_summary
    Product.print_label = print_label
    _register_model_templates(Product)
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      modelTemplates(app: "test_app", model: "Product") {
        key
        templateType
        endpoint
        urlPath
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None
        payload = result["data"]["modelTemplates"]
        url_paths = {item["urlPath"] for item in payload}
        assert any(path.endswith("/print_summary") for path in url_paths)
        assert any(path.endswith("/print_label") for path in url_paths)
        assert all(item["templateType"] == "pdf" for item in payload)
    finally:
        if original_summary is None and hasattr(Product, "print_summary"):
            delattr(Product, "print_summary")
        elif original_summary is not None:
            Product.print_summary = original_summary

        if original_label is None and hasattr(Product, "print_label"):
            delattr(Product, "print_label")
        elif original_label is not None:
            Product.print_label = original_label

        template_registry._templates = dict(original_templates)
        invalidate_metadata_cache(app="test_app", model="Product")

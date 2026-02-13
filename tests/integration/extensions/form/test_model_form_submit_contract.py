import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def generated_contract_enabled():
    previous = getattr(Product.GraphQLMeta, "custom_metadata", None)
    Product.GraphQLMeta.custom_metadata = {"generated_form": {"enabled": True}}
    if hasattr(Product, "_graphql_meta_instance"):
        delattr(Product, "_graphql_meta_instance")
    yield
    if previous is None and hasattr(Product.GraphQLMeta, "custom_metadata"):
        delattr(Product.GraphQLMeta, "custom_metadata")
    else:
        Product.GraphQLMeta.custom_metadata = previous
    if hasattr(Product, "_graphql_meta_instance"):
        delattr(Product, "_graphql_meta_instance")


@pytest.fixture
def gql_client(generated_contract_enabled):
    harness = build_schema(schema_name="test_model_form_submit_contract", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="model_form_submit_admin",
        email="model_form_submit_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema, schema_name="test_model_form_submit_contract", user=user
    )


def test_model_form_submit_contract_query_returns_required_bindings(gql_client):
    query = """
    query {
      submit: modelFormSubmitContract(appLabel: "test_app", modelName: "Product") {
        appLabel
        modelName
        bindings {
          createOperation
          updateOperation
          defaultIdentifierKey
          formErrorKey
        }
      }
    }
    """
    result = gql_client.execute(query)
    assert result.get("errors") is None

    payload = result["data"]["submit"]
    assert payload["appLabel"] == "test_app"
    assert payload["modelName"] == "Product"
    assert payload["bindings"]["createOperation"] == "createProduct"
    assert payload["bindings"]["updateOperation"] == "updateProduct"
    assert payload["bindings"]["defaultIdentifierKey"] == "objectId"
    assert payload["bindings"]["formErrorKey"] == "__all__"

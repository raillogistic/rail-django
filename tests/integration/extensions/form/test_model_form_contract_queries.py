import json

import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Category, Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _decode_json(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


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
    harness = build_schema(schema_name="test_form_contract_queries", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="form_contract_admin",
        email="form_contract_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema, schema_name="test_form_contract_queries", user=user
    )


def test_model_form_contract_and_pages_queries(gql_client):
    query = """
    query($models: [ModelRefInput!]) {
      contract: modelFormContract(
        appLabel: "test_app"
        modelName: "Product"
        mode: CREATE
      ) {
        id
        appLabel
        modelName
        mutationBindings {
          createOperation
          updateOperation
        }
      }
      page: modelFormContractPages(page: 1, perPage: 10, models: $models) {
        page
        perPage
        total
        results {
          id
          modelName
        }
      }
    }
    """
    variables = {"models": [{"appLabel": "test_app", "modelName": "Product"}]}
    result = gql_client.execute(query, variables=variables)
    assert result.get("errors") is None

    contract = result["data"]["contract"]
    assert contract["appLabel"] == "test_app"
    assert contract["modelName"] == "Product"
    assert contract["mutationBindings"]["createOperation"] == "createProduct"

    page = result["data"]["page"]
    assert page["page"] == 1
    assert page["perPage"] == 10
    assert page["total"] >= 1
    assert any(item["modelName"] == "Product" for item in page["results"])


def test_model_form_initial_data_supports_nested_and_runtime_overrides(gql_client):
    category = Category.objects.create(name="Software", description="Apps")
    product = Product.objects.create(
        name="Starter",
        price=10,
        inventory_count=2,
        category=category,
    )

    query = """
    query($id: ID!, $runtimeOverrides: [ModelFormRuntimeOverrideInput!]) {
      payload: modelFormInitialData(
        appLabel: "test_app"
        modelName: "Product"
        objectId: $id
        includeNested: true
        runtimeOverrides: $runtimeOverrides
      ) {
        appLabel
        modelName
        objectId
        values
      }
    }
    """
    variables = {
        "id": str(product.pk),
        "runtimeOverrides": [
            {"path": "inventoryCount", "value": "99", "action": "REPLACE"}
        ],
    }
    result = gql_client.execute(query, variables=variables)
    assert result.get("errors") is None

    payload = result["data"]["payload"]
    values = _decode_json(payload["values"])
    assert values["inventoryCount"] == 99
    assert isinstance(values["category"], dict)
    assert str(values["category"]["id"]) == str(category.pk)

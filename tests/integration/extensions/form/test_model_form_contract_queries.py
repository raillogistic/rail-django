import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Category, OrderItem, Product

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
        relations {
          name
          path
        }
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
    order_items_relation = next(
        (item for item in contract["relations"] if item["path"] == "order_items"),
        None,
    )
    assert order_items_relation is not None
    assert order_items_relation["name"] == "orderItems"

    page = result["data"]["page"]
    assert page["page"] == 1
    assert page["perPage"] == 10
    assert page["total"] >= 1
    assert any(item["modelName"] == "Product" for item in page["results"])


def test_model_form_contract_resolves_operation_permissions_for_limited_user(gql_client):
    User = get_user_model()
    limited_user = User.objects.create_user(
        username="form_contract_limited",
        password="pass12345",
    )
    limited_user.user_permissions.add(
        Permission.objects.get(
            codename="view_product",
            content_type__app_label="test_app",
        ),
    )

    query = """
    query {
      contract: modelFormContract(
        appLabel: "test_app"
        modelName: "Product"
        mode: UPDATE
      ) {
        permissions {
          canView
          canCreate
          canUpdate
          canDelete
          update {
            allowed
            requiredPermissions
            requiresAuthentication
            reason
          }
          fieldPermissions {
            field
            canRead
            canWrite
            visibility
          }
        }
      }
    }
    """
    result = gql_client.execute(query, user=limited_user)
    assert result.get("errors") is None

    permissions = result["data"]["contract"]["permissions"]
    assert permissions["canView"] is True
    assert permissions["canCreate"] is False
    assert permissions["canUpdate"] is False
    assert permissions["canDelete"] is False
    assert permissions["update"]["allowed"] is False
    assert "test_app.change_product" in permissions["update"]["requiredPermissions"]
    assert permissions["update"]["requiresAuthentication"] is True
    assert permissions["update"]["reason"]
    assert permissions["fieldPermissions"], "Expected field-level permissions snapshot."


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


def test_model_form_initial_data_supports_nested_fields_filter(gql_client):
    category = Category.objects.create(name="Hardware", description="Devices")
    product = Product.objects.create(
        name="Starter",
        price=10,
        inventory_count=2,
        category=category,
    )
    order_item = OrderItem.objects.create(product=product, quantity=3, unit_price=10)

    query = """
    query($id: ID!, $nestedFields: [String!]) {
      payload: modelFormInitialData(
        appLabel: "test_app"
        modelName: "Product"
        objectId: $id
        includeNested: true
        nestedFields: $nestedFields
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
        "nestedFields": ["category"],
    }
    result = gql_client.execute(query, variables=variables)
    assert result.get("errors") is None

    payload = result["data"]["payload"]
    values = _decode_json(payload["values"])

    assert isinstance(values["category"], dict)
    assert str(values["category"]["id"]) == str(category.pk)

    assert isinstance(values["orderItems"], list)
    assert len(values["orderItems"]) == 1
    assert values["orderItems"][0] == order_item.pk

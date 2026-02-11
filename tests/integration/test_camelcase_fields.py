import pytest
from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product, Category

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

from django.contrib.auth import get_user_model


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_camel", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="camel_admin",
        email="admin@example.com",
        password="pass",
    )
    return RailGraphQLTestClient(harness.schema, schema_name="test_camel", user=user)


def test_camelcase_field_selection(gql_client):
    """Test that snake_case model fields are exposed as camelCase."""
    cat = Category.objects.create(name="Test Cat")
    Product.objects.create(name="Test Product", price=10.0, category=cat)

    query = """
    query {
        productList {
            dateCreation
            costPrice
        }
    }
    """
    result = gql_client.execute(query)
    assert result.get("errors") is None
    item = result["data"]["productList"][0]
    assert "dateCreation" in item
    assert "costPrice" in item


def test_camelcase_filter_input(gql_client):
    """Test that filter inputs use camelCase field names."""
    cat = Category.objects.create(name="Test Cat")
    Product.objects.create(name="P1", price=10.0, cost_price=5.0, category=cat)
    Product.objects.create(name="P2", price=20.0, cost_price=15.0, category=cat)

    query = """
    query($where: ProductWhereInput) {
        productList(where: $where) {
            name
        }
    }
    """

    # Filter by costPrice (camelCase of cost_price)
    variables = {"where": {"costPrice": {"gt": 10.0}}}

    result = gql_client.execute(query, variables=variables)
    assert result.get("errors") is None
    items = result["data"]["productList"]
    assert len(items) == 1
    assert items[0]["name"] == "P2"


def test_camelcase_filter_operators(gql_client):
    """Test that filter operators use camelCase (startsWith)."""
    cat = Category.objects.create(name="Alpha")
    Category.objects.create(name="Beta")

    query = """
    query($where: CategoryWhereInput) {
        categoryList(where: $where) {
            name
        }
    }
    """

    variables = {"where": {"name": {"startsWith": "Al"}}}

    result = gql_client.execute(query, variables=variables)
    assert result.get("errors") is None
    items = result["data"]["categoryList"]
    assert len(items) == 1
    assert items[0]["name"] == "Alpha"



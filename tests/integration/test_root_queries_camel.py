import pytest
from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

from django.contrib.auth import get_user_model


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_root_camel", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="root_admin",
        email="root@example.com",
        password="pass",
    )
    return RailGraphQLTestClient(
        harness.schema, schema_name="test_root_camel", user=user
    )


def test_root_query_camelcase(gql_client):
    """Test that root queries use camelCase (product vs products, products)."""
    Product.objects.create(name="P1", price=10.0)

    # Single query: product (was product or product__objects)
    # List query: products (was products or products__objects)
    # Alias: products (was all_products)

    query = """
    query {
        products {
            name
        }
        products {
            name
        }
    }
    """

    result = gql_client.execute(query)
    assert result.get("errors") is None
    assert len(result["data"]["products"]) == 1
    assert len(result["data"]["products"]) == 1


def test_root_query_pagination_camelcase(gql_client):
    """Test that pagination queries use camelCase (productsPages)."""
    Product.objects.create(name="P1", price=10.0)

    # Was products_pages
    query = """
    query {
        productPages {
            items {
                name
            }
        }
    }
    """

    result = gql_client.execute(query)
    assert result.get("errors") is None
    assert len(result["data"]["productPages"]["items"]) == 1

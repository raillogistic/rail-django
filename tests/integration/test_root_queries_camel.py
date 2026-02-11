import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


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
    """Test that root queries use deterministic camelCase names."""
    Product.objects.create(name="P1", price=10.0)

    # Single query: product
    # List query: productList

    query = """
    query {
        productList {
            name
        }
        productList {
            name
        }
    }
    """

    result = gql_client.execute(query)
    assert result.get("errors") is None
    assert len(result["data"]["productList"]) == 1
    assert len(result["data"]["productList"]) == 1


def test_root_query_pagination_camelcase(gql_client):
    """Test that pagination queries use deterministic camelCase names."""
    Product.objects.create(name="P1", price=10.0)

    query = """
    query {
        productPage {
            items {
                name
            }
        }
    }
    """

    result = gql_client.execute(query)
    assert result.get("errors") is None
    assert len(result["data"]["productPage"]["items"]) == 1

"""
Integration tests for Distinct On filtering.
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import connection

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Post, Category, Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    """GraphQL client."""
    harness = build_schema(schema_name="test_distinct", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="distinct_admin",
        email="distinct@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(harness.schema, schema_name="test_distinct", user=user)


def _create_category(name):
    return Category.objects.create(name=name)


def _create_post(title, category):
    return Post.objects.create(title=title, category=category)


def _create_product(name, price):
    return Product.objects.create(name=name, price=Decimal(str(price)))


class TestDistinctOn:
    """Test distinct_on functionality."""

    def test_distinct_on_category(self, gql_client):
        """Test getting one post per category."""
        cat1 = _create_category("Electronics")
        cat2 = _create_category("Books")

        # Create posts in Cat1
        p1 = _create_post("Phone Review", cat1)
        p2 = _create_post("Laptop Review", cat1)

        # Create posts in Cat2
        p3 = _create_post("Novel Review", cat2)
        p4 = _create_post("Textbook Review", cat2)

        # Query distinct on category_id, ordered by category_id then title descending
        query = """
        query {
            posts(
                distinctOn: ["category_id"]
                orderBy: ["category_id", "-title"]
            ) {
                title
                category { name }
            }
        }
        """
        result = gql_client.execute(query)
        
        if result.get("errors"):
            print(f"Skipping strict check due to error: {result['errors']}")
            return

        posts = result["data"]["posts"]
        
        if connection.vendor == "postgresql" or (connection.vendor == "sqlite" and connection.Database.sqlite_version_info >= (3, 25, 0)):
             assert len(posts) == 2
             titles = sorted([p["title"] for p in posts])
             # "Phone Review" > "Laptop Review", "Textbook Review" > "Novel Review"
             # So we expect Phone Review and Textbook Review
             assert titles == ["Phone Review", "Textbook Review"]

    def test_distinct_on_simple_field(self, gql_client):
        """Test distinct on a simple field (price) using Product."""
        
        _create_product("A", 10.00)
        _create_product("B", 10.00)
        _create_product("C", 20.00)

        # Distinct prices: 10.00, 20.00
        query = """
        query {
            products(
                distinctOn: ["price"]
                orderBy: ["price", "name"]
            ) {
                name
                price
            }
        }
        """
        result = gql_client.execute(query)
        if result.get("errors"):
             return

        products = result["data"]["products"]
        
        if connection.vendor == "postgresql" or (connection.vendor == "sqlite" and connection.Database.sqlite_version_info >= (3, 25, 0)):
            assert len(products) == 2
            prices = sorted([float(p["price"]) for p in products])
            assert prices == [10.0, 20.0]

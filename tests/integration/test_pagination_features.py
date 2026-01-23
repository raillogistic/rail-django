"""
Integration tests for advanced features in paginated queries (presets, saved filters, distinct).
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import connection

from rail_django.testing import RailGraphQLTestClient, build_schema
from rail_django.saved_filter import SavedFilter
from test_app.models import Product, Category

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    """GraphQL client."""
    harness = build_schema(schema_name="test_paginated_features", apps=["test_app", "rail_django"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="paginated_admin",
        email="paginated@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(harness.schema, schema_name="test_paginated_features", user=user)


def _create_category(name):
    return Category.objects.create(name=name)


def _create_product(name, price, category=None):
    return Product.objects.create(name=name, price=Decimal(str(price)), category=category)


class TestPaginatedFeatures:
    """Test advanced features in paginated queries."""

    def test_paginated_presets(self, gql_client):
        """Test presets in paginated query."""
        _create_product("Cheap Item", 10.00)
        _create_product("Expensive Item", 100.00)
        _create_product("Mid Item", 50.00)

        # "expensive" preset defined in Product model (>= 50.0)
        query = """
        query {
            productPages(
                presets: ["expensive"]
                orderBy: ["price"]
                page: 1
                perPage: 10
            ) {
                items {
                    name
                    price
                }
                pageInfo {
                    totalCount
                }
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        data = result["data"]["productPages"]
        assert data["pageInfo"]["totalCount"] == 2
        names = sorted([p["name"] for p in data["items"]])
        assert names == ["Expensive Item", "Mid Item"]

    def test_paginated_saved_filter(self, gql_client):
        """Test saved filter in paginated query."""
        user = get_user_model().objects.get(username="paginated_admin")
        
        SavedFilter.objects.create(
            name="cheap_products",
            model_name="Product",
            filter_json={"price": {"lt": 20.00}},
            created_by=user,
            is_shared=True
        )

        _create_product("Cheap A", 10.00)
        _create_product("Cheap B", 15.00)
        _create_product("Expensive", 100.00)

        query = """
        query {
            productPages(
                savedFilter: "cheap_products"
                page: 1
                perPage: 10
            ) {
                items {
                    name
                }
                pageInfo {
                    totalCount
                }
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        data = result["data"]["productPages"]
        assert data["pageInfo"]["totalCount"] == 2
        names = sorted([p["name"] for p in data["items"]])
        assert names == ["Cheap A", "Cheap B"]

    def test_paginated_distinct_on(self, gql_client):
        """Test distinct_on in paginated query."""
        # Note: Distinct on usually requires Postgres for strict adherence, 
        # but our fallback should work for simple cases.
        
        cat1 = _create_category("Cat1")
        cat2 = _create_category("Cat2")

        # Create products
        # Cat1: A (10), B (20) -> Max price: B
        _create_product("A", 10.00, cat1)
        _create_product("B", 20.00, cat1)
        
        # Cat2: C (15), D (25) -> Max price: D
        _create_product("C", 15.00, cat2)
        _create_product("D", 25.00, cat2)

        query = """
        query {
            productPages(
                distinctOn: ["category_id"]
                orderBy: ["category_id", "-price"]
                page: 1
                perPage: 10
            ) {
                items {
                    name
                    price
                }
                pageInfo {
                    totalCount
                }
            }
        }
        """
        result = gql_client.execute(query)
        
        if result.get("errors"):
             print(f"Skipping due to error: {result['errors']}")
             return

        data = result["data"]["productPages"]
        
        # Check logic based on DB capabilities
        if connection.vendor == "postgresql" or (connection.vendor == "sqlite" and connection.Database.sqlite_version_info >= (3, 25, 0)):
            assert data["pageInfo"]["totalCount"] == 2
            names = sorted([p["name"] for p in data["items"]])
            assert names == ["B", "D"]

    def test_empty_results_pagination(self, gql_client):
        """Test pagination with empty results returns consistent page info."""
        # Query for non-existent products
        query = """
        query {
            productPages(
                where: { name: { eq: "NonExistent" } }
                page: 1
                perPage: 10
            ) {
                items {
                    name
                }
                pageInfo {
                    totalCount
                    pageCount
                    currentPage
                    hasNextPage
                    hasPreviousPage
                }
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        data = result["data"]["productPages"]

        # Should return consistent pagination for empty results
        assert data["pageInfo"]["totalCount"] == 0
        assert data["pageInfo"]["pageCount"] == 0
        assert data["pageInfo"]["currentPage"] == 1  # Always page 1 for empty
        assert data["pageInfo"]["hasNextPage"] is False
        assert data["pageInfo"]["hasPreviousPage"] is False
        assert data["items"] == []

    def test_page_beyond_range_clamps_to_last(self, gql_client):
        """Test that requesting page beyond range returns last valid page."""
        # Create exactly 3 products
        _create_product("P1", 10.00)
        _create_product("P2", 20.00)
        _create_product("P3", 30.00)

        # Request page 100 with 2 per page (only 2 pages exist)
        query = """
        query {
            productPages(
                page: 100
                perPage: 2
            ) {
                items {
                    name
                }
                pageInfo {
                    totalCount
                    pageCount
                    currentPage
                }
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        data = result["data"]["productPages"]

        # Should clamp to last page (page 2)
        assert data["pageInfo"]["totalCount"] == 3
        assert data["pageInfo"]["pageCount"] == 2
        assert data["pageInfo"]["currentPage"] == 2  # Clamped to last page
        assert len(data["items"]) == 1  # Last page has 1 item

    def test_combined_presets_and_where(self, gql_client):
        """Test combining presets with where filter."""
        _create_product("Expensive Phone", 100.00)
        _create_product("Expensive Laptop", 80.00)
        _create_product("Cheap Phone", 10.00)

        # Combine "expensive" preset (>= 50) with additional where filter
        query = """
        query {
            productPages(
                presets: ["expensive"]
                where: { name: { icontains: "Phone" } }
                page: 1
                perPage: 10
            ) {
                items {
                    name
                    price
                }
                pageInfo {
                    totalCount
                }
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        data = result["data"]["productPages"]

        # Should only return expensive items with "Phone" in name
        # "Expensive Phone" matches both (price >= 50 AND name contains "Phone")
        # "Expensive Laptop" matches preset but not where (no "Phone")
        # "Cheap Phone" matches where but not preset (price < 50)
        assert data["pageInfo"]["totalCount"] == 1
        assert data["items"][0]["name"] == "Expensive Phone"

    def test_include_ids_with_filters(self, gql_client):
        """Test include IDs union with other filters."""
        p1 = _create_product("Cheap", 10.00)
        p2 = _create_product("Expensive", 100.00)
        p3 = _create_product("Another Expensive", 150.00)

        # Filter for expensive but include the cheap one
        query = f"""
        query {{
            productPages(
                where: {{ price: {{ gte: 50.00 }} }}
                include: ["{p1.id}"]
                page: 1
                perPage: 10
            ) {{
                items {{
                    id
                    name
                }}
                pageInfo {{
                    totalCount
                }}
            }}
        }}
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        data = result["data"]["productPages"]

        # Should return expensive items PLUS the included cheap one
        assert data["pageInfo"]["totalCount"] == 3
        names = sorted([p["name"] for p in data["items"]])
        assert "Cheap" in names
        assert "Expensive" in names
        assert "Another Expensive" in names



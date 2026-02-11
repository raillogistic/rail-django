"""
Integration tests for saved filters.
"""

import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product
from rail_django.extensions.filters.models import SavedFilter

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    """GraphQL client."""
    harness = build_schema(schema_name="test_saved_filters", apps=["test_app", "rail_django"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="saved_filter_admin",
        email="saved_filter@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(harness.schema, schema_name="test_saved_filters", user=user)


def _create_product(name, price, category=None):
    return Product.objects.create(name=name, price=price)


class TestSavedFilters:
    """Test saved filter functionality."""

    def test_apply_saved_filter_by_name(self, gql_client):
        """Test applying a saved filter by name."""
        user = get_user_model().objects.get(username="saved_filter_admin")
        
        # Create productList
        _create_product("Laptop", 1000.00)
        _create_product("Mouse", 20.00)
        _create_product("Monitor", 200.00)

        # Create saved filter
        SavedFilter.objects.create(
            name="expensive_items",
            model_name="Product",
            filter_json={"price": {"gte": 500.00}},
            created_by=user,
            is_shared=True
        )

        query = """
        query {
            productList(savedFilter: "expensive_items") {
                name
                price
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Laptop"

        # Verify usage count updated
        sf = SavedFilter.objects.get(name="expensive_items")
        assert sf.use_count == 1
        assert sf.last_used_at is not None

    def test_apply_saved_filter_by_id(self, gql_client):
        """Test applying a saved filter by ID."""
        user = get_user_model().objects.get(username="saved_filter_admin")
        
        _create_product("A", 10.00)
        _create_product("B", 20.00)

        sf = SavedFilter.objects.create(
            name="items_b",
            model_name="Product",
            filter_json={"name": {"eq": "B"}},
            created_by=user,
            is_shared=True
        )

        query = f"""
        query {{
            productList(savedFilter: "{sf.id}") {{
                name
            }}
        }}
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "B"

    def test_saved_filter_and_user_filter_merge(self, gql_client):
        """Test merging saved filter with user provided filter."""
        user = get_user_model().objects.get(username="saved_filter_admin")
        
        _create_product("Gaming Laptop", 1500.00)
        _create_product("Office Laptop", 800.00)
        _create_product("Gaming Mouse", 50.00)

        # Saved filter: name contains "Gaming"
        SavedFilter.objects.create(
            name="gaming_gear",
            model_name="Product",
            filter_json={"name": {"icontains": "Gaming"}},
            created_by=user,
            is_shared=True
        )

        # User query: savedFilter="gaming_gear" AND price > 1000
        query = """
        query {
            productList(
                savedFilter: "gaming_gear"
                where: { price: { gt: 1000.00 } }
            ) {
                name
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Gaming Laptop"

    def test_private_filter_visibility(self, gql_client):
        """Test that private filters are only visible to owner."""
        user = get_user_model().objects.get(username="saved_filter_admin")
        other_user = get_user_model().objects.create_user(username="other", password="pw")
        
        _create_product("Secret", 100.00)

        # Create private filter owned by 'other'
        SavedFilter.objects.create(
            name="private_filter",
            model_name="Product",
            filter_json={"name": {"eq": "Secret"}},
            created_by=other_user,
            is_shared=False
        )

        # Admin user tries to use it (should fail/ignore)
        query = """
        query {
            productList(savedFilter: "private_filter") {
                name
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        # Should return all productList because filter was ignored (not found)
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Secret" 
        # Note: In this specific test setup with 1 product, ignoring the filter 
        # also returns the product. Let's make it clearer.
        
        _create_product("Public", 10.00)
        result = gql_client.execute(query)
        productList = result["data"]["productList"]
        # If filter applied, we'd see 1. If ignored (default all), we see 2.
        assert len(productList) == 2



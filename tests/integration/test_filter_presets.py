"""
Integration tests for filter presets.
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    """GraphQL client."""
    harness = build_schema(schema_name="test_presets", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="preset_admin",
        email="preset_admin@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(harness.schema, schema_name="test_presets", user=user)


def _create_product(name, price):
    return Product.objects.create(name=name, price=Decimal(str(price)))


class TestFilterPresets:
    """Test filter presets functionality."""

    def test_single_preset(self, gql_client):
        """Test applying a single preset."""
        _create_product("Cheap Item", 10.00)
        _create_product("Expensive Item", 100.00)

        query = """
        query {
            productList(presets: ["expensive"], orderBy: ["name"]) {
                name
                price
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Expensive Item"

    def test_multiple_presets(self, gql_client):
        """Test combining multiple presets."""
        _create_product("Cheap", 10.00)
        _create_product("Mid", 50.00)
        _create_product("Expensive", 100.00)

        # mid_range is 20-80, expensive is >= 50. Intersection is [50, 80]
        query = """
        query {
            productList(presets: ["mid_range", "expensive"], orderBy: ["name"]) {
                name
                price
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Mid"

    def test_preset_with_user_filters(self, gql_client):
        """Test preset combined with user provided filters."""
        _create_product("Cheap Pro", 10.00)
        _create_product("Expensive Pro", 100.00)
        _create_product("Expensive Basic", 100.00)

        # expensive (>= 50) + name contains "Pro"
        query = """
        query {
            productList(
                presets: ["expensive"]
                where: { name: { icontains: "Pro" } }
                orderBy: ["name"]
            ) {
                name
                price
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Expensive Pro"

    def test_complex_preset(self, gql_client):
        """Test a preset with complex logic (AND/OR)."""
        _create_product("Cheap Pro", 10.00)
        _create_product("Expensive Pro", 120.00)
        _create_product("Expensive Basic", 120.00)

        # complex_preset: name contains "pro" AND price >= 100
        query = """
        query {
            productList(presets: ["complex_preset"], orderBy: ["name"]) {
                name
                price
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Expensive Pro"

    def test_unknown_preset_ignored(self, gql_client):
        """Test that unknown presets are ignored without error."""
        _create_product("Item", 10.00)

        query = """
        query {
            productList(presets: ["non_existent_preset"]) {
                name
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1

    def test_field_ending_in_count(self, gql_client):
        """Test preset on a field ending in _count (regression test)."""
        p1 = _create_product("In Stock", 10.00)
        p1.inventory_count = 10
        p1.save()
        
        p2 = _create_product("Out of Stock", 10.00)
        p2.inventory_count = 0
        p2.save()

        query = """
        query {
            productList(presets: ["out_of_stock"]) {
                name
                inventoryCount
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Out of Stock"




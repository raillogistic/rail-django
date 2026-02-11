"""
Integration tests for computed filters.
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db.models import F, ExpressionWrapper, FloatField

from rail_django.testing import RailGraphQLTestClient, build_schema
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    """GraphQL client."""
    # Dynamically inject computed_filters into Product model for testing
    if not hasattr(Product, "GraphQLMeta"):
         class Meta(RailGraphQLMeta):
             pass
         Product.GraphQLMeta = Meta
    
    Product.GraphQLMeta.computed_filters = {
        "profit": {
            "expression": ExpressionWrapper(
                F("price") - F("cost_price"),
                output_field=FloatField()
            ),
            "filter_type": "float",
            "description": "Profit (price - cost)",
        },
        "markup_pct": {
            "expression": ExpressionWrapper(
                (F("price") - F("cost_price")) / F("cost_price") * 100,
                output_field=FloatField()
            ),
            "filter_type": "float",
            "description": "Markup Percentage",
        }
    }
    # Re-initialize meta to pick up changes (meta instance is cached)
    if hasattr(Product, "_graphql_meta_instance"):
        del Product._graphql_meta_instance

    harness = build_schema(schema_name="test_computed", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="computed_admin",
        email="computed@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(harness.schema, schema_name="test_computed", user=user)


def _create_product(name, price, cost_price):
    p = Product.objects.create(name=name, price=Decimal(str(price)), cost_price=Decimal(str(cost_price)))
    return p


class TestComputedFilters:
    """Test computed filter functionality."""

    def test_computed_filter_simple(self, gql_client):
        """Test filtering by a simple computed field (profit)."""
        _create_product("High Profit", 100.00, 50.00) # Profit 50
        _create_product("Low Profit", 100.00, 90.00)  # Profit 10
        _create_product("Loss", 50.00, 60.00)         # Profit -10

        query = """
        query {
            productList(where: {
                profit: { gte: 20.0 }
            }) {
                name
                price
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "High Profit"

    def test_computed_filter_complex(self, gql_client):
        """Test filtering by a complex expression (markup percentage)."""
        # 50 cost, 100 price -> 100% markup
        _create_product("Double", 100.00, 50.00)
        # 100 cost, 110 price -> 10% markup
        _create_product("TenPercent", 110.00, 100.00) 

        query = """
        query {
            productList(where: {
                markupPct: { gt: 50.0 }
            }) {
                name
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        productList = result["data"]["productList"]
        assert len(productList) == 1
        assert productList[0]["name"] == "Double"

    def test_computed_filter_sorting(self, gql_client):
        """Test sorting by computed field (if supported by property ordering logic)."""
        # Note: Computed filters currently only add annotations for filtering. 
        # To sort by them, they would need to be in `ordering.allowed`.
        # This test just verifies filtering works with standard ordering.
        _create_product("A", 100.00, 50.00) # Profit 50
        
        query = """
        query {
            productList(
                where: { profit: { gt: 0 } }
                orderBy: ["name"]
            ) {
                name
            }
        }
        """
        result = gql_client.execute(query)
        assert result.get("errors") is None
        assert len(result["data"]["productList"]) == 1



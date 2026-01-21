"""
Integration tests for advanced filter features.

Tests Window Functions, Subquery Filters, Conditional Aggregation, and Array Filters
with actual database queries.
"""

import json
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Category, Product, OrderItem

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client_advanced():
    """GraphQL client with all advanced filter features enabled."""
    harness = build_schema(
        schema_name="test_advanced_filters",
        apps=["test_app"],
        settings={
            "filtering_settings": {
                "enable_window_filters": True,
                "enable_subquery_filters": True,
                "enable_conditional_aggregation": True,
                "enable_array_filters": True,
                "enable_field_comparison": True,
                "enable_distinct_count": True,
                "enable_date_trunc_filters": True,
                "enable_extract_date_filters": True,
            },
        },
    )
    User = get_user_model()
    user = User.objects.create_superuser(
        username="advanced_admin",
        email="advanced_admin@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(
        harness.schema, schema_name="test_advanced_filters", user=user
    )


def _create_category(name="General"):
    return Category.objects.create(name=name)


def _create_product(name, price, cost_price=0, category=None, inventory_count=0):
    return Product.objects.create(
        name=name,
        price=Decimal(str(price)),
        cost_price=Decimal(str(cost_price)),
        category=category,
        inventory_count=inventory_count,
    )


def _create_order_item(product, quantity, unit_price):
    return OrderItem.objects.create(
        product=product,
        quantity=quantity,
        unit_price=Decimal(str(unit_price)),
    )


class TestConditionalAggregationFilters:
    """Test conditional aggregation filters with actual queries."""

    def test_filter_by_conditional_count(self, gql_client_advanced):
        """Filter products by conditional count of related order items."""
        # Create products with varying order items
        p1 = _create_product("Product A", 100)
        p2 = _create_product("Product B", 200)
        p3 = _create_product("Product C", 300)

        # P1: 3 high-value items (unit_price >= 50)
        _create_order_item(p1, 1, 60)
        _create_order_item(p1, 2, 70)
        _create_order_item(p1, 1, 80)
        _create_order_item(p1, 1, 10)  # Low value

        # P2: 1 high-value item
        _create_order_item(p2, 1, 55)
        _create_order_item(p2, 1, 20)

        # P3: 0 high-value items
        _create_order_item(p3, 1, 30)
        _create_order_item(p3, 1, 25)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Filter products with at least 2 high-value order items
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "orderItemsCondAgg": {
                        "field": "id",
                        "filter": json.dumps({"unit_price": {"gte": 50}}),
                        "count": {"gte": 2},
                    }
                }
            },
        )

        # Should only include Product A with 3 high-value items
        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Product A" in names
        assert "Product B" not in names
        assert "Product C" not in names


class TestSubqueryFilters:
    """Test subquery filters with actual queries."""

    def test_filter_by_subquery_latest_value(self, gql_client_advanced):
        """Filter products by the max unit price of their order items."""
        p1 = _create_product("Product Alpha", 100)
        p2 = _create_product("Product Beta", 200)
        p3 = _create_product("Product Gamma", 300)

        # Product Alpha: max order item price is 150
        _create_order_item(p1, 1, 50)
        _create_order_item(p1, 1, 150)
        _create_order_item(p1, 1, 100)

        # Product Beta: max order item price is 80
        _create_order_item(p2, 1, 80)
        _create_order_item(p2, 1, 40)

        # Product Gamma: max order item price is 200
        _create_order_item(p3, 1, 200)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Filter products whose highest priced order item exceeds 100
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_subquery": {
                        "relation": "order_items",
                        "orderBy": ["-unit_price"],
                        "field": "unit_price",
                        "gt": 100,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        # Product Alpha (150) and Product Gamma (200) should match
        assert "Product Alpha" in names
        assert "Product Gamma" in names
        assert "Product Beta" not in names


class TestExistsFilters:
    """Test exists filters with actual queries."""

    def test_filter_by_exists(self, gql_client_advanced):
        """Filter products that have at least one order item."""
        p1 = _create_product("Has Orders", 100)
        p2 = _create_product("No Orders", 200)

        _create_order_item(p1, 1, 50)
        _create_order_item(p1, 2, 30)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Filter products that have order items
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_exists": {
                        "relation": "order_items",
                        "exists": True,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Has Orders" in names
        assert "No Orders" not in names

    def test_filter_by_not_exists(self, gql_client_advanced):
        """Filter products that have no order items."""
        p1 = _create_product("Has Items", 100)
        p2 = _create_product("Empty", 200)

        _create_order_item(p1, 1, 50)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Filter products that have NO order items
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_exists": {
                        "relation": "order_items",
                        "exists": False,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Empty" in names
        assert "Has Items" not in names

    def test_filter_by_exists_with_condition(self, gql_client_advanced):
        """Filter products that have high-quantity order items."""
        p1 = _create_product("Bulk Seller", 100)
        p2 = _create_product("Single Units", 200)
        p3 = _create_product("No Sales", 300)

        # Bulk seller has high quantity items
        _create_order_item(p1, 10, 50)
        _create_order_item(p1, 15, 30)

        # Single units only has low quantity items
        _create_order_item(p2, 1, 100)
        _create_order_item(p2, 2, 50)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Filter products that have order items with quantity >= 10
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_exists": {
                        "relation": "order_items",
                        "filter": json.dumps({"quantity": {"gte": 10}}),
                        "exists": True,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Bulk Seller" in names
        assert "Single Units" not in names
        assert "No Sales" not in names


class TestWindowFilters:
    """Test window function filters with actual queries."""

    def test_window_filter_top_n_overall(self, gql_client_advanced):
        """Filter products by their overall rank by price."""
        _create_product("Cheap", 10)
        _create_product("Mid", 50)
        _create_product("Expensive", 100)
        _create_product("Premium", 200)
        _create_product("Luxury", 500)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["-price"]) {
                name
                price
            }
        }
        """

        # Get top 3 most expensive products
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_window": {
                        "function": "RANK",
                        "orderBy": ["-price"],
                        "rank": {"lte": 3},
                    }
                }
            },
        )

        assert result.get("errors") is None
        products = result["data"]["products"]
        names = [p["name"] for p in products]

        # Top 3 by price should be Luxury, Premium, Expensive
        assert "Luxury" in names
        assert "Premium" in names
        assert "Expensive" in names
        assert "Mid" not in names
        assert "Cheap" not in names

    def test_window_filter_top_per_category(self, gql_client_advanced):
        """Filter to get top product per category using window function."""
        cat_electronics = _create_category("Electronics")
        cat_clothing = _create_category("Clothing")

        _create_product("Phone", 500, category=cat_electronics)
        _create_product("Laptop", 1000, category=cat_electronics)
        _create_product("Tablet", 300, category=cat_electronics)

        _create_product("Shirt", 50, category=cat_clothing)
        _create_product("Pants", 80, category=cat_clothing)
        _create_product("Jacket", 150, category=cat_clothing)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["category_id", "-price"]) {
                name
                price
                category {
                    name
                }
            }
        }
        """

        # Get top 1 product per category
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_window": {
                        "function": "ROW_NUMBER",
                        "partitionBy": ["category_id"],
                        "orderBy": ["-price"],
                        "rank": {"eq": 1},
                    }
                }
            },
        )

        assert result.get("errors") is None
        products = result["data"]["products"]
        names = [p["name"] for p in products]

        # Should have Laptop (top Electronics) and Jacket (top Clothing)
        assert "Laptop" in names
        assert "Jacket" in names
        # Should not have lower-ranked products
        assert "Phone" not in names
        assert "Shirt" not in names


class TestCombinedAdvancedFilters:
    """Test combining advanced filters with standard filters."""

    def test_combined_exists_and_standard_filters(self, gql_client_advanced):
        """Combine exists filter with standard price filter."""
        p1 = _create_product("Expensive with Sales", 500)
        p2 = _create_product("Cheap with Sales", 50)
        p3 = _create_product("Expensive no Sales", 600)

        _create_order_item(p1, 1, 100)
        _create_order_item(p2, 1, 20)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
                price
            }
        }
        """

        # Expensive products (>= 200) that have sales
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "price": {"gte": 200},
                    "_exists": {
                        "relation": "order_items",
                        "exists": True,
                    },
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Expensive with Sales" in names
        assert "Cheap with Sales" not in names  # Too cheap
        assert "Expensive no Sales" not in names  # No sales


class TestFieldComparisonFilters:
    """Test F() expression field comparison filters with actual queries."""

    def test_filter_price_greater_than_cost(self, gql_client_advanced):
        """Filter products where price > cost_price (profitable products)."""
        _create_product("Profitable", 100, cost_price=50)  # profit margin
        _create_product("Break Even", 100, cost_price=100)  # no margin
        _create_product("Loss", 50, cost_price=80)  # negative margin

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
                price
                costPrice
            }
        }
        """

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_compare": {
                        "left": "price",
                        "operator": "GT",
                        "right": "cost_price",
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Profitable" in names
        assert "Break Even" not in names
        assert "Loss" not in names

    def test_filter_with_multiplier(self, gql_client_advanced):
        """Filter products where price >= cost_price * 1.5 (50%+ markup)."""
        _create_product("High Markup", 180, cost_price=100)  # 80% markup
        _create_product("Low Markup", 120, cost_price=100)  # 20% markup
        _create_product("Medium Markup", 150, cost_price=100)  # 50% markup

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_compare": {
                        "left": "price",
                        "operator": "GTE",
                        "right": "cost_price",
                        "rightMultiplier": 1.5,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "High Markup" in names
        assert "Medium Markup" in names  # Exactly 50%
        assert "Low Markup" not in names

    def test_filter_with_offset(self, gql_client_advanced):
        """Filter products where price > cost_price + 30 (absolute margin)."""
        _create_product("Good Margin", 100, cost_price=50)  # $50 margin
        _create_product("Small Margin", 80, cost_price=60)  # $20 margin
        _create_product("Exact Margin", 80, cost_price=50)  # $30 margin

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "_compare": {
                        "left": "price",
                        "operator": "GT",
                        "right": "cost_price",
                        "rightOffset": 30,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Good Margin" in names
        assert "Small Margin" not in names
        assert "Exact Margin" not in names  # Exactly $30, not greater


class TestDistinctCountFilters:
    """Test distinct count aggregation filters with actual queries."""

    def test_filter_by_distinct_unit_prices(self, gql_client_advanced):
        """Filter products by count of distinct unit prices in orders."""
        p1 = _create_product("Varied Pricing", 100)
        p2 = _create_product("Fixed Pricing", 200)
        p3 = _create_product("Some Varied", 300)

        # P1: 3 distinct unit prices
        _create_order_item(p1, 1, 50)
        _create_order_item(p1, 2, 60)
        _create_order_item(p1, 1, 70)
        _create_order_item(p1, 1, 50)  # Duplicate price

        # P2: 1 distinct unit price
        _create_order_item(p2, 1, 100)
        _create_order_item(p2, 2, 100)
        _create_order_item(p2, 1, 100)

        # P3: 2 distinct unit prices
        _create_order_item(p3, 1, 150)
        _create_order_item(p3, 1, 200)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Filter products with at least 3 distinct unit prices
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "orderItemsAgg": {
                        "field": "unit_price",
                        "countDistinct": {"gte": 3},
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Varied Pricing" in names
        assert "Fixed Pricing" not in names
        assert "Some Varied" not in names


class TestDateTruncFilters:
    """Test date truncation filters with actual queries."""

    def test_filter_by_year(self, gql_client_advanced):
        """Filter products created in a specific year."""
        from django.utils import timezone
        from datetime import timedelta

        # Create products with different date_creation dates
        p1 = _create_product("This Year Product", 100)
        p2 = _create_product("Last Year Product", 200)

        # Manually update date_creation for testing
        today = timezone.now()
        last_year = today.replace(year=today.year - 1)

        # Update p2 to be created last year
        from test_app.models import Product
        Product.objects.filter(pk=p2.pk).update(date_creation=last_year)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Filter products created this year
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationTrunc": {
                        "precision": "YEAR",
                        "thisPeriod": True,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "This Year Product" in names
        assert "Last Year Product" not in names

    def test_filter_by_specific_year(self, gql_client_advanced):
        """Filter products by specific year value."""
        from django.utils import timezone

        p1 = _create_product("Current Product", 100)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        current_year = timezone.now().year

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationTrunc": {
                        "precision": "YEAR",
                        "year": current_year,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Current Product" in names

    def test_filter_by_month(self, gql_client_advanced):
        """Filter products created in a specific month."""
        from django.utils import timezone

        p1 = _create_product("This Month Product", 100)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        today = timezone.now()

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationTrunc": {
                        "precision": "MONTH",
                        "year": today.year,
                        "month": today.month,
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "This Month Product" in names


class TestExtractDateFilters:
    """Test date extraction filters with actual queries."""

    def test_filter_by_day_of_month(self, gql_client_advanced):
        """Filter products created on the 15th of any month."""
        from django.utils import timezone
        from datetime import timedelta

        # Create products
        p1 = _create_product("Created on 15th", 100)
        p2 = _create_product("Created on other day", 200)

        # Update date_creation for testing
        today = timezone.now()
        day_15 = today.replace(day=15)
        day_20 = today.replace(day=20)

        from test_app.models import Product
        Product.objects.filter(pk=p1.pk).update(date_creation=day_15)
        Product.objects.filter(pk=p2.pk).update(date_creation=day_20)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationExtract": {
                        "day": {"eq": 15}
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Created on 15th" in names
        assert "Created on other day" not in names

    def test_filter_by_quarter(self, gql_client_advanced):
        """Filter products created in Q4 (October-December)."""
        from django.utils import timezone

        p1 = _create_product("Q4 Product", 100)
        p2 = _create_product("Q2 Product", 200)

        # Set Q4 date (October) and Q2 date (April)
        q4_date = timezone.now().replace(month=10, day=15)
        q2_date = timezone.now().replace(month=4, day=15)

        from test_app.models import Product
        Product.objects.filter(pk=p1.pk).update(date_creation=q4_date)
        Product.objects.filter(pk=p2.pk).update(date_creation=q2_date)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationExtract": {
                        "quarter": {"eq": 4}
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Q4 Product" in names
        assert "Q2 Product" not in names

    def test_filter_by_day_of_week(self, gql_client_advanced):
        """Filter products created on specific day of week."""
        from django.utils import timezone
        from datetime import timedelta

        p1 = _create_product("Monday Product", 100)
        p2 = _create_product("Friday Product", 200)

        # Find next Monday and Friday
        today = timezone.now()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday = today + timedelta(days=days_until_monday)
        friday = monday + timedelta(days=4)

        from test_app.models import Product
        Product.objects.filter(pk=p1.pk).update(date_creation=monday)
        Product.objects.filter(pk=p2.pk).update(date_creation=friday)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Monday is day 2 in Django's ExtractWeekDay (Sunday=1, Monday=2, ..., Saturday=7)
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationExtract": {
                        "dayOfWeek": {"eq": 2}  # Monday
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Monday Product" in names
        assert "Friday Product" not in names

    def test_filter_by_hour_range(self, gql_client_advanced):
        """Filter products by hour range (business hours)."""
        from django.utils import timezone

        p1 = _create_product("Morning Product", 100)
        p2 = _create_product("Evening Product", 200)

        # Set 10 AM and 8 PM times
        morning = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        evening = timezone.now().replace(hour=20, minute=0, second=0, microsecond=0)

        from test_app.models import Product
        Product.objects.filter(pk=p1.pk).update(date_creation=morning)
        Product.objects.filter(pk=p2.pk).update(date_creation=evening)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        # Business hours: 9 AM - 5 PM (9-17)
        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationExtract": {
                        "hour": {"gte": 9, "lt": 17}
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Morning Product" in names
        assert "Evening Product" not in names

    def test_filter_combined_extract_parts(self, gql_client_advanced):
        """Filter by multiple extracted date parts (year and month)."""
        from django.utils import timezone

        p1 = _create_product("Target Product", 100)
        p2 = _create_product("Different Month", 200)

        today = timezone.now()
        target_date = today.replace(month=6, day=15)  # June 15
        other_date = today.replace(month=3, day=15)   # March 15

        from test_app.models import Product
        Product.objects.filter(pk=p1.pk).update(date_creation=target_date)
        Product.objects.filter(pk=p2.pk).update(date_creation=other_date)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, orderBy: ["name"]) {
                name
            }
        }
        """

        result = gql_client_advanced.execute(
            query,
            variables={
                "where": {
                    "dateCreationExtract": {
                        "year": {"eq": today.year},
                        "month": {"eq": 6}
                    }
                }
            },
        )

        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Target Product" in names
        assert "Different Month" not in names


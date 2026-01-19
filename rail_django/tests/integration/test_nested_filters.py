"""
Integration tests for nested filter inputs (Prisma/Hasura style filtering).

Tests the 'where' argument with nested filter syntax against actual database queries.
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Category, Post, Tag, Product, Comment, OrderItem

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client_nested():
    """GraphQL client with nested filter style."""
    harness = build_schema(schema_name="test_nested", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="nested_admin",
        email="nested_admin@example.com",
        password="pass12345",
    )
    yield RailGraphQLTestClient(harness.schema, schema_name="test_nested", user=user)


def _create_category(name="General", description=""):
    return Category.objects.create(name=name, description=description)


def _create_post(title, category, tags=None):
    post = Post.objects.create(title=title, category=category)
    if tags:
        post.tags.set(tags)
    return post


def _create_tag(name):
    return Tag.objects.create(name=name)


def _create_product(name, price):
    return Product.objects.create(name=name, price=Decimal(str(price)))


def _create_order_item(product, quantity, unit_price):
    return OrderItem.objects.create(
        product=product,
        quantity=quantity,
        unit_price=Decimal(str(unit_price)),
    )


class TestNestedStringFilters:
    """Test string filter operations with nested syntax."""

    def test_eq_filter(self, gql_client_nested):
        """Test exact string match."""
        _create_category("Electronics")
        _create_category("Books")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"name": {"eq": "Electronics"}}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert names == ["Electronics"]

    def test_icontains_filter(self, gql_client_nested):
        """Test case-insensitive contains."""
        _create_category("Electronics")
        _create_category("Electronic Games")
        _create_category("Books")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"name": {"icontains": "electron"}}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert "Electronics" in names
        assert "Electronic Games" in names
        assert "Books" not in names

    def test_starts_with_filter(self, gql_client_nested):
        """Test starts_with filter."""
        _create_category("Python Programming")
        _create_category("Java Programming")
        _create_category("Programming Basics")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"name": {"starts_with": "Python"}}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert names == ["Python Programming"]

    def test_in_filter(self, gql_client_nested):
        """Test in list filter."""
        _create_category("A")
        _create_category("B")
        _create_category("C")
        _create_category("D")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"name": {"in": ["A", "C"]}}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert names == ["A", "C"]

    def test_not_in_filter(self, gql_client_nested):
        """Test not in list filter."""
        _create_category("A")
        _create_category("B")
        _create_category("C")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"name": {"not_in": ["A", "C"]}}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert names == ["B"]


class TestNestedNumericFilters:
    """Test numeric filter operations with nested syntax."""

    def test_gt_filter(self, gql_client_nested):
        """Test greater than filter."""
        _create_product("Cheap", 10.00)
        _create_product("Mid", 50.00)
        _create_product("Expensive", 100.00)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, order_by: ["price"]) {
                name
                price
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"price": {"gt": 40.0}}}
        )
        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert "Cheap" not in names
        assert "Mid" in names
        assert "Expensive" in names

    def test_between_filter(self, gql_client_nested):
        """Test between range filter."""
        _create_product("P1", 10.00)
        _create_product("P2", 25.00)
        _create_product("P3", 50.00)
        _create_product("P4", 75.00)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, order_by: ["price"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"price": {"between": [20.0, 60.0]}}}
        )
        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert names == ["P2", "P3"]

    def test_multiple_operators_same_field(self, gql_client_nested):
        """Test multiple operators on same field (AND logic)."""
        _create_product("P1", 10.00)
        _create_product("P2", 30.00)
        _create_product("P3", 50.00)
        _create_product("P4", 70.00)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, order_by: ["price"]) {
                name
            }
        }
        """
        # price > 20 AND price < 60
        result = gql_client_nested.execute(
            query, variables={"where": {"price": {"gt": 20.0, "lt": 60.0}}}
        )
        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert names == ["P2", "P3"]


class TestNestedBooleanOperators:
    """Test AND, OR, NOT boolean operators with nested syntax."""

    def test_and_operator(self, gql_client_nested):
        """Test AND operator combining conditions."""
        cat = _create_category("Tech", "Technology articles")
        _create_post("Python Tips", cat)
        _create_post("Java Tips", cat)
        _create_post("Python Advanced", cat)

        query = """
        query($where: PostWhereInput) {
            posts(where: $where, order_by: ["title"]) {
                title
            }
        }
        """
        result = gql_client_nested.execute(
            query,
            variables={
                "where": {
                    "AND": [
                        {"title": {"icontains": "python"}},
                        {"title": {"icontains": "tips"}},
                    ]
                }
            },
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert titles == ["Python Tips"]

    def test_or_operator(self, gql_client_nested):
        """Test OR operator for alternative conditions."""
        cat = _create_category("General")
        _create_post("Alpha", cat)
        _create_post("Beta", cat)
        _create_post("Gamma", cat)

        query = """
        query($where: PostWhereInput) {
            posts(where: $where, order_by: ["title"]) {
                title
            }
        }
        """
        result = gql_client_nested.execute(
            query,
            variables={
                "where": {
                    "OR": [{"title": {"eq": "Alpha"}}, {"title": {"eq": "Gamma"}}]
                }
            },
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert titles == ["Alpha", "Gamma"]

    def test_not_operator(self, gql_client_nested):
        """Test NOT operator for negation."""
        cat = _create_category("General")
        _create_post("Include Me", cat)
        _create_post("Exclude Me", cat)
        _create_post("Also Include", cat)

        query = """
        query($where: PostWhereInput) {
            posts(where: $where, order_by: ["title"]) {
                title
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"NOT": {"title": {"icontains": "exclude"}}}}
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert "Include Me" in titles
        assert "Also Include" in titles
        assert "Exclude Me" not in titles

    def test_nested_boolean_operators(self, gql_client_nested):
        """Test complex nested boolean logic."""
        cat = _create_category("General")
        _create_post("Python Beginner", cat)
        _create_post("Python Advanced", cat)
        _create_post("Java Beginner", cat)
        _create_post("Ruby Advanced", cat)

        query = """
        query($where: PostWhereInput) {
            posts(where: $where, order_by: ["title"]) {
                title
            }
        }
        """
        # (Python OR Java) AND NOT Beginner
        result = gql_client_nested.execute(
            query,
            variables={
                "where": {
                    "AND": [
                        {
                            "OR": [
                                {"title": {"icontains": "python"}},
                                {"title": {"icontains": "java"}},
                            ]
                        },
                        {"NOT": {"title": {"icontains": "beginner"}}},
                    ]
                }
            },
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert titles == ["Python Advanced"]


class TestNestedRelationFilters:
    """Test relation-based filters with nested syntax."""

    def test_filter_by_fk_id(self, gql_client_nested):
        """Test filtering by foreign key ID."""
        cat1 = _create_category("Category 1")
        cat2 = _create_category("Category 2")
        _create_post("Post in Cat1", cat1)
        _create_post("Post in Cat2", cat2)

        query = """
        query($where: PostWhereInput) {
            posts(where: $where) {
                title
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"category": {"eq": str(cat1.id)}}}
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert titles == ["Post in Cat1"]

    def test_filter_by_nested_relation(self, gql_client_nested):
        """Test filtering by nested relation fields."""
        cat1 = _create_category("Electronics")
        cat2 = _create_category("Books")
        _create_post("Phone Review", cat1)
        _create_post("Novel Review", cat2)

        query = """
        query($where: PostWhereInput) {
            posts(where: $where) {
                title
            }
        }
        """
        result = gql_client_nested.execute(
            query,
            variables={"where": {"category_rel": {"name": {"eq": "Electronics"}}}},
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert titles == ["Phone Review"]


class TestNestedM2MFilters:
    """Test many-to-many relation filters with nested syntax."""

    def test_some_filter(self, gql_client_nested):
        """Test _some filter for M2M relations."""
        cat = _create_category("General")
        tag_python = _create_tag("python")
        tag_java = _create_tag("java")
        tag_ruby = _create_tag("ruby")

        post1 = _create_post("Python Guide", cat, tags=[tag_python])
        post2 = _create_post("Java Guide", cat, tags=[tag_java])
        post3 = _create_post("Multi-lang", cat, tags=[tag_python, tag_ruby])

        query = """
        query($where: PostWhereInput) {
            posts(where: $where, order_by: ["title"]) {
                title
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"tags_some": {"name": {"eq": "python"}}}}
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert "Python Guide" in titles
        assert "Multi-lang" in titles
        assert "Java Guide" not in titles

    def test_none_filter(self, gql_client_nested):
        """Test _none filter for M2M relations."""
        cat = _create_category("General")
        tag_deprecated = _create_tag("deprecated")
        tag_active = _create_tag("active")

        _create_post("Old Post", cat, tags=[tag_deprecated])
        _create_post("New Post", cat, tags=[tag_active])
        _create_post("No Tags", cat)

        query = """
        query($where: PostWhereInput) {
            posts(where: $where, order_by: ["title"]) {
                title
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"tags_none": {"name": {"eq": "deprecated"}}}}
        )
        assert result.get("errors") is None
        titles = [p["title"] for p in result["data"]["posts"]]
        assert "Old Post" not in titles
        assert "New Post" in titles
        assert "No Tags" in titles


class TestNestedAggregationFilters:
    """Test aggregation filters on related objects."""

    def test_sum_aggregation_filter(self, gql_client_nested):
        """Filter by SUM over related objects."""
        product_a = _create_product("Bulk", 10.00)
        product_b = _create_product("Single", 20.00)

        _create_order_item(product_a, 1, 600.00)
        _create_order_item(product_a, 1, 450.00)
        _create_order_item(product_b, 1, 50.00)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query,
            variables={
                "where": {
                    "order_items_agg": {
                        "field": "unit_price",
                        "sum": {"gte": 1000.0},
                    }
                }
            },
        )
        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert names == ["Bulk"]

    def test_count_aggregation_filter(self, gql_client_nested):
        """Filter by COUNT over related objects."""
        product_a = _create_product("WithMany", 5.00)
        product_b = _create_product("WithOne", 8.00)

        _create_order_item(product_a, 1, 25.00)
        _create_order_item(product_a, 2, 30.00)
        _create_order_item(product_b, 1, 15.00)

        query = """
        query($where: ProductWhereInput) {
            products(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query,
            variables={
                "where": {
                    "order_items_agg": {
                        "field": "id",
                        "count": {"gte": 2},
                    }
                }
            },
        )
        assert result.get("errors") is None
        names = [p["name"] for p in result["data"]["products"]]
        assert names == ["WithMany"]


class TestNestedIsNullFilter:
    """Test is_null filter for nullable fields."""

    def test_is_null_true(self, gql_client_nested):
        """Test filtering for null values."""
        _create_category("With Desc", "Has description")
        _create_category("No Desc", "")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"description": {"eq": ""}}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert "No Desc" in names


class TestQuickFilter:
    """Test quick filter (multi-field search) functionality."""

    def test_quick_filter_finds_in_name(self, gql_client_nested):
        """Quick filter should search across text fields."""
        _create_category("Electronics", "Devices and gadgets")
        _create_category("Books", "Reading materials")
        _create_category("Music", "Audio and sound")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"quick": "electron"}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert "Electronics" in names
        assert "Books" not in names

    def test_quick_filter_finds_in_description(self, gql_client_nested):
        """Quick filter should search in description field."""
        _create_category("Category A", "Contains electronics info")
        _create_category("Category B", "Contains books info")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {"quick": "electronics"}}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert "Category A" in names
        assert "Category B" not in names

    def test_quick_filter_combined_with_other_filters(self, gql_client_nested):
        """Quick filter should work with other filters."""
        _create_category("Electronics", "Gadgets")
        _create_category("Electronic Games", "Gaming")
        _create_category("Books", "Reading")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where, order_by: ["name"]) {
                name
            }
        }
        """
        result = gql_client_nested.execute(
            query, variables={"where": {
                "quick": "electron",
                "name": {"ends_with": "Games"}
            }}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert "Electronic Games" in names
        assert "Electronics" not in names


class TestIncludeFilter:
    """Test include filter (ID union) functionality."""

    def test_include_filter_adds_specific_ids(self, gql_client_nested):
        """Include filter should add specific IDs to results."""
        cat1 = _create_category("Category 1", "First")
        cat2 = _create_category("Category 2", "Second")
        cat3 = _create_category("Category 3", "Third")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where) {
                id
                name
            }
        }
        """
        # Filter for Category 1 but include Category 3
        result = gql_client_nested.execute(
            query, variables={"where": {
                "name": {"eq": "Category 1"},
                "include": [str(cat3.id)]
            }}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert "Category 1" in names
        assert "Category 3" in names
        assert "Category 2" not in names

    def test_include_filter_with_empty_base_results(self, gql_client_nested):
        """Include should work even when base filter returns nothing."""
        cat1 = _create_category("Alpha", "A")
        cat2 = _create_category("Beta", "B")

        query = """
        query($where: CategoryWhereInput) {
            categorys(where: $where) {
                id
                name
            }
        }
        """
        # Filter for non-existent category but include cat1
        result = gql_client_nested.execute(
            query, variables={"where": {
                "name": {"eq": "NonExistent"},
                "include": [str(cat1.id)]
            }}
        )
        assert result.get("errors") is None
        names = [c["name"] for c in result["data"]["categorys"]]
        assert "Alpha" in names

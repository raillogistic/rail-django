import pytest

from rail_django.extensions.optimization.analyzer import QueryAnalyzer
from rail_django.extensions.optimization.config import QueryOptimizationConfig
from rail_django.extensions.optimization.optimizer import QueryOptimizer
from test_app.models import Post, Product

pytestmark = pytest.mark.unit


def test_analyzer_ignores_invalid_wrapper_paths_for_prefetch():
    analyzer = QueryAnalyzer(QueryOptimizationConfig())
    requested_fields = {
        "pageInfo",
        "pageInfo__totalCount",
        "items",
        "items__name",
        "items__tags",
        "items__order_items__unit_price",
        "items__order_items__product__name",
    }

    prefetch_fields = analyzer._get_prefetch_related_fields(Product, requested_fields)

    assert prefetch_fields == ["order_items"]
    assert "items__tags" not in prefetch_fields


def test_analyzer_stops_on_invalid_prefix_in_nested_path():
    analyzer = QueryAnalyzer(QueryOptimizationConfig())
    requested_fields = {
        "foo__tags__name",
    }

    prefetch_fields = analyzer._get_prefetch_related_fields(Post, requested_fields)

    assert prefetch_fields == []


def test_optimizer_filters_invalid_prefetch_paths():
    optimizer = QueryOptimizer(QueryOptimizationConfig())

    valid, invalid = optimizer._filter_valid_prefetch_fields(
        Product,
        ["items__tags", "order_items", "order_items"],
    )

    assert valid == ["order_items"]
    assert invalid == ["items__tags"]

"""
Unit tests for advanced filter features.

Tests Window Functions, Subquery Filters, Conditional Aggregation, and Array Filters.
"""

import pytest
from unittest.mock import MagicMock, patch

import graphene
from django.db.models import Q
from django.test import TestCase

from rail_django.generators.filters import (
    ArrayFilterInput,
    ConditionalAggregationFilterInput,
    ExistsFilterInput,
    SubqueryFilterInput,
    WindowFilterInput,
    WindowFunctionEnum,
    NestedFilterApplicator,
    NestedFilterInputGenerator,
)

pytestmark = pytest.mark.unit


class TestAdvancedFilterInputTypes(TestCase):
    """Test new filter input type definitions."""

    def test_window_filter_input_fields(self):
        """WindowFilterInput should have expected fields."""
        fields = WindowFilterInput._meta.fields

        self.assertIn("function", fields)
        self.assertIn("partition_by", fields)
        self.assertIn("order_by", fields)
        self.assertIn("rank", fields)
        self.assertIn("percentile", fields)

    def test_subquery_filter_input_fields(self):
        """SubqueryFilterInput should have expected fields."""
        fields = SubqueryFilterInput._meta.fields

        self.assertIn("relation", fields)
        self.assertIn("order_by", fields)
        self.assertIn("filter", fields)
        self.assertIn("field", fields)
        self.assertIn("eq", fields)
        self.assertIn("neq", fields)
        self.assertIn("gt", fields)
        self.assertIn("gte", fields)
        self.assertIn("lt", fields)
        self.assertIn("lte", fields)
        self.assertIn("is_null", fields)

    def test_exists_filter_input_fields(self):
        """ExistsFilterInput should have expected fields."""
        fields = ExistsFilterInput._meta.fields

        self.assertIn("relation", fields)
        self.assertIn("filter", fields)
        self.assertIn("exists", fields)

    def test_conditional_aggregation_filter_input_fields(self):
        """ConditionalAggregationFilterInput should have expected fields."""
        fields = ConditionalAggregationFilterInput._meta.fields

        self.assertIn("field", fields)
        self.assertIn("filter", fields)
        self.assertIn("sum", fields)
        self.assertIn("avg", fields)
        self.assertIn("count", fields)

    def test_array_filter_input_fields(self):
        """ArrayFilterInput should have expected fields."""
        fields = ArrayFilterInput._meta.fields

        self.assertIn("contains", fields)
        self.assertIn("contained_by", fields)
        self.assertIn("overlaps", fields)
        self.assertIn("length", fields)
        self.assertIn("is_null", fields)

    def test_window_function_enum_values(self):
        """WindowFunctionEnum should have expected values."""
        self.assertEqual(WindowFunctionEnum.RANK.value, "rank")
        self.assertEqual(WindowFunctionEnum.DENSE_RANK.value, "dense_rank")
        self.assertEqual(WindowFunctionEnum.ROW_NUMBER.value, "row_number")
        self.assertEqual(WindowFunctionEnum.PERCENT_RANK.value, "percent_rank")


class TestWindowFilterMethods(TestCase):
    """Test window function filter methods."""

    def setUp(self):
        self.applicator = NestedFilterApplicator(schema_name="test")

    def test_build_window_filter_q_with_rank(self):
        """Window filter with rank condition should build correct Q object."""
        window_filter = {
            "function": "rank",
            "order_by": ["-price"],
            "rank": {"lte": 3},
        }

        q = self.applicator._build_window_filter_q(window_filter)

        # Should build Q object filtering on _window_rank
        self.assertIsInstance(q, Q)

    def test_build_window_filter_q_with_percentile(self):
        """Window filter with percentile condition should build correct Q object."""
        window_filter = {
            "function": "percent_rank",
            "partition_by": ["category_id"],
            "order_by": ["-sales"],
            "percentile": {"lte": 0.1},
        }

        q = self.applicator._build_window_filter_q(window_filter)

        self.assertIsInstance(q, Q)


class TestConditionalAggregationFilterMethods(TestCase):
    """Test conditional aggregation filter methods."""

    def setUp(self):
        self.applicator = NestedFilterApplicator(schema_name="test")

    def test_collect_conditional_aggregation_annotations_empty(self):
        """Empty where input should return empty annotations."""
        annotations = self.applicator._collect_conditional_aggregation_annotations({})
        self.assertEqual(annotations, {})

    def test_build_conditional_aggregation_annotations(self):
        """Should build correct annotations with filter condition."""
        cond_agg_filter = {
            "field": "amount",
            "filter": {"status": {"eq": "completed"}},
            "count": {"gte": 5},
        }

        annotations = self.applicator._build_conditional_aggregation_annotations(
            "orders", cond_agg_filter
        )

        self.assertIn("orders_cond_count", annotations)

    def test_build_conditional_aggregation_q(self):
        """Should build Q object for conditional aggregation."""
        cond_agg_filter = {
            "field": "amount",
            "count": {"gte": 5},
        }

        q = self.applicator._build_conditional_aggregation_q("orders", cond_agg_filter)

        self.assertIsInstance(q, Q)


class TestSubqueryFilterMethods(TestCase):
    """Test subquery filter methods."""

    def setUp(self):
        self.applicator = NestedFilterApplicator(schema_name="test")

    def test_build_subquery_filter_q_returns_tuple(self):
        """Subquery filter should return tuple of (Q, annotations)."""
        from test_app.models import Product

        subquery_filter = {
            "relation": "order_items",
            "order_by": ["-unit_price"],
            "field": "unit_price",
            "gt": 100,
        }

        result = self.applicator._build_subquery_filter_q(subquery_filter, Product)

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], Q)
        self.assertIsInstance(result[1], dict)


class TestExistsFilterMethods(TestCase):
    """Test exists filter methods."""

    def setUp(self):
        self.applicator = NestedFilterApplicator(schema_name="test")

    def test_build_exists_filter_q_returns_q(self):
        """Exists filter should return Q object."""
        from test_app.models import Product

        exists_filter = {
            "relation": "order_items",
            "filter": {"quantity": {"gte": 10}},
            "exists": True,
        }

        q = self.applicator._build_exists_filter_q(exists_filter, Product)

        self.assertIsInstance(q, Q)

    def test_build_exists_filter_q_with_no_exists(self):
        """Exists filter with exists=False should negate the query."""
        from test_app.models import Product

        exists_filter = {
            "relation": "order_items",
            "exists": False,
        }

        q = self.applicator._build_exists_filter_q(exists_filter, Product)

        self.assertIsInstance(q, Q)


class TestArrayFilterMethods(TestCase):
    """Test array field filter methods."""

    def setUp(self):
        self.applicator = NestedFilterApplicator(schema_name="test")

    def test_build_array_field_q_contains(self):
        """Array filter with contains should build correct Q object."""
        array_filter = {
            "contains": ["python", "django"],
        }

        q = self.applicator._build_array_field_q("tags", array_filter)

        self.assertIsInstance(q, Q)

    def test_build_array_field_q_overlaps(self):
        """Array filter with overlaps should build correct Q object."""
        array_filter = {
            "overlaps": ["python", "javascript", "rust"],
        }

        q = self.applicator._build_array_field_q("tags", array_filter)

        self.assertIsInstance(q, Q)

    def test_build_array_field_q_is_null(self):
        """Array filter with is_null should build correct Q object."""
        array_filter = {
            "is_null": True,
        }

        q = self.applicator._build_array_field_q("tags", array_filter)

        self.assertIsInstance(q, Q)


class TestGeneratorWithAdvancedFilters(TestCase):
    """Test filter generator with advanced filter settings."""

    def test_generator_adds_window_filter_when_enabled(self):
        """Generator should add _window field when window filters are enabled."""
        from test_app.models import Product

        mock_settings = MagicMock()
        mock_settings.enable_window_filters = True
        mock_settings.enable_subquery_filters = False
        mock_settings.enable_conditional_aggregation = False
        mock_settings.enable_array_filters = False
        mock_settings.enable_full_text_search = False

        generator = NestedFilterInputGenerator(schema_name="test_window_gen")
        generator.filtering_settings = mock_settings
        generator.clear_cache()

        where_input = generator.generate_where_input(Product)
        fields = where_input._meta.fields

        self.assertIn("_window", fields)

    def test_generator_adds_subquery_filter_when_enabled(self):
        """Generator should add _subquery and _exists fields when subquery filters are enabled."""
        from test_app.models import Product

        mock_settings = MagicMock()
        mock_settings.enable_window_filters = False
        mock_settings.enable_subquery_filters = True
        mock_settings.enable_conditional_aggregation = False
        mock_settings.enable_array_filters = False
        mock_settings.enable_full_text_search = False

        generator = NestedFilterInputGenerator(schema_name="test_subquery_gen")
        generator.filtering_settings = mock_settings
        generator.clear_cache()

        where_input = generator.generate_where_input(Product)
        fields = where_input._meta.fields

        self.assertIn("_subquery", fields)
        self.assertIn("_exists", fields)

    def test_generator_adds_conditional_agg_when_enabled(self):
        """Generator should add _cond_agg fields when conditional aggregation is enabled."""
        from test_app.models import Product

        mock_settings = MagicMock()
        mock_settings.enable_window_filters = False
        mock_settings.enable_subquery_filters = False
        mock_settings.enable_conditional_aggregation = True
        mock_settings.enable_array_filters = False
        mock_settings.enable_full_text_search = False

        generator = NestedFilterInputGenerator(schema_name="test_cond_agg_gen")
        generator.filtering_settings = mock_settings
        generator.clear_cache()

        where_input = generator.generate_where_input(Product)
        fields = where_input._meta.fields

        # Should have order_items_cond_agg for reverse relation
        self.assertIn("order_items_cond_agg", fields)


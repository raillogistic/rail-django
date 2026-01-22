"""
Tests for query generator base utilities and refactored query builders.

This module tests:
- QueryContext dataclass
- QueryFilterPipeline
- QueryOrderingHelper
- build_query_arguments function
- Integration with list and paginated queries
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, PropertyMock, patch
from dataclasses import asdict

import pytest
from django.db import models
from django.db.models import Q
from django.test import TestCase

from rail_django.generators.queries.base import (
    RESERVED_QUERY_ARGS,
    QueryContext,
    QueryFilterPipeline,
    QueryOrderingHelper,
    build_query_arguments,
    create_default_ordering_config,
    map_filter_to_graphql_type,
)


# =============================================================================
# Test Models (in-memory only, not migrated)
# =============================================================================

class MockModel(models.Model):
    """Mock model for testing."""
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "tests"
        managed = False


class MockRelatedModel(models.Model):
    """Mock related model for testing."""
    parent = models.ForeignKey(MockModel, on_delete=models.CASCADE, related_name="children")
    title = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"
        managed = False


# =============================================================================
# Test Constants
# =============================================================================

class TestReservedQueryArgs:
    """Tests for RESERVED_QUERY_ARGS constant."""

    def test_reserved_args_is_frozenset(self):
        """RESERVED_QUERY_ARGS should be immutable."""
        assert isinstance(RESERVED_QUERY_ARGS, frozenset)

    def test_contains_expected_args(self):
        """Should contain all expected reserved argument names."""
        expected = {
            "where", "order_by", "offset", "limit", "page", "per_page",
            "include", "presets", "savedFilter", "distinct_on", "quick",
            "search", "group_by"
        }
        assert expected.issubset(RESERVED_QUERY_ARGS)

    def test_immutability(self):
        """Should not allow modification."""
        with pytest.raises(AttributeError):
            RESERVED_QUERY_ARGS.add("new_arg")


# =============================================================================
# Test QueryContext
# =============================================================================

class TestQueryContext:
    """Tests for QueryContext dataclass."""

    def test_creation_with_required_fields(self):
        """Should create context with required fields."""
        mock_model = Mock()
        mock_queryset = Mock()
        mock_info = Mock()

        context = QueryContext(
            model=mock_model,
            queryset=mock_queryset,
            info=mock_info,
            kwargs={"page": 1},
            graphql_meta=Mock(),
            filter_applicator=None,
            filter_class=None,
            ordering_config=None,
            settings=Mock(),
        )

        assert context.model == mock_model
        assert context.queryset == mock_queryset
        assert context.kwargs == {"page": 1}
        assert context.schema_name == "default"

    def test_default_schema_name(self):
        """Should use 'default' as default schema_name."""
        context = QueryContext(
            model=Mock(),
            queryset=Mock(),
            info=Mock(),
            kwargs={},
            graphql_meta=Mock(),
            filter_applicator=None,
            filter_class=None,
            ordering_config=None,
            settings=Mock(),
        )
        assert context.schema_name == "default"

    def test_custom_schema_name(self):
        """Should accept custom schema_name."""
        context = QueryContext(
            model=Mock(),
            queryset=Mock(),
            info=Mock(),
            kwargs={},
            graphql_meta=Mock(),
            filter_applicator=None,
            filter_class=None,
            ordering_config=None,
            settings=Mock(),
            schema_name="custom_schema",
        )
        assert context.schema_name == "custom_schema"


# =============================================================================
# Test QueryFilterPipeline
# =============================================================================

@pytest.mark.unit
class TestQueryFilterPipeline:
    """Tests for QueryFilterPipeline."""

    def _create_context(self, **overrides) -> QueryContext:
        """Helper to create test context."""
        mock_queryset = Mock()
        mock_queryset.filter = Mock(return_value=mock_queryset)
        mock_queryset.none = Mock(return_value=mock_queryset)

        defaults = {
            "model": Mock(__name__="TestModel"),
            "queryset": mock_queryset,
            "info": Mock(context=Mock(user=None)),
            "kwargs": {},
            "graphql_meta": Mock(),
            "filter_applicator": None,
            "filter_class": None,
            "ordering_config": None,
            "settings": Mock(),
        }
        defaults.update(overrides)
        return QueryContext(**defaults)

    def test_apply_all_returns_queryset(self):
        """apply_all should return a queryset."""
        context = self._create_context()
        pipeline = QueryFilterPipeline(context)

        result = pipeline.apply_all()

        assert result is not None

    def test_apply_all_without_filters(self):
        """Should return original queryset when no filters provided."""
        mock_queryset = Mock()
        context = self._create_context(queryset=mock_queryset, kwargs={})
        pipeline = QueryFilterPipeline(context)

        result = pipeline.apply_all()

        assert result == mock_queryset

    def test_get_current_where_initializes_from_kwargs(self):
        """Should initialize where dict from kwargs."""
        context = self._create_context(kwargs={"where": {"name": {"eq": "test"}}})
        pipeline = QueryFilterPipeline(context)

        result = pipeline._get_current_where()

        assert result == {"name": {"eq": "test"}}

    def test_get_current_where_creates_copy(self):
        """Should create a copy of where dict to avoid mutation."""
        original_where = {"name": {"eq": "test"}}
        context = self._create_context(kwargs={"where": original_where})
        pipeline = QueryFilterPipeline(context)

        result = pipeline._get_current_where()
        result["new_key"] = "new_value"

        assert "new_key" not in original_where

    def test_get_current_where_empty_when_none(self):
        """Should return empty dict when where is None."""
        context = self._create_context(kwargs={})
        pipeline = QueryFilterPipeline(context)

        result = pipeline._get_current_where()

        assert result == {}

    def test_apply_include_ids(self):
        """Should merge include IDs into where filter."""
        context = self._create_context(kwargs={"include": ["1", "2", "3"]})
        pipeline = QueryFilterPipeline(context)

        pipeline._apply_include_ids()

        where = pipeline._get_current_where()
        assert "include" in where
        assert where["include"] == ["1", "2", "3"]

    def test_apply_include_ids_merges_with_existing(self):
        """Should merge new include IDs with existing ones."""
        context = self._create_context(kwargs={
            "where": {"include": ["existing"]},
            "include": ["new1", "new2"],
        })
        pipeline = QueryFilterPipeline(context)
        pipeline._get_current_where()  # Initialize

        pipeline._apply_include_ids()

        where = pipeline._get_current_where()
        assert "existing" in where["include"]
        assert "new1" in where["include"]
        assert "new2" in where["include"]

    def test_apply_presets_calls_applicator(self):
        """Should call filter applicator's apply_presets method."""
        mock_applicator = Mock()
        mock_applicator.apply_presets = Mock(return_value={"preset_applied": True})

        context = self._create_context(
            kwargs={"presets": ["active", "recent"]},
            filter_applicator=mock_applicator,
        )
        pipeline = QueryFilterPipeline(context)

        pipeline._apply_presets()

        mock_applicator.apply_presets.assert_called_once()

    def test_apply_basic_filters_with_valid_filterset(self):
        """Should apply basic filters when filterset is valid."""
        mock_queryset = Mock()
        mock_filtered_qs = Mock()

        mock_filterset = Mock()
        mock_filterset.is_valid = Mock(return_value=True)
        mock_filterset.qs = mock_filtered_qs

        mock_filter_class = Mock(return_value=mock_filterset)

        context = self._create_context(
            queryset=mock_queryset,
            kwargs={"custom_filter": "value"},
            filter_class=mock_filter_class,
        )
        pipeline = QueryFilterPipeline(context)

        result = pipeline._apply_basic_filters(mock_queryset)

        assert result == mock_filtered_qs

    def test_apply_basic_filters_excludes_reserved_args(self):
        """Should not pass reserved arguments to filterset."""
        mock_queryset = Mock()
        mock_filterset = Mock()
        mock_filterset.is_valid = Mock(return_value=True)
        mock_filterset.qs = mock_queryset

        mock_filter_class = Mock(return_value=mock_filterset)

        context = self._create_context(
            queryset=mock_queryset,
            kwargs={
                "where": {"name": "test"},
                "order_by": ["-id"],
                "limit": 10,
                "custom_filter": "value",
            },
            filter_class=mock_filter_class,
        )
        pipeline = QueryFilterPipeline(context)

        pipeline._apply_basic_filters(mock_queryset)

        # Check that filter class was called only with non-reserved args
        call_args = mock_filter_class.call_args[0][0]
        assert "custom_filter" in call_args
        assert "where" not in call_args
        assert "order_by" not in call_args
        assert "limit" not in call_args


# =============================================================================
# Test QueryOrderingHelper
# =============================================================================

@pytest.mark.unit
class TestQueryOrderingHelper:
    """Tests for QueryOrderingHelper."""

    def _create_helper(self):
        """Create a QueryOrderingHelper for testing."""
        mock_qg = Mock()
        mock_qg._normalize_ordering_specs = Mock(return_value=["-created_at"])
        mock_qg._apply_count_annotations_for_ordering = Mock(
            return_value=(Mock(), ["-created_at"])
        )
        mock_qg._split_order_specs = Mock(return_value=(["-created_at"], []))
        mock_qg._apply_distinct_on = Mock(return_value=Mock())
        mock_qg._apply_property_ordering = Mock(side_effect=lambda items, specs: items)

        mock_model = Mock(__name__="TestModel")
        mock_ordering_config = Mock(allowed=[], default=[])
        mock_settings = Mock(max_property_ordering_results=1000)

        return QueryOrderingHelper(
            mock_qg, mock_model, mock_ordering_config, mock_settings
        )

    def test_apply_with_db_ordering(self):
        """Should apply database ordering to queryset."""
        helper = self._create_helper()
        mock_queryset = Mock()
        mock_queryset.order_by = Mock(return_value=mock_queryset)
        mock_queryset.count = Mock(return_value=100)

        helper.qg._apply_count_annotations_for_ordering.return_value = (
            mock_queryset, ["-created_at"]
        )
        helper.qg._split_order_specs.return_value = (["-created_at"], [])

        queryset, items, has_prop, total = helper.apply(
            mock_queryset, ["-created_at"], None
        )

        mock_queryset.order_by.assert_called_with("-created_at")
        assert items is None
        assert has_prop is False

    def test_apply_with_property_ordering(self):
        """Should apply property ordering and return items."""
        helper = self._create_helper()
        mock_queryset = Mock()
        mock_queryset.order_by = Mock(return_value=mock_queryset)
        mock_queryset.count = Mock(return_value=50)
        mock_queryset.__iter__ = Mock(return_value=iter([Mock(), Mock()]))
        mock_queryset.__getitem__ = Mock(return_value=mock_queryset)

        helper.qg._apply_count_annotations_for_ordering.return_value = (
            mock_queryset, ["-custom_property"]
        )
        helper.qg._split_order_specs.return_value = ([], ["-custom_property"])

        queryset, items, has_prop, total = helper.apply(
            mock_queryset, ["-custom_property"], None
        )

        assert has_prop is True
        assert total == 50

    def test_apply_with_distinct_on(self):
        """Should apply distinct_on when specified."""
        helper = self._create_helper()
        mock_queryset = Mock()

        helper.qg._normalize_ordering_specs.return_value = ["-created_at"]
        helper.qg._apply_count_annotations_for_ordering.return_value = (
            mock_queryset, ["-created_at"]
        )
        helper.qg._split_order_specs.return_value = (["-created_at"], [])

        helper.apply(mock_queryset, ["-created_at"], ["category"])

        helper.qg._apply_distinct_on.assert_called_once()


# =============================================================================
# Test build_query_arguments
# =============================================================================

@pytest.mark.unit
class TestBuildQueryArguments:
    """Tests for build_query_arguments function."""

    def _create_mock_settings(self, **overrides):
        """Create mock settings object."""
        settings = Mock()
        settings.enable_ordering = overrides.get("enable_ordering", True)
        settings.enable_pagination = overrides.get("enable_pagination", True)
        settings.default_page_size = overrides.get("default_page_size", 25)
        return settings

    def test_includes_where_when_nested_input_provided(self):
        """Should include 'where' argument when nested_where_input is provided."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()
        nested_where_input = Mock()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
            nested_where_input=nested_where_input,
        )

        assert "where" in args

    def test_includes_presets_when_nested_input_provided(self):
        """Should include 'presets' argument when nested_where_input is provided."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()
        nested_where_input = Mock()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
            nested_where_input=nested_where_input,
        )

        assert "presets" in args

    def test_includes_saved_filter_when_nested_input_provided(self):
        """Should include 'savedFilter' argument when nested_where_input is provided."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()
        nested_where_input = Mock()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
            nested_where_input=nested_where_input,
        )

        assert "savedFilter" in args

    def test_includes_include_argument(self):
        """Should always include 'include' argument."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
        )

        assert "include" in args

    def test_offset_limit_pagination(self):
        """Should include offset/limit for non-page-based pagination."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
            include_pagination=True,
            use_page_based=False,
        )

        assert "offset" in args
        assert "limit" in args
        assert "page" not in args
        assert "per_page" not in args

    def test_page_based_pagination(self):
        """Should include page/per_page for page-based pagination."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
            include_pagination=True,
            use_page_based=True,
        )

        assert "page" in args
        assert "per_page" in args
        assert "offset" not in args
        assert "limit" not in args

    def test_no_pagination_when_disabled(self):
        """Should not include pagination args when include_pagination=False."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
            include_pagination=False,
        )

        assert "offset" not in args
        assert "limit" not in args
        assert "page" not in args
        assert "per_page" not in args

    def test_includes_ordering_args_when_enabled(self):
        """Should include order_by and distinct_on when ordering is enabled."""
        settings = self._create_mock_settings(enable_ordering=True)
        ordering_config = create_default_ordering_config()

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
        )

        assert "order_by" in args
        assert "distinct_on" in args

    def test_includes_quick_when_in_filter_class(self):
        """Should include 'quick' when available in filter class."""
        settings = self._create_mock_settings()
        ordering_config = create_default_ordering_config()

        mock_filter_class = Mock()
        mock_filter_class.base_filters = {"quick": Mock()}

        args = build_query_arguments(
            settings=settings,
            ordering_config=ordering_config,
            filter_class=mock_filter_class,
        )

        assert "quick" in args


# =============================================================================
# Test create_default_ordering_config
# =============================================================================

@pytest.mark.unit
class TestCreateDefaultOrderingConfig:
    """Tests for create_default_ordering_config function."""

    def test_returns_object_with_allowed_attribute(self):
        """Should return object with 'allowed' attribute."""
        config = create_default_ordering_config()
        assert hasattr(config, "allowed")
        assert config.allowed == []

    def test_returns_object_with_default_attribute(self):
        """Should return object with 'default' attribute."""
        config = create_default_ordering_config()
        assert hasattr(config, "default")
        assert config.default == []


# =============================================================================
# Test map_filter_to_graphql_type
# =============================================================================

@pytest.mark.unit
class TestMapFilterToGraphqlType:
    """Tests for map_filter_to_graphql_type function."""

    def test_include_returns_list_of_id(self):
        """Should return List of ID for 'include' field."""
        import graphene

        field = Mock()
        result = map_filter_to_graphql_type(field, "include")

        # Check it's a List of ID
        assert result == graphene.List(graphene.ID)

    def test_default_is_string(self):
        """Should default to String type."""
        import graphene

        field = Mock()
        field.__class__.__name__ = "CharFilter"

        result = map_filter_to_graphql_type(field, "custom_field")

        assert result == graphene.String


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.unit
class TestFilterPipelineIntegration:
    """Integration tests for filter pipeline with multiple features."""

    def test_full_pipeline_execution(self):
        """Should execute full pipeline with all filter types."""
        mock_queryset = Mock()
        mock_queryset.filter = Mock(return_value=mock_queryset)
        mock_queryset.none = Mock(return_value=mock_queryset)

        mock_applicator = Mock()
        mock_applicator.apply_where_filter = Mock(return_value=mock_queryset)
        mock_applicator.apply_presets = Mock(return_value={"preset": True})
        mock_applicator._deep_merge = Mock(side_effect=lambda a, b: {**a, **b})

        context = QueryContext(
            model=Mock(__name__="TestModel"),
            queryset=mock_queryset,
            info=Mock(context=Mock(user=None)),
            kwargs={
                "where": {"name": {"eq": "test"}},
                "presets": ["active"],
                "include": ["1", "2"],
            },
            graphql_meta=Mock(),
            filter_applicator=mock_applicator,
            filter_class=None,
            ordering_config=None,
            settings=Mock(),
        )

        pipeline = QueryFilterPipeline(context)
        result = pipeline.apply_all()

        # Should have called apply_where_filter
        mock_applicator.apply_where_filter.assert_called_once()

        # Should have called apply_presets
        mock_applicator.apply_presets.assert_called_once()


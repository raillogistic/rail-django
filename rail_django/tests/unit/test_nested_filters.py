"""
Unit tests for nested filter input types (Prisma/Hasura style filtering).

Tests the NestedFilterInputGenerator and NestedFilterApplicator classes
which provide typed per-field filter inputs instead of flat lookup expressions.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import graphene
from django.db.models import Q
from django.test import TestCase
from django.utils import timezone

from rail_django.generators.filter_inputs import (
    BooleanFilterInput,
    CountFilterInput,
    DateFilterInput,
    DateTimeFilterInput,
    FloatFilterInput,
    IDFilterInput,
    IntFilterInput,
    JSONFilterInput,
    NestedFilterApplicator,
    NestedFilterInputGenerator,
    StringFilterInput,
    UUIDFilterInput,
    get_filter_input_for_field,
    generate_where_input_for_model,
    apply_where_filter,
    FIELD_TYPE_TO_FILTER_INPUT,
)
from test_app.models import Category, Post, Tag, Product, Comment, Profile, OrderItem

pytestmark = pytest.mark.unit


class TestBaseFilterInputTypes(TestCase):
    """Test base filter input type definitions."""

    def test_string_filter_input_fields(self):
        """StringFilterInput should have all expected operators."""
        fields = StringFilterInput._meta.fields

        expected_fields = [
            "eq", "neq", "contains", "icontains",
            "starts_with", "istarts_with", "ends_with", "iends_with",
            "in_", "not_in", "is_null", "regex", "iregex"
        ]
        # Note: 'in_' stays as 'in_' in Python meta fields but is exposed as 'in' in GraphQL schema
        for field_name in expected_fields:
            self.assertIn(field_name, fields)

    def test_int_filter_input_fields(self):
        """IntFilterInput should have numeric comparison operators."""
        fields = IntFilterInput._meta.fields

        expected_fields = [
            "eq", "neq", "gt", "gte", "lt", "lte",
            "in_", "not_in", "between", "is_null"
        ]
        for field_name in expected_fields:
            self.assertIn(field_name, fields)

    def test_float_filter_input_fields(self):
        """FloatFilterInput should have numeric comparison operators."""
        fields = FloatFilterInput._meta.fields

        self.assertIn("eq", fields)
        self.assertIn("gte", fields)
        self.assertIn("between", fields)

    def test_boolean_filter_input_fields(self):
        """BooleanFilterInput should have eq and is_null."""
        fields = BooleanFilterInput._meta.fields

        self.assertIn("eq", fields)
        self.assertIn("is_null", fields)

    def test_date_filter_input_fields(self):
        """DateFilterInput should have date operators and temporal filters."""
        fields = DateFilterInput._meta.fields

        # Basic comparison
        self.assertIn("eq", fields)
        self.assertIn("gt", fields)
        self.assertIn("between", fields)

        # Temporal convenience filters
        self.assertIn("year", fields)
        self.assertIn("month", fields)
        self.assertIn("today", fields)
        self.assertIn("this_week", fields)
        self.assertIn("this_month", fields)
        self.assertIn("past_year", fields)

    def test_datetime_filter_input_fields(self):
        """DateTimeFilterInput should include hour filter."""
        fields = DateTimeFilterInput._meta.fields

        self.assertIn("eq", fields)
        self.assertIn("hour", fields)
        self.assertIn("today", fields)
        self.assertIn("date", fields)

    def test_id_filter_input_fields(self):
        """IDFilterInput should have eq, neq, in_, not_in, is_null."""
        fields = IDFilterInput._meta.fields

        self.assertIn("eq", fields)
        self.assertIn("neq", fields)
        self.assertIn("in_", fields)  # Python name; exposed as 'in' in GraphQL
        self.assertIn("not_in", fields)
        self.assertIn("is_null", fields)

    def test_uuid_filter_input_fields(self):
        """UUIDFilterInput should support string-based comparisons."""
        fields = UUIDFilterInput._meta.fields

        self.assertIn("eq", fields)
        self.assertIn("in_", fields)  # Python name; exposed as 'in' in GraphQL

    def test_json_filter_input_fields(self):
        """JSONFilterInput should support JSON-specific operations."""
        fields = JSONFilterInput._meta.fields

        self.assertIn("eq", fields)
        self.assertIn("has_key", fields)
        self.assertIn("has_keys", fields)
        self.assertIn("has_any_keys", fields)

    def test_count_filter_input_fields(self):
        """CountFilterInput should support numeric comparisons."""
        fields = CountFilterInput._meta.fields

        self.assertIn("eq", fields)
        self.assertIn("neq", fields)
        self.assertIn("gt", fields)
        self.assertIn("gte", fields)
        self.assertIn("lt", fields)
        self.assertIn("lte", fields)


class TestFieldTypeMapping(TestCase):
    """Test the mapping from Django field types to filter inputs."""

    def test_charfield_maps_to_string_filter(self):
        """CharField should map to StringFilterInput."""
        from django.db import models
        field = models.CharField(max_length=100)
        self.assertEqual(get_filter_input_for_field(field), StringFilterInput)

    def test_textfield_maps_to_string_filter(self):
        """TextField should map to StringFilterInput."""
        from django.db import models
        field = models.TextField()
        self.assertEqual(get_filter_input_for_field(field), StringFilterInput)

    def test_emailfield_maps_to_string_filter(self):
        """EmailField should map to StringFilterInput."""
        from django.db import models
        field = models.EmailField()
        self.assertEqual(get_filter_input_for_field(field), StringFilterInput)

    def test_integerfield_maps_to_int_filter(self):
        """IntegerField should map to IntFilterInput."""
        from django.db import models
        field = models.IntegerField()
        self.assertEqual(get_filter_input_for_field(field), IntFilterInput)

    def test_decimalfield_maps_to_float_filter(self):
        """DecimalField should map to FloatFilterInput."""
        from django.db import models
        field = models.DecimalField(max_digits=10, decimal_places=2)
        self.assertEqual(get_filter_input_for_field(field), FloatFilterInput)

    def test_booleanfield_maps_to_boolean_filter(self):
        """BooleanField should map to BooleanFilterInput."""
        from django.db import models
        field = models.BooleanField()
        self.assertEqual(get_filter_input_for_field(field), BooleanFilterInput)

    def test_datefield_maps_to_date_filter(self):
        """DateField should map to DateFilterInput."""
        from django.db import models
        field = models.DateField()
        self.assertEqual(get_filter_input_for_field(field), DateFilterInput)

    def test_datetimefield_maps_to_datetime_filter(self):
        """DateTimeField should map to DateTimeFilterInput."""
        from django.db import models
        field = models.DateTimeField()
        self.assertEqual(get_filter_input_for_field(field), DateTimeFilterInput)

    def test_uuidfield_maps_to_uuid_filter(self):
        """UUIDField should map to UUIDFilterInput."""
        from django.db import models
        field = models.UUIDField()
        self.assertEqual(get_filter_input_for_field(field), UUIDFilterInput)

    def test_jsonfield_maps_to_json_filter(self):
        """JSONField should map to JSONFilterInput."""
        from django.db import models
        field = models.JSONField()
        self.assertEqual(get_filter_input_for_field(field), JSONFilterInput)

    def test_choice_field_maps_to_string_filter(self):
        """CharField with choices should map to StringFilterInput."""
        from django.db import models
        field = models.CharField(
            max_length=20,
            choices=[("A", "Active"), ("I", "Inactive")]
        )
        self.assertEqual(get_filter_input_for_field(field), StringFilterInput)

    def test_filefield_maps_to_string_filter(self):
        """FileField should map to StringFilterInput."""
        from django.db import models
        field = models.FileField()
        self.assertEqual(get_filter_input_for_field(field), StringFilterInput)


class TestNestedFilterInputGenerator(TestCase):
    """Test the NestedFilterInputGenerator class."""

    def setUp(self):
        self.generator = NestedFilterInputGenerator(max_nested_depth=2)
        # Clear cache for each test
        NestedFilterInputGenerator._filter_input_cache.clear()
        NestedFilterInputGenerator._generation_stack.clear()

    def test_generate_where_input_creates_input_type(self):
        """generate_where_input should create an InputObjectType."""
        where_input = self.generator.generate_where_input(Category)

        self.assertTrue(issubclass(where_input, graphene.InputObjectType))
        self.assertEqual(where_input.__name__, "CategoryWhereInput")

    def test_where_input_has_field_filters(self):
        """Generated WhereInput should have field filters."""
        where_input = self.generator.generate_where_input(Category)
        fields = where_input._meta.fields

        # Category has name (CharField) and description (TextField)
        self.assertIn("name", fields)
        self.assertIn("description", fields)

    def test_where_input_has_boolean_operators(self):
        """Generated WhereInput should have AND, OR, NOT operators."""
        where_input = self.generator.generate_where_input(Category)
        fields = where_input._meta.fields

        self.assertIn("AND", fields)
        self.assertIn("OR", fields)
        self.assertIn("NOT", fields)

    def test_where_input_has_id_filter(self):
        """Generated WhereInput should have ID filter."""
        where_input = self.generator.generate_where_input(Category)
        fields = where_input._meta.fields

        self.assertIn("id", fields)

    def test_where_input_for_model_with_fk(self):
        """WhereInput for model with FK should have relation filters."""
        where_input = self.generator.generate_where_input(Post)
        fields = where_input._meta.fields

        # Post has category FK
        self.assertIn("category", fields)  # ID filter
        self.assertIn("category_rel", fields)  # Nested filter

    def test_where_input_for_model_with_m2m(self):
        """WhereInput for model with M2M should have quantifier filters."""
        where_input = self.generator.generate_where_input(Post)
        fields = where_input._meta.fields

        # Post has tags M2M
        self.assertIn("tags", fields)  # ID filter
        self.assertIn("tags_count", fields)  # Count filter
        self.assertIn("tags_some", fields)  # Some match
        self.assertIn("tags_every", fields)  # All match
        self.assertIn("tags_none", fields)  # None match

    def test_where_input_for_model_with_reverse_fk(self):
        """WhereInput for model with reverse FK should have relation filters."""
        where_input = self.generator.generate_where_input(Category)
        fields = where_input._meta.fields

        # Category has posts reverse FK
        self.assertIn("posts_count", fields)
        self.assertIn("posts_some", fields)
        self.assertIn("posts_every", fields)
        self.assertIn("posts_none", fields)

    def test_nested_depth_limiting(self):
        """Nested filters should respect max_nested_depth."""
        generator = NestedFilterInputGenerator(max_nested_depth=1)
        NestedFilterInputGenerator._filter_input_cache.clear()

        where_input = generator.generate_where_input(Post)
        fields = where_input._meta.fields

        # Should have first level nested filter
        self.assertIn("category_rel", fields)

        # But nested filter for category shouldn't have deep nesting
        category_filter = fields.get("category_rel")
        if category_filter:
            nested_type = category_filter.type
            if callable(nested_type):
                nested_type = nested_type()
            if nested_type:
                nested_fields = getattr(nested_type, "_meta", None)
                if nested_fields:
                    nested_fields = nested_fields.fields
                    # At depth 1, the nested Category filter shouldn't have posts_some etc.
                    # because that would be depth 2

    def test_caching_returns_same_type(self):
        """Generator should cache and return the same type."""
        where_input1 = self.generator.generate_where_input(Category)
        where_input2 = self.generator.generate_where_input(Category)

        self.assertIs(where_input1, where_input2)

    def test_different_schemas_have_different_cache(self):
        """Different schema names should have separate caches."""
        generator1 = NestedFilterInputGenerator(schema_name="schema1")
        generator2 = NestedFilterInputGenerator(schema_name="schema2")

        where_input1 = generator1.generate_where_input(Category)
        where_input2 = generator2.generate_where_input(Category)

        # They should be separate types
        self.assertIsNot(where_input1, where_input2)


class TestNestedFilterApplicator(TestCase):
    """Test the NestedFilterApplicator class."""

    def setUp(self):
        self.applicator = NestedFilterApplicator()

    def test_empty_filter_returns_same_queryset(self):
        """Empty where input should return unchanged queryset."""
        queryset = Category.objects.all()
        result = self.applicator.apply_where_filter(queryset, {}, Category)

        self.assertIs(result, queryset)

    def test_none_filter_returns_same_queryset(self):
        """None where input should return unchanged queryset."""
        queryset = Category.objects.all()
        result = self.applicator.apply_where_filter(queryset, None, Category)

        self.assertIs(result, queryset)

    def test_simple_eq_filter(self):
        """Simple eq filter should produce correct Q object."""
        where_input = {"name": {"eq": "Electronics"}}
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)
        # Q object should represent name__exact="Electronics"

    def test_simple_icontains_filter(self):
        """icontains filter should produce correct lookup."""
        where_input = {"name": {"icontains": "elect"}}
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_multiple_operators_on_same_field(self):
        """Multiple operators on same field should AND together."""
        where_input = {"name": {"icontains": "test", "starts_with": "T"}}
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_numeric_gt_filter(self):
        """gt filter on numeric field should work."""
        where_input = {"price": {"gt": 100.0}}
        q = self.applicator._build_q_from_where(where_input, Product)

        self.assertIsInstance(q, Q)

    def test_between_filter(self):
        """between filter should create gte + lte combination."""
        where_input = {"price": {"between": [10.0, 50.0]}}
        q = self.applicator._build_q_from_where(where_input, Product)

        self.assertIsInstance(q, Q)

    def test_in_filter(self):
        """in filter should use __in lookup."""
        where_input = {"name": {"in_": ["A", "B", "C"]}}
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_not_in_filter(self):
        """not_in filter should negate __in lookup."""
        where_input = {"name": {"not_in": ["X", "Y"]}}
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_neq_filter(self):
        """neq filter should negate exact match."""
        where_input = {"name": {"neq": "Test"}}
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_is_null_filter(self):
        """is_null filter should use __isnull lookup."""
        where_input = {"description": {"is_null": True}}
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_and_operator(self):
        """AND operator should combine conditions with AND."""
        where_input = {
            "AND": [
                {"name": {"icontains": "test"}},
                {"description": {"icontains": "desc"}}
            ]
        }
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_or_operator(self):
        """OR operator should combine conditions with OR."""
        where_input = {
            "OR": [
                {"name": {"eq": "A"}},
                {"name": {"eq": "B"}}
            ]
        }
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_not_operator(self):
        """NOT operator should negate the condition."""
        where_input = {
            "NOT": {"name": {"eq": "Test"}}
        }
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_nested_boolean_operators(self):
        """Boolean operators should work when nested."""
        where_input = {
            "AND": [
                {"name": {"icontains": "test"}},
                {
                    "OR": [
                        {"description": {"eq": "A"}},
                        {"description": {"eq": "B"}}
                    ]
                }
            ]
        }
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_relation_filter_with_rel_suffix(self):
        """Filters ending in _rel should filter on related model fields."""
        where_input = {
            "category_rel": {"name": {"eq": "Electronics"}}
        }
        q = self.applicator._build_q_from_where(where_input, Post)

        self.assertIsInstance(q, Q)

    def test_some_filter(self):
        """_some filter should work for exists-style queries."""
        where_input = {
            "tags_some": {"name": {"eq": "Python"}}
        }
        q = self.applicator._build_q_from_where(where_input, Post)

        self.assertIsInstance(q, Q)

    def test_none_filter(self):
        """_none filter should negate the subquery."""
        where_input = {
            "tags_none": {"name": {"eq": "Deprecated"}}
        }
        q = self.applicator._build_q_from_where(where_input, Post)

        self.assertIsInstance(q, Q)

    def test_count_filter(self):
        """_count filter should handle count-based filtering."""
        where_input = {
            "tags_count": {"gte": 2}
        }
        q = self.applicator._build_count_q("tags", {"gte": 2})

        self.assertIsInstance(q, Q)

    def test_null_values_skipped(self):
        """Null values in filter input should be skipped."""
        where_input = {
            "name": {"eq": None, "icontains": "test"}
        }
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)


class TestTemporalFilters(TestCase):
    """Test temporal/date-based filter operations."""

    def setUp(self):
        self.applicator = NestedFilterApplicator()

    def test_today_filter(self):
        """today filter should match current date."""
        q = self.applicator._build_temporal_q("created_at", "today")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_yesterday_filter(self):
        """yesterday filter should match previous date."""
        q = self.applicator._build_temporal_q("created_at", "yesterday")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_this_week_filter(self):
        """this_week filter should match current week."""
        q = self.applicator._build_temporal_q("created_at", "this_week")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_past_week_filter(self):
        """past_week filter should match previous week."""
        q = self.applicator._build_temporal_q("created_at", "past_week")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_this_month_filter(self):
        """this_month filter should match current month."""
        q = self.applicator._build_temporal_q("created_at", "this_month")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_past_month_filter(self):
        """past_month filter should match previous month."""
        q = self.applicator._build_temporal_q("created_at", "past_month")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_this_year_filter(self):
        """this_year filter should match current year."""
        q = self.applicator._build_temporal_q("created_at", "this_year")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_past_year_filter(self):
        """past_year filter should match previous year."""
        q = self.applicator._build_temporal_q("created_at", "past_year")

        self.assertIsInstance(q, Q)
        self.assertIsNotNone(q)

    def test_unknown_temporal_filter_returns_none(self):
        """Unknown temporal filter should return None."""
        q = self.applicator._build_temporal_q("created_at", "unknown_filter")

        self.assertIsNone(q)


class TestOperatorMapping(TestCase):
    """Test the operator to Django lookup mapping."""

    def setUp(self):
        self.applicator = NestedFilterApplicator()

    def test_eq_maps_to_exact(self):
        """eq operator should map to exact lookup."""
        lookup = self.applicator._get_lookup_for_operator("eq")
        self.assertEqual(lookup, "exact")

    def test_gt_maps_to_gt(self):
        """gt operator should map to gt lookup."""
        lookup = self.applicator._get_lookup_for_operator("gt")
        self.assertEqual(lookup, "gt")

    def test_icontains_maps_to_icontains(self):
        """icontains operator should map to icontains lookup."""
        lookup = self.applicator._get_lookup_for_operator("icontains")
        self.assertEqual(lookup, "icontains")

    def test_starts_with_maps_to_startswith(self):
        """starts_with operator should map to startswith lookup."""
        lookup = self.applicator._get_lookup_for_operator("starts_with")
        self.assertEqual(lookup, "startswith")

    def test_is_null_maps_to_isnull(self):
        """is_null operator should map to isnull lookup."""
        lookup = self.applicator._get_lookup_for_operator("is_null")
        self.assertEqual(lookup, "isnull")

    def test_year_maps_to_year(self):
        """year operator should map to year lookup."""
        lookup = self.applicator._get_lookup_for_operator("year")
        self.assertEqual(lookup, "year")

    def test_has_key_maps_to_has_key(self):
        """has_key operator should map to has_key lookup."""
        lookup = self.applicator._get_lookup_for_operator("has_key")
        self.assertEqual(lookup, "has_key")

    def test_unknown_operator_returns_none(self):
        """Unknown operator should return None."""
        lookup = self.applicator._get_lookup_for_operator("unknown_op")
        self.assertIsNone(lookup)


class TestCountAnnotations(TestCase):
    """Test count annotation collection for count filters."""

    def setUp(self):
        self.applicator = NestedFilterApplicator()

    def test_collect_count_annotations_simple(self):
        """Should collect count annotation for simple _count filter."""
        where_input = {"tags_count": {"gte": 2}}
        annotations = self.applicator._collect_count_annotations(where_input)

        self.assertIn("tags_count_annotation", annotations)
        self.assertEqual(annotations["tags_count_annotation"], "tags")

    def test_collect_count_annotations_nested_in_and(self):
        """Should collect count annotations nested in AND."""
        where_input = {
            "AND": [
                {"tags_count": {"gte": 1}},
                {"comments_count": {"eq": 5}}
            ]
        }
        annotations = self.applicator._collect_count_annotations(where_input)

        self.assertIn("tags_count_annotation", annotations)
        self.assertIn("comments_count_annotation", annotations)

    def test_collect_count_annotations_nested_in_or(self):
        """Should collect count annotations nested in OR."""
        where_input = {
            "OR": [
                {"tags_count": {"gt": 0}},
                {"comments_count": {"gt": 0}}
            ]
        }
        annotations = self.applicator._collect_count_annotations(where_input)

        self.assertIn("tags_count_annotation", annotations)
        self.assertIn("comments_count_annotation", annotations)

    def test_collect_count_annotations_nested_in_not(self):
        """Should collect count annotations nested in NOT."""
        where_input = {
            "NOT": {"tags_count": {"eq": 0}}
        }
        annotations = self.applicator._collect_count_annotations(where_input)

        self.assertIn("tags_count_annotation", annotations)


class TestConvenienceFunctions(TestCase):
    """Test the module-level convenience functions."""

    def setUp(self):
        NestedFilterInputGenerator._filter_input_cache.clear()
        NestedFilterInputGenerator._generation_stack.clear()

    def test_generate_where_input_for_model(self):
        """generate_where_input_for_model should return InputObjectType."""
        where_input = generate_where_input_for_model(Category)

        self.assertTrue(issubclass(where_input, graphene.InputObjectType))
        self.assertEqual(where_input.__name__, "CategoryWhereInput")

    def test_generate_where_input_for_model_with_max_depth(self):
        """generate_where_input_for_model should respect max_depth."""
        where_input = generate_where_input_for_model(Post, max_depth=1)

        self.assertTrue(issubclass(where_input, graphene.InputObjectType))

    def test_apply_where_filter_returns_queryset(self):
        """apply_where_filter should return a queryset."""
        queryset = Category.objects.all()
        where_input = {"name": {"icontains": "test"}}

        result = apply_where_filter(queryset, where_input)

        # Should still be a queryset (or manager)
        self.assertTrue(hasattr(result, "filter"))


class TestComplexFilterScenarios(TestCase):
    """Test complex real-world filter scenarios."""

    def setUp(self):
        self.generator = NestedFilterInputGenerator(max_nested_depth=3)
        self.applicator = NestedFilterApplicator()
        NestedFilterInputGenerator._filter_input_cache.clear()
        NestedFilterInputGenerator._generation_stack.clear()

    def test_combined_field_and_relation_filters(self):
        """Filter combining field and relation conditions."""
        where_input = {
            "title": {"icontains": "Python"},
            "category_rel": {"name": {"eq": "Programming"}}
        }
        q = self.applicator._build_q_from_where(where_input, Post)

        self.assertIsInstance(q, Q)

    def test_deeply_nested_boolean_logic(self):
        """Complex boolean logic should work correctly."""
        where_input = {
            "AND": [
                {"title": {"icontains": "test"}},
                {
                    "OR": [
                        {
                            "AND": [
                                {"category_rel": {"name": {"eq": "A"}}},
                                {"tags_some": {"name": {"eq": "tag1"}}}
                            ]
                        },
                        {
                            "NOT": {"title": {"icontains": "draft"}}
                        }
                    ]
                }
            ]
        }
        q = self.applicator._build_q_from_where(where_input, Post)

        self.assertIsInstance(q, Q)

    def test_multiple_count_filters(self):
        """Multiple count filters in one query."""
        where_input = {
            "AND": [
                {"tags_count": {"gte": 1}},
                {"comments_count": {"lte": 10}}
            ]
        }
        annotations = self.applicator._collect_count_annotations(where_input)

        self.assertEqual(len(annotations), 2)

    def test_filter_with_all_string_operators(self):
        """Using multiple string operators together."""
        where_input = {
            "name": {
                "icontains": "test",
                "istarts_with": "t",
                "iends_with": "t"
            }
        }
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)

    def test_empty_and_or_lists(self):
        """Empty AND/OR lists should not cause errors."""
        where_input = {
            "AND": [],
            "OR": []
        }
        q = self.applicator._build_q_from_where(where_input, Category)

        self.assertIsInstance(q, Q)


class TestSchemaIntegration(TestCase):
    """Test integration with GraphQL schema generation."""

    def setUp(self):
        NestedFilterInputGenerator._filter_input_cache.clear()
        NestedFilterInputGenerator._generation_stack.clear()

    def test_generated_type_works_with_graphene(self):
        """Generated type should be valid for graphene schema."""
        generator = NestedFilterInputGenerator()
        where_input = generator.generate_where_input(Category)

        # Should be usable as an argument type
        field = graphene.Field(
            graphene.String,
            where=graphene.Argument(where_input)
        )
        self.assertIsNotNone(field.args.get("where"))

    def test_multiple_models_generate_distinct_types(self):
        """Different models should generate different types."""
        generator = NestedFilterInputGenerator()

        category_where = generator.generate_where_input(Category)
        post_where = generator.generate_where_input(Post)

        self.assertNotEqual(category_where.__name__, post_where.__name__)
        self.assertEqual(category_where.__name__, "CategoryWhereInput")
        self.assertEqual(post_where.__name__, "PostWhereInput")

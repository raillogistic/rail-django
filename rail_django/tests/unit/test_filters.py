"""
Unit tests for advanced filter generation and inputs.
"""

import pytest
from django.test import TestCase

from rail_django.generators.filters import AdvancedFilterGenerator
from test_app.models import Post

pytestmark = pytest.mark.unit


class TestAdvancedFilterGenerator(TestCase):
    def setUp(self):
        self.generator = AdvancedFilterGenerator(max_nested_depth=2)

    def test_filter_set_includes_nested_and_quick_filters(self):
        filter_set = self.generator.generate_filter_set(Post)
        filters = filter_set.base_filters

        self.assertIn("title__icontains", filters)
        self.assertIn("category__name__icontains", filters)
        self.assertIn("tags__name__icontains", filters)
        self.assertIn("quick", filters)
        self.assertIn("include", filters)

    def test_complex_filter_input_exposes_boolean_ops(self):
        input_type = self.generator.generate_complex_filter_input(Post)
        fields = input_type._meta.fields

        self.assertIn("AND", fields)
        self.assertIn("OR", fields)
        self.assertIn("NOT", fields)
        self.assertIn("title__icontains", fields)

    def test_apply_complex_filters_returns_same_queryset_for_empty(self):
        queryset = Post.objects.all()
        filtered = self.generator.apply_complex_filters(queryset, {})
        self.assertIs(filtered, queryset)

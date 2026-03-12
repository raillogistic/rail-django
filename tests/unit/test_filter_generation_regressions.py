from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db.models import Q
from django.test import TestCase

from rail_django.generators.filters import (
    MAX_ALLOWED_NESTED_DEPTH,
    NestedFilterApplicator,
    NestedFilterInputGenerator,
)
from test_app.models import Category, OrderItem, Product

pytestmark = pytest.mark.unit


def _build_graphql_meta(*, exposed_fields=None, filter_fields=None):
    exposed = set(exposed_fields or [])

    def should_expose_field(field_name, for_input=False):  # noqa: ARG001
        return field_name in exposed

    return SimpleNamespace(
        filtering=SimpleNamespace(fields=filter_fields or {}),
        should_expose_field=should_expose_field,
    )


class TestFilterGenerationRegressions(TestCase):
    def test_generator_respects_field_exposure_and_filter_roots(self):
        generator = NestedFilterInputGenerator(schema_name="filter_visibility_regression")
        graphql_meta = _build_graphql_meta(
            exposed_fields={"name", "id"},
            filter_fields={"name": object()},
        )

        with patch("rail_django.core.meta.get_model_graphql_meta", return_value=graphql_meta):
            generator.clear_cache()
            where_input = generator.generate_where_input(Category)

        fields = where_input._meta.fields
        self.assertIn("name", fields)
        self.assertNotIn("description", fields)
        self.assertNotIn("posts_agg", fields)
        self.assertNotIn("posts_count", fields)

    def test_applicator_blocks_hidden_direct_field_filters(self):
        applicator = NestedFilterApplicator(schema_name="filter_visibility_regression")
        graphql_meta = _build_graphql_meta(
            exposed_fields={"name", "id"},
            filter_fields={"name": object()},
        )

        with patch("rail_django.core.meta.get_model_graphql_meta", return_value=graphql_meta):
            q = applicator._build_field_q("description", {"eq": "secret"}, Category)

        self.assertEqual(q, Q())

    def test_generator_rejects_depth_values_above_hard_limit(self):
        with self.assertRaises(ValueError):
            NestedFilterInputGenerator(
                schema_name="depth_limit_regression",
                max_nested_depth=MAX_ALLOWED_NESTED_DEPTH + 1,
            )

    def test_subquery_json_filters_use_nested_where_engine(self):
        applicator = NestedFilterApplicator(schema_name="subquery_regression")
        subquery_filter = {
            "relation": "order_items",
            "field": "unit_price",
            "filter": '{"unit_price": {"between": [10, 20]}}',
            "gt": 15,
        }

        with patch.object(
            applicator,
            "_build_q_from_where",
            wraps=applicator._build_q_from_where,
        ) as build_q:
            _, annotations = applicator._build_subquery_filter_q(subquery_filter, Product)

        self.assertTrue(annotations)
        self.assertTrue(build_q.called)
        related_where, related_model = build_q.call_args.args[:2]
        self.assertEqual(related_where, {"unit_price": {"between": [10, 20]}})
        self.assertIs(related_model, OrderItem)

    def test_exists_json_filters_enforce_complexity_limits(self):
        applicator = NestedFilterApplicator(schema_name="exists_regression")
        applicator.filtering_settings = SimpleNamespace(
            max_filter_depth=10,
            max_filter_clauses=3,
        )
        clauses = ",".join(
            f'"field{i}": {{"eq": {i}}}' for i in range(5)
        )
        exists_filter = {
            "relation": "order_items",
            "filter": "{" + clauses + "}",
            "exists": True,
        }

        q = applicator._build_exists_filter_q(exists_filter, Product)

        self.assertEqual(q.children, [("pk__in", [])])

    def test_day_of_year_extract_filter_builds_annotation(self):
        applicator = NestedFilterApplicator(schema_name="extract_regression")

        q, annotations = applicator._build_date_extract_filter_q(
            "date_creation",
            {"day_of_year": {"eq": 42}},
        )

        self.assertNotEqual(q, Q())
        self.assertIn("_date_creation_extract_day_of_year", annotations)

    def test_field_compare_rejects_hidden_fields(self):
        applicator = NestedFilterApplicator(schema_name="compare_regression")
        graphql_meta = _build_graphql_meta(
            exposed_fields={"name", "price", "id"},
            filter_fields={"price": object()},
        )

        with patch("rail_django.core.meta.get_model_graphql_meta", return_value=graphql_meta):
            q = applicator._build_field_compare_q(
                {"left": "price", "operator": "gt", "right": "cost_price"},
                Product,
            )

        self.assertEqual(q, Q())

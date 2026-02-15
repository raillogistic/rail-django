import pytest
from graphql import GraphQLError

from rail_django.extensions.form.automation.computed import compute_field
from rail_django.extensions.form.automation.conditional import evaluate_condition
from rail_django.extensions.form.automation.dependencies import detect_cycles
from rail_django.extensions.form.normalization.input_normalizer import normalize_values
from rail_django.extensions.form.normalization.type_coercion import coerce_value

pytestmark = pytest.mark.unit


def test_evaluate_condition_supports_single_and_grouped_rules():
    values = {"price": 42, "status": "active", "meta": {"flag": True}}

    assert evaluate_condition(
        {"field": "price", "operator": "GTE", "value": 40},
        values,
    )
    assert evaluate_condition(
        {
            "logic": "AND",
            "conditions": [
                {"field": "price", "operator": "GT", "value": 10},
                {"field": "status", "operator": "EQ", "value": "active"},
            ],
        },
        values,
    )
    assert not evaluate_condition(
        {
            "logic": "OR",
            "conditions": [
                {"field": "price", "operator": "LT", "value": 10},
                {"field": "status", "operator": "EQ", "value": "draft"},
            ],
        },
        values,
    )


def test_compute_field_supports_path_template_and_expression_modes():
    values = {"price": 10, "qty": 3, "profile": {"first_name": "Ada", "last_name": "Lovelace"}}

    assert compute_field("price", values) == 10
    assert compute_field("price * qty", values) == 30
    assert (
        compute_field(
            "{{profile.first_name}} {{profile.last_name}}",
            values,
        )
        == "Ada Lovelace"
    )


def test_detect_cycles_handles_mapping_graph_input():
    assert detect_cycles({"a": ["b"], "b": ["c"], "c": []}) is False
    assert detect_cycles({"a": ["b"], "b": ["c"], "c": ["a"]}) is True


def test_coerce_value_normalizes_common_scalar_and_nested_inputs():
    source = {
        "enabled": "true",
        "count": "12",
        "ratio": "12.5",
        "payload": '{"status":"ok"}',
        "list": ["false", "7"],
    }
    result = coerce_value(source)

    assert result["enabled"] is True
    assert result["count"] == 12
    assert result["ratio"] == 12.5
    assert result["payload"] == {"status": "ok"}
    assert result["list"] == [False, 7]


def test_normalize_values_supports_relation_aliases_and_policy_checks():
    config = {
        "relations": [
            {
                "name": "category",
                "field_name": "category",
                "path": "category",
            }
        ],
        "relation_policies": {
            "category": {"blocked_actions": ["DELETE"]},
        },
    }
    assert normalize_values({"category": [1, 2]}, config) == {
        "category": {"connect": [1, 2]}
    }

    with pytest.raises(GraphQLError):
        normalize_values(
            {"category": {"delete": [1]}},
            config,
        )

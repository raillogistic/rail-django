"""
Unit tests for reporting helper functions.
"""

import pytest

from rail_django.extensions.reporting import (
    ReportingError,
    _hash_query_payload,
    _safe_formula_eval,
    _safe_identifier,
    _safe_query_expression,
    _to_filter_list,
)

pytestmark = pytest.mark.unit


def test_safe_formula_eval_supports_arithmetic():
    result = _safe_formula_eval("a + b * 2", {"a": 2, "b": 3})
    assert result == 8


def test_safe_formula_eval_rejects_unsafe_nodes():
    with pytest.raises(ReportingError):
        _safe_formula_eval("__import__('os').system('echo bad')", {})


def test_safe_query_expression_rejects_unknown_names():
    with pytest.raises(ReportingError):
        _safe_query_expression("amount + secret", allowed_names={"amount"})


def test_hash_query_payload_is_stable():
    first = _hash_query_payload({"a": 1, "b": 2})
    second = _hash_query_payload({"b": 2, "a": 1})
    assert first == second
    assert len(first) == 24


def test_safe_identifier_normalizes():
    assert _safe_identifier(" 123 bad name ", fallback="field") == "field_123_bad_name"


def test_to_filter_list_normalizes_items():
    filters = _to_filter_list(
        [
            {"field": "nom_client", "lookup": "icontains", "value": "alpha"},
            {"field": "", "value": "skip"},
        ]
    )
    assert len(filters) == 1
    assert filters[0].field == "nom_client"



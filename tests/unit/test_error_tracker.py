"""Unit tests for error tracker internals."""

import pytest

from rail_django.debugging.error_tracking.tracker import ErrorTracker
from rail_django.debugging.error_tracking.types import ErrorContext

pytestmark = pytest.mark.unit


def test_generate_error_id_changes_with_context():
    tracker = ErrorTracker()

    bare = tracker._generate_error_id("failure")
    contextual = tracker._generate_error_id(
        "failure",
        ErrorContext(operation_name="UpdateOrder", field_path="order.total"),
    )

    assert len(bare) == 12
    assert len(contextual) == 12
    assert bare != contextual


def test_create_pattern_key_normalizes_numeric_noise():
    tracker = ErrorTracker()

    first = tracker._create_pattern_key("Order 123 failed for 12345678")
    second = tracker._create_pattern_key("Order 999 failed for 87654321")

    assert len(first) == 8
    assert first == second

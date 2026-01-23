"""
Unit tests for validation extension queries.
"""

import pytest

from rail_django.extensions.validation import ValidationQuery

pytestmark = pytest.mark.unit


def test_validation_query_accepts_valid_email():
    query = ValidationQuery()
    result = query.resolve_validate_field(None, field_name="email", value="user@example.com")
    assert result.is_valid is True
    assert result.error_message is None


def test_validation_query_rejects_invalid_email():
    query = ValidationQuery()
    result = query.resolve_validate_field(None, field_name="email", value="not-an-email")
    assert result.is_valid is False
    assert result.error_message



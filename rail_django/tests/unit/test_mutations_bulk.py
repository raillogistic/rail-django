"""
Unit tests for bulk mutation operations.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError

pytestmark = pytest.mark.unit


class TestBulkSizeValidation:
    """Tests for bulk operation size limit validation."""

    def test_check_bulk_size_limit_under_limit(self):
        """Inputs under the limit should not raise."""
        from rail_django.generators.mutations_utils import check_bulk_size_limit

        # Should not raise for inputs under the limit
        check_bulk_size_limit([1, 2, 3], max_size=10)

    def test_check_bulk_size_limit_at_limit(self):
        """Inputs at exactly the limit should not raise."""
        from rail_django.generators.mutations_utils import check_bulk_size_limit

        check_bulk_size_limit(list(range(100)), max_size=100)

    def test_check_bulk_size_limit_over_limit_raises(self):
        """Inputs over the limit should raise BulkSizeError."""
        from rail_django.generators.mutations_utils import check_bulk_size_limit
        from rail_django.generators.mutations_exceptions import BulkSizeError

        with pytest.raises(BulkSizeError) as exc_info:
            check_bulk_size_limit(list(range(101)), max_size=100)

        assert exc_info.value.max_size == 100
        assert exc_info.value.actual_size == 101

    def test_check_bulk_size_limit_default_size(self):
        """Default size limit should be used when not specified."""
        from rail_django.generators.mutations_utils import (
            check_bulk_size_limit,
            DEFAULT_MAX_BULK_SIZE,
        )
        from rail_django.generators.mutations_exceptions import BulkSizeError

        # Should not raise for default limit
        check_bulk_size_limit(list(range(DEFAULT_MAX_BULK_SIZE)))

        # Should raise for over default limit
        with pytest.raises(BulkSizeError):
            check_bulk_size_limit(list(range(DEFAULT_MAX_BULK_SIZE + 1)))


class TestInputSanitization:
    """Tests for input data sanitization."""

    def test_sanitize_input_data_strips_whitespace(self):
        """String values should have whitespace stripped."""
        from rail_django.generators.mutations_utils import sanitize_input_data

        result = sanitize_input_data({"name": "  test  ", "description": "  hello  "})
        assert result["name"] == "test"
        assert result["description"] == "hello"

    def test_sanitize_input_data_converts_id_to_string(self):
        """ID field should be converted to string."""
        from rail_django.generators.mutations_utils import sanitize_input_data

        result = sanitize_input_data({"id": 123, "name": "test"})
        assert result["id"] == "123"
        assert isinstance(result["id"], str)

    def test_sanitize_input_data_handles_nested_dicts(self):
        """Nested dictionaries should be recursively sanitized."""
        from rail_django.generators.mutations_utils import sanitize_input_data

        result = sanitize_input_data({
            "name": "  test  ",
            "nested": {"inner": "  value  ", "id": 456}
        })
        assert result["name"] == "test"
        assert result["nested"]["inner"] == "value"
        assert result["nested"]["id"] == "456"

    def test_sanitize_input_data_handles_lists(self):
        """Lists with nested dicts should be sanitized."""
        from rail_django.generators.mutations_utils import sanitize_input_data

        result = sanitize_input_data({
            "items": [
                {"name": "  item1  "},
                {"name": "  item2  "},
            ]
        })
        assert result["items"][0]["name"] == "item1"
        assert result["items"][1]["name"] == "item2"

    def test_sanitize_input_data_empty_input(self):
        """Empty input should return empty dict."""
        from rail_django.generators.mutations_utils import sanitize_input_data

        assert sanitize_input_data({}) == {}
        assert sanitize_input_data(None) == {}


class TestEnumNormalization:
    """Tests for enum input normalization."""

    def test_normalize_enum_inputs_extracts_value(self):
        """Enum objects should have their value extracted."""
        from rail_django.generators.mutations_utils import normalize_enum_inputs

        class MockEnum:
            value = "active"

        mock_model = MagicMock()
        mock_field = MagicMock()
        mock_field.name = "status"
        mock_field.choices = [("active", "Active"), ("inactive", "Inactive")]
        mock_model._meta.get_fields.return_value = [mock_field]

        result = normalize_enum_inputs({"status": MockEnum()}, mock_model)
        assert result["status"] == "active"

    def test_normalize_enum_inputs_preserves_regular_values(self):
        """Regular values should be preserved."""
        from rail_django.generators.mutations_utils import normalize_enum_inputs

        mock_model = MagicMock()
        mock_model._meta.get_fields.return_value = []

        result = normalize_enum_inputs(
            {"name": "test", "count": 5},
            mock_model
        )
        assert result["name"] == "test"
        assert result["count"] == 5


class TestPrimaryKeyValidation:
    """Tests for primary key validation and normalization."""

    def test_validate_and_normalize_pk_integer(self):
        """Integer PKs should be returned as-is."""
        from rail_django.generators.mutations_utils import validate_and_normalize_pk

        assert validate_and_normalize_pk(123, "id") == 123

    def test_validate_and_normalize_pk_numeric_string(self):
        """Numeric string PKs should be converted to int."""
        from rail_django.generators.mutations_utils import validate_and_normalize_pk

        assert validate_and_normalize_pk("456", "id") == 456

    def test_validate_and_normalize_pk_uuid_string(self):
        """UUID string PKs should be kept as strings."""
        from rail_django.generators.mutations_utils import validate_and_normalize_pk
        import uuid

        test_uuid = str(uuid.uuid4())
        result = validate_and_normalize_pk(test_uuid, "id")
        assert result == test_uuid

    def test_validate_and_normalize_pk_none(self):
        """None should return None."""
        from rail_django.generators.mutations_utils import validate_and_normalize_pk

        assert validate_and_normalize_pk(None, "id") is None

    def test_validate_and_normalize_pk_model_instance(self):
        """Model instance should return its PK."""
        from rail_django.generators.mutations_utils import validate_and_normalize_pk

        mock_instance = MagicMock()
        mock_instance.pk = 789
        result = validate_and_normalize_pk(mock_instance, "id")
        assert result == 789


class TestErrorSanitization:
    """Tests for error message sanitization."""

    def test_sanitize_error_message_validation_error(self):
        """ValidationError messages should be returned as-is."""
        from rail_django.generators.mutations_utils import sanitize_error_message

        exc = ValidationError("Field is required")
        result = sanitize_error_message(exc, "create", "TestModel")
        assert "Field is required" in result

    def test_sanitize_error_message_permission_denied(self):
        """PermissionDenied messages should be returned as-is."""
        from rail_django.generators.mutations_utils import sanitize_error_message

        exc = PermissionDenied("Access denied")
        result = sanitize_error_message(exc, "update", "TestModel")
        assert "Access denied" in result

    def test_sanitize_error_message_generic_exception(self):
        """Generic exceptions should return sanitized message."""
        from rail_django.generators.mutations_utils import sanitize_error_message

        exc = Exception("Internal database error with sensitive info")
        result = sanitize_error_message(exc, "delete", "TestModel")
        # Should not contain the sensitive info
        assert "sensitive info" not in result
        assert "error occurred" in result.lower() or "processing" in result.lower()


class TestMutationExceptions:
    """Tests for custom mutation exceptions."""

    def test_nested_depth_error(self):
        """NestedDepthError should contain depth information."""
        from rail_django.generators.mutations_exceptions import NestedDepthError

        error = NestedDepthError(max_depth=5, current_depth=6)
        assert error.max_depth == 5
        assert error.current_depth == 6
        assert "5" in str(error)
        assert "6" in str(error)
        assert error.code == "DEPTH_EXCEEDED"

    def test_bulk_size_error(self):
        """BulkSizeError should contain size information."""
        from rail_django.generators.mutations_exceptions import BulkSizeError

        error = BulkSizeError(max_size=100, actual_size=150)
        assert error.max_size == 100
        assert error.actual_size == 150
        assert "100" in str(error)
        assert "150" in str(error)
        assert error.code == "BULK_SIZE_EXCEEDED"

    def test_circular_reference_error(self):
        """CircularReferenceError should contain model information."""
        from rail_django.generators.mutations_exceptions import CircularReferenceError

        error = CircularReferenceError(model_name="Author", path="books.author")
        assert error.model_name == "Author"
        assert error.path == "books.author"
        assert "Author" in str(error)
        assert error.code == "CIRCULAR_REFERENCE"

    def test_invalid_id_format_error(self):
        """InvalidIdFormatError should contain field and value."""
        from rail_django.generators.mutations_exceptions import InvalidIdFormatError

        error = InvalidIdFormatError(field_name="author_id", value="invalid")
        assert error.field == "author_id"
        assert error.value == "invalid"
        assert "author_id" in str(error)
        assert error.code == "INVALID_ID_FORMAT"

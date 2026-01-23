"""
Unit tests for nested mutation operations.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import ValidationError

pytestmark = pytest.mark.unit


class TestNestedDepthLimiting:
    """Tests for nested operation depth limiting."""

    def test_check_nested_depth_under_limit(self):
        """Depth under the limit should not raise."""
        from rail_django.generators.mutations.utils import check_nested_depth

        # Should not raise
        check_nested_depth(5, max_depth=10)

    def test_check_nested_depth_at_limit(self):
        """Depth at exactly the limit should not raise."""
        from rail_django.generators.mutations.utils import check_nested_depth

        check_nested_depth(10, max_depth=10)

    def test_check_nested_depth_over_limit_raises(self):
        """Depth over the limit should raise NestedDepthError."""
        from rail_django.generators.mutations.utils import check_nested_depth
        from rail_django.generators.mutations.exceptions import NestedDepthError

        with pytest.raises(NestedDepthError) as exc_info:
            check_nested_depth(11, max_depth=10)

        assert exc_info.value.max_depth == 10
        assert exc_info.value.current_depth == 11

    def test_check_nested_depth_default_limit(self):
        """Default depth limit should be used when not specified."""
        from rail_django.generators.mutations.utils import (
            check_nested_depth,
            DEFAULT_MAX_NESTED_DEPTH,
        )
        from rail_django.generators.mutations.exceptions import NestedDepthError

        # Should not raise for default limit
        check_nested_depth(DEFAULT_MAX_NESTED_DEPTH)

        # Should raise for over default limit
        with pytest.raises(NestedDepthError):
            check_nested_depth(DEFAULT_MAX_NESTED_DEPTH + 1)


class TestNestedOperationHandler:
    """Tests for NestedOperationHandler class."""

    def test_reset_state_clears_tracking(self):
        """_reset_state should clear all tracking collections."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()
        handler._processed_objects.add("test1")
        handler._processed_objects.add("test2")
        handler._validation_errors.append("error1")
        handler.circular_reference_tracker.add("model1")

        handler._reset_state()

        assert len(handler._processed_objects) == 0
        assert len(handler._validation_errors) == 0
        assert len(handler.circular_reference_tracker) == 0

    def test_max_depth_from_settings(self):
        """max_depth should be read from mutation settings."""
        from rail_django.generators.nested import NestedOperationHandler

        mock_settings = MagicMock()
        mock_settings.max_nested_depth = 15

        handler = NestedOperationHandler(mutation_settings=mock_settings)
        assert handler.max_depth == 15

    def test_max_depth_default(self):
        """max_depth should default to 10."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()
        assert handler.max_depth == 10


class TestCircularReferenceDetection:
    """Tests for circular reference detection."""

    def test_has_circular_reference_simple_case(self):
        """Should detect simple circular references."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Create a mock model that references itself
        mock_model = MagicMock()
        mock_model.__name__ = "Author"

        mock_field = MagicMock()
        mock_field.related_model = mock_model  # Self-reference

        mock_model._meta.get_field.return_value = mock_field
        mock_model._meta.get_fields.return_value = [mock_field]

        # Self-referencing data
        input_data = {"author": {"author": {}}}

        # Should detect circular reference
        assert handler._has_circular_reference(mock_model, input_data) is True

    def test_has_circular_reference_no_cycle(self):
        """Should not detect circular reference when there is none."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Create mock models without circular reference
        mock_author = MagicMock()
        mock_author.__name__ = "Author"

        mock_book = MagicMock()
        mock_book.__name__ = "Book"

        # Author -> Book relationship (no cycle)
        mock_field = MagicMock()
        mock_field.related_model = mock_book

        mock_author._meta.get_field.return_value = mock_field
        mock_author._meta.get_fields.return_value = [mock_field]

        # Book has no fields that could create cycle
        mock_book._meta.get_field.side_effect = Exception()
        mock_book._meta.get_fields.return_value = []

        input_data = {"book": {"title": "Test"}}

        assert handler._has_circular_reference(mock_author, input_data) is False


class TestReverseRelationsProcessing:
    """Tests for reverse relations processing."""

    def test_get_reverse_relations_single_iteration(self):
        """_get_reverse_relations should not produce duplicates."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Create mock model with related_objects
        mock_model = MagicMock()
        mock_rel1 = MagicMock()
        mock_rel1.get_accessor_name.return_value = "books"
        mock_rel1.hidden = False
        mock_rel1.related_model._meta.abstract = False

        mock_rel2 = MagicMock()
        mock_rel2.get_accessor_name.return_value = "articles"
        mock_rel2.hidden = False
        mock_rel2.related_model._meta.abstract = False

        mock_model._meta.related_objects = [mock_rel1, mock_rel2]

        result = handler._get_reverse_relations(mock_model)

        # Should have exactly 2 entries (no duplicates)
        assert len(result) == 2
        assert "books" in result
        assert "articles" in result

    def test_get_reverse_relations_excludes_hidden(self):
        """_get_reverse_relations should exclude hidden relations."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        mock_model = MagicMock()
        mock_rel = MagicMock()
        mock_rel.get_accessor_name.return_value = "hidden_relation"
        mock_rel.hidden = True

        mock_model._meta.related_objects = [mock_rel]

        result = handler._get_reverse_relations(mock_model)

        assert "hidden_relation" not in result


class TestProcessRelationInput:
    """Tests for relation input processing (unified inputs)."""

    def test_process_relation_input_passthrough(self):
        """process_relation_input should pass through unified input data."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        input_data = {
            "name": "Test",
            "author": {"connect": "123"},
            "tags": {"create": [{"name": "Tag1"}]},
        }

        result = handler.process_relation_input(input_data)

        # Unified inputs should pass through unchanged
        assert result == input_data
        assert "author" in result
        assert result["author"] == {"connect": "123"}
        assert "tags" in result
        assert result["tags"] == {"create": [{"name": "Tag1"}]}

    def test_process_relation_input_regular_fields(self):
        """process_relation_input should preserve regular fields."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        input_data = {
            "name": "Test",
            "description": "A description",
            "price": 10.0,
        }

        result = handler.process_relation_input(input_data)

        assert result == input_data
        assert result["name"] == "Test"
        assert result["description"] == "A description"
        assert result["price"] == 10.0


class TestHasNestedPayload:
    """Tests for unified operation payload detection."""

    def test_has_nested_payload_with_create(self):
        """Should detect 'create' key as unified operation payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        value = {"create": [{"name": "New Item"}]}
        assert handler._has_nested_payload(value) is True

    def test_has_nested_payload_with_update(self):
        """Should detect 'update' key as unified operation payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        value = {"update": {"id": 1, "name": "Updated"}}
        assert handler._has_nested_payload(value) is True

    def test_has_nested_payload_with_connect(self):
        """Should detect 'connect' key as unified operation payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Connect is a unified operation
        assert handler._has_nested_payload({"connect": [1, 2, 3]}) is True
        assert handler._has_nested_payload({"connect": "123"}) is True

    def test_has_nested_payload_with_disconnect(self):
        """Should detect 'disconnect' key as unified operation payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Disconnect is a unified operation
        assert handler._has_nested_payload({"disconnect": [1]}) is True

    def test_has_nested_payload_with_set(self):
        """Should detect 'set' key as unified operation payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Set is a unified operation
        assert handler._has_nested_payload({"set": [1, 2, 3]}) is True
        assert handler._has_nested_payload({"set": [{"name": "New Item"}]}) is True

    def test_has_nested_payload_regular_dict(self):
        """Regular dict without operation keys should not be unified payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Regular data dict without unified operation keys
        value = {"name": "Item", "description": "Test"}
        assert handler._has_nested_payload(value) is False

    def test_has_nested_payload_list(self):
        """List values should not be detected as unified payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        # Lists (legacy format) are not unified payloads
        assert handler._has_nested_payload([1, 2, 3]) is False
        assert handler._has_nested_payload([{"name": "Item 1"}]) is False

    def test_has_nested_payload_scalar(self):
        """Scalar values should not be detected as unified payload."""
        from rail_django.generators.nested import NestedOperationHandler

        handler = NestedOperationHandler()

        assert handler._has_nested_payload("123") is False
        assert handler._has_nested_payload(123) is False
        assert handler._has_nested_payload(None) is False


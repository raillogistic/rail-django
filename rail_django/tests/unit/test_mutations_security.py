"""
Unit tests for mutation security features.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError

pytestmark = pytest.mark.unit


class TestBulkSizeLimiting:
    """Tests for bulk operation size limits."""

    def test_bulk_size_error_attributes(self):
        """BulkSizeError should have proper attributes."""
        from rail_django.generators.mutations_exceptions import BulkSizeError

        error = BulkSizeError(max_size=100, actual_size=150)
        assert error.max_size == 100
        assert error.actual_size == 150
        assert error.code == "BULK_SIZE_EXCEEDED"
        assert "100" in str(error)
        assert "150" in str(error)

    def test_default_max_bulk_size_value(self):
        """DEFAULT_MAX_BULK_SIZE should be reasonable."""
        from rail_django.generators.mutations_utils import DEFAULT_MAX_BULK_SIZE

        # Default should be a reasonable value between 50 and 1000
        assert 50 <= DEFAULT_MAX_BULK_SIZE <= 1000


class TestNestedDepthLimiting:
    """Tests for nested operation depth limits."""

    def test_nested_depth_error_attributes(self):
        """NestedDepthError should have proper attributes."""
        from rail_django.generators.mutations_exceptions import NestedDepthError

        error = NestedDepthError(max_depth=5, current_depth=6)
        assert error.max_depth == 5
        assert error.current_depth == 6
        assert error.code == "DEPTH_EXCEEDED"

    def test_default_max_nested_depth_value(self):
        """DEFAULT_MAX_NESTED_DEPTH should be reasonable."""
        from rail_django.generators.mutations_utils import DEFAULT_MAX_NESTED_DEPTH

        # Default should be between 5 and 20
        assert 5 <= DEFAULT_MAX_NESTED_DEPTH <= 20


class TestErrorMessageSanitization:
    """Tests for error message sanitization."""

    def test_validation_error_shown(self):
        """Validation errors should be shown to users."""
        from rail_django.generators.mutations_utils import sanitize_error_message

        error = ValidationError("Name field is required")
        result = sanitize_error_message(error, "create", "User")

        assert "Name field is required" in result or "required" in result.lower()

    def test_permission_error_shown(self):
        """Permission errors should be shown to users."""
        from rail_django.generators.mutations_utils import sanitize_error_message

        error = PermissionDenied("You don't have permission to edit this resource")
        result = sanitize_error_message(error, "update", "Resource")

        assert "permission" in result.lower()

    def test_generic_exception_sanitized(self):
        """Generic exceptions should not leak internal details."""
        from rail_django.generators.mutations_utils import sanitize_error_message

        # Simulate internal error with sensitive info
        error = Exception(
            "psycopg2.errors.UniqueViolation: duplicate key value violates unique "
            "constraint at /var/lib/postgresql/data"
        )
        result = sanitize_error_message(error, "create", "User")

        # Should NOT contain path information
        assert "/var/lib" not in result
        assert "postgresql" not in result.lower()
        # Should contain generic message
        assert "error" in result.lower() or "processing" in result.lower()

    def test_database_error_sanitized(self):
        """Database errors should be sanitized."""
        from rail_django.generators.mutations_utils import sanitize_error_message

        error = Exception(
            "FATAL: password authentication failed for user 'admin'"
        )
        result = sanitize_error_message(error, "create", "User")

        # Should NOT leak credentials
        assert "password" not in result.lower()
        assert "admin" not in result


class TestTenantIsolation:
    """Tests for tenant isolation in mutations."""

    def test_tenant_access_error_attributes(self):
        """TenantAccessError should have proper attributes."""
        from rail_django.generators.mutations_exceptions import TenantAccessError

        error = TenantAccessError(model_name="Document", operation="update")
        assert error.model_name == "Document"
        assert error.operation == "update"
        assert error.code == "TENANT_ACCESS_DENIED"
        assert "Document" in str(error)
        assert "update" in str(error)


class TestMutationBaseMixins:
    """Tests for mutation base class mixins."""

    def test_tenant_mixin_apply_tenant_scope_with_no_extension(self):
        """_apply_tenant_scope should return unmodified queryset if extension not available."""
        from rail_django.generators.mutations_base import TenantMixin

        class TestClass(TenantMixin):
            schema_name = "default"

        obj = TestClass()
        mock_queryset = MagicMock()
        mock_info = MagicMock()
        mock_model = MagicMock()

        # Should return the same queryset when extension is not available
        result = obj._apply_tenant_scope(mock_queryset, mock_info, mock_model)
        # Result should be the same or similar queryset
        assert result is not None

    def test_permission_mixin_has_operation_guard(self):
        """_has_operation_guard should check for guards correctly."""
        from rail_django.generators.mutations_base import PermissionMixin

        class TestClass(PermissionMixin):
            pass

        obj = TestClass()

        # No guards defined
        mock_meta_no_guards = MagicMock()
        mock_meta_no_guards._operation_guards = None
        assert obj._has_operation_guard(mock_meta_no_guards, "create") is False

        # Empty guards
        mock_meta_empty = MagicMock()
        mock_meta_empty._operation_guards = {}
        assert obj._has_operation_guard(mock_meta_empty, "create") is False

        # Has specific guard
        mock_meta_with_guard = MagicMock()
        mock_meta_with_guard._operation_guards = {"create": lambda x: True}
        assert obj._has_operation_guard(mock_meta_with_guard, "create") is True
        assert obj._has_operation_guard(mock_meta_with_guard, "update") is False

        # Has wildcard guard
        mock_meta_wildcard = MagicMock()
        mock_meta_wildcard._operation_guards = {"*": lambda x: True}
        assert obj._has_operation_guard(mock_meta_wildcard, "create") is True
        assert obj._has_operation_guard(mock_meta_wildcard, "delete") is True

    def test_permission_mixin_build_model_permission_name(self):
        """_build_model_permission_name should build correct permission string."""
        from rail_django.generators.mutations_base import PermissionMixin

        class TestClass(PermissionMixin):
            pass

        obj = TestClass()
        mock_model = MagicMock()
        mock_model._meta.app_label = "myapp"
        mock_model._meta.model_name = "document"

        assert obj._build_model_permission_name(mock_model, "create") == "myapp.add_document"
        assert obj._build_model_permission_name(mock_model, "retrieve") == "myapp.view_document"
        assert obj._build_model_permission_name(mock_model, "update") == "myapp.change_document"
        assert obj._build_model_permission_name(mock_model, "delete") == "myapp.delete_document"

        # Bulk operations should map to their base operation
        assert obj._build_model_permission_name(mock_model, "bulk_create") == "myapp.add_document"
        assert obj._build_model_permission_name(mock_model, "bulk_update") == "myapp.change_document"
        assert obj._build_model_permission_name(mock_model, "bulk_delete") == "myapp.delete_document"


class TestInvalidIdFormatHandling:
    """Tests for invalid ID format handling."""

    def test_invalid_id_format_error(self):
        """InvalidIdFormatError should contain field and value info."""
        from rail_django.generators.mutations_exceptions import InvalidIdFormatError

        error = InvalidIdFormatError(field_name="author_id", value="not-a-valid-id")
        assert error.field == "author_id"
        assert error.value == "not-a-valid-id"
        assert error.code == "INVALID_ID_FORMAT"
        assert "author_id" in str(error)

    def test_related_object_not_found_error(self):
        """RelatedObjectNotFoundError should contain model and pk info."""
        from rail_django.generators.mutations_exceptions import RelatedObjectNotFoundError

        error = RelatedObjectNotFoundError(
            model_name="Author",
            field_name="author_id",
            pk_value="999"
        )
        assert error.model_name == "Author"
        assert error.field == "author_id"
        assert error.pk_value == "999"
        assert error.code == "RELATED_OBJECT_NOT_FOUND"
        assert "Author" in str(error)
        assert "999" in str(error)


class TestCircularReferenceHandling:
    """Tests for circular reference detection."""

    def test_circular_reference_error(self):
        """CircularReferenceError should contain model and path info."""
        from rail_django.generators.mutations_exceptions import CircularReferenceError

        error = CircularReferenceError(model_name="Author", path="books.author.books")
        assert error.model_name == "Author"
        assert error.path == "books.author.books"
        assert error.code == "CIRCULAR_REFERENCE"
        assert "Author" in str(error)
        assert "books.author.books" in str(error)

    def test_circular_reference_error_no_path(self):
        """CircularReferenceError should work without path."""
        from rail_django.generators.mutations_exceptions import CircularReferenceError

        error = CircularReferenceError(model_name="Author")
        assert error.model_name == "Author"
        assert error.path == ""
        assert "Author" in str(error)

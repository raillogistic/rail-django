"""
Tests pour la rétro-compatibilité du renommage exceptions → errors.

Ce module vérifie que les imports depuis ``rail_django.core.exceptions``
continuent de fonctionner et pointent vers les mêmes classes que
``rail_django.core.errors``.
"""

import pytest


@pytest.mark.unit
class TestExceptionsBackwardCompatibility:
    """Vérification de la façade de rétro-compatibilité."""

    def test_imports_from_exceptions_module(self):
        """Les imports depuis exceptions.py doivent fonctionner."""
        from rail_django.core.exceptions import (
            AuthenticationError,
            ErrorCode,
            ErrorHandler,
            FileUploadError,
            GraphQLAutoError,
            PermissionError,
            QueryComplexityError,
            QueryDepthError,
            RateLimitError,
            ResourceNotFoundError,
            SecurityError,
            ValidationError,
            error_handler,
            handle_graphql_error,
        )
        # Verify they are all importable (no-op checks)
        assert ErrorCode is not None
        assert GraphQLAutoError is not None
        assert error_handler is not None

    def test_canonical_and_facade_are_same_objects(self):
        """Les objets importés des deux chemins doivent être identiques."""
        from rail_django.core.errors import (
            GraphQLAutoError as Canonical,
            ErrorCode as CanonicalCode,
            error_handler as canonical_handler,
        )
        from rail_django.core.exceptions import (
            GraphQLAutoError as Legacy,
            ErrorCode as LegacyCode,
            error_handler as legacy_handler,
        )

        assert Canonical is Legacy
        assert CanonicalCode is LegacyCode
        assert canonical_handler is legacy_handler

    def test_core_init_exposes_errors(self):
        """Les exports depuis rail_django.core doivent pointer vers errors."""
        from rail_django.core import GraphQLAutoError, ErrorCode
        from rail_django.core.errors import (
            GraphQLAutoError as CanonicalError,
            ErrorCode as CanonicalCode,
        )

        assert GraphQLAutoError is CanonicalError
        assert ErrorCode is CanonicalCode

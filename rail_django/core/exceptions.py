"""
Backward-compatible re-export facade for ``rail_django.core.errors``.

.. deprecated::
    Import from ``rail_django.core.errors`` instead. This module exists
    solely to preserve backward compatibility for existing downstream
    imports of ``from rail_django.core.exceptions import ...``.

All symbols are re-exported unchanged from the canonical module.
"""

# Re-export everything from the canonical errors module so existing
# ``from rail_django.core.exceptions import X`` statements keep working.
from rail_django.core.errors import (  # noqa: F401
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

__all__ = [
    "AuthenticationError",
    "ErrorCode",
    "ErrorHandler",
    "FileUploadError",
    "GraphQLAutoError",
    "PermissionError",
    "QueryComplexityError",
    "QueryDepthError",
    "RateLimitError",
    "ResourceNotFoundError",
    "SecurityError",
    "ValidationError",
    "error_handler",
    "handle_graphql_error",
]

"""
Middleware stack management for Rail Django GraphQL.

This module provides functions for building and managing the middleware
stack for GraphQL operations.
"""

from typing import Any, Callable, List, Optional

from .base import BaseMiddleware
from .auth import AuthenticationMiddleware, FieldPermissionMiddleware
from .security import (
    AccessGuardMiddleware,
    ErrorHandlingMiddleware,
    GraphQLAuditMiddleware,
    LoggingMiddleware,
    ValidationMiddleware,
)
from .performance import (
    PerformanceMiddleware,
    QueryComplexityMiddleware,
    RateLimitingMiddleware,
)
from .plugin import CORSMiddleware, PluginMiddleware

# Optional multitenancy middleware
try:
    from ...extensions.multitenancy import TenantContextMiddleware
except Exception:
    TenantContextMiddleware = None


# Default middleware stack
# Order matters: middleware is executed in order for requests,
# and in reverse order for responses
DEFAULT_MIDDLEWARE: List[type] = [
    AuthenticationMiddleware,
    TenantContextMiddleware,
    GraphQLAuditMiddleware,
    RateLimitingMiddleware,
    AccessGuardMiddleware,
    ValidationMiddleware,
    FieldPermissionMiddleware,
    QueryComplexityMiddleware,
    PluginMiddleware,
    PerformanceMiddleware,
    LoggingMiddleware,
    ErrorHandlingMiddleware,
    CORSMiddleware,
]

# Filter out None values (e.g., if TenantContextMiddleware is not available)
DEFAULT_MIDDLEWARE = [mw for mw in DEFAULT_MIDDLEWARE if mw is not None]


def get_middleware_stack(schema_name: Optional[str] = None) -> List[BaseMiddleware]:
    """Get the middleware stack for a schema.

    Creates instances of all default middleware classes configured for
    the specified schema.

    Args:
        schema_name: Optional schema name for schema-specific middleware.

    Returns:
        List of middleware instances in execution order.

    Example:
        >>> middleware_stack = get_middleware_stack("my_schema")
        >>> for middleware in middleware_stack:
        ...     print(middleware.__class__.__name__)
        AuthenticationMiddleware
        GraphQLAuditMiddleware
        RateLimitingMiddleware
        ...
    """
    middleware_stack = []

    for middleware_class in DEFAULT_MIDDLEWARE:
        middleware_instance = middleware_class(schema_name)
        middleware_stack.append(middleware_instance)

    return middleware_stack


def create_middleware_resolver(middleware_stack: List[BaseMiddleware]) -> Callable:
    """Create a resolver that applies middleware stack.

    Creates a resolver function that wraps the original resolver with
    all middleware in the stack, applying them in order.

    Args:
        middleware_stack: List of middleware instances to apply.

    Returns:
        A middleware resolver function that can wrap any GraphQL resolver.

    Example:
        >>> stack = get_middleware_stack()
        >>> resolver = create_middleware_resolver(stack)
        >>> # Use resolver in GraphQL execution
        >>> result = resolver(original_resolver, root, info, **kwargs)
    """
    def middleware_resolver(next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Apply middleware stack to resolver.

        Args:
            next_resolver: The original resolver function.
            root: Root value passed to the resolver.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Result from the resolver chain.
        """

        def apply_middleware(index: int, current_root: Any, current_info: Any, current_kwargs: dict) -> Any:
            """Recursively apply middleware at the given index.

            Args:
                index: Current middleware index in the stack.
                current_root: Root value passed through the middleware chain.
                current_info: GraphQL resolve info passed through the chain.
                current_kwargs: Resolver kwargs passed through the chain.

            Returns:
                Result from the middleware chain.
            """
            if index >= len(middleware_stack):
                return next_resolver(current_root, current_info, **current_kwargs)

            middleware = middleware_stack[index]

            def next_middleware_resolver(r, i, **kw):
                return apply_middleware(index + 1, r, i, kw)

            return middleware.resolve(next_middleware_resolver, current_root, current_info, **current_kwargs)

        return apply_middleware(0, root, info, kwargs)

    return middleware_resolver

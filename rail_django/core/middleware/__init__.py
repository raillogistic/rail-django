"""
GraphQL middleware for Rail Django.

This package implements middleware functionality for GraphQL operations,
including authentication, logging, performance monitoring, security,
and error handling.

Middleware Classes:
    - BaseMiddleware: Base class for all middleware
    - MiddlewareSettings: Configuration dataclass for middleware
    - AuthenticationMiddleware: User authentication
    - FieldPermissionMiddleware: Field-level permission enforcement
    - ValidationMiddleware: Input validation
    - AccessGuardMiddleware: Schema-level access control
    - GraphQLAuditMiddleware: Operation auditing
    - ErrorHandlingMiddleware: Error handling and logging
    - LoggingMiddleware: Operation logging
    - PerformanceMiddleware: Performance monitoring
    - QueryComplexityMiddleware: Query complexity analysis
    - RateLimitingMiddleware: Rate limiting
    - PluginMiddleware: Plugin execution hooks
    - CORSMiddleware: CORS handling

Functions:
    - get_middleware_stack: Get the middleware stack for a schema
    - create_middleware_resolver: Create a resolver with middleware applied
"""

from .base import BaseMiddleware, MiddlewareSettings
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
from .stack import (
    DEFAULT_MIDDLEWARE,
    create_middleware_resolver,
    get_middleware_stack,
)

__all__ = [
    # Base classes
    "BaseMiddleware",
    "MiddlewareSettings",
    # Authentication middleware
    "AuthenticationMiddleware",
    "FieldPermissionMiddleware",
    # Security middleware
    "AccessGuardMiddleware",
    "ErrorHandlingMiddleware",
    "GraphQLAuditMiddleware",
    "LoggingMiddleware",
    "ValidationMiddleware",
    # Performance middleware
    "PerformanceMiddleware",
    "QueryComplexityMiddleware",
    "RateLimitingMiddleware",
    # Plugin middleware
    "CORSMiddleware",
    "PluginMiddleware",
    # Stack management
    "DEFAULT_MIDDLEWARE",
    "create_middleware_resolver",
    "get_middleware_stack",
]

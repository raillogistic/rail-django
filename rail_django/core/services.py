"""
Service hooks for pluggable runtime components.

This module provides lightweight dependency injection points for shared services
like rate limiting, query optimization, and audit logging.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol

from rail_django.common.interfaces import (
    AuditLoggerProtocol,
    QueryCacheBackendProtocol,
    QueryOptimizerProtocol,
    RateLimiterProtocol,
)

RateLimiterFactory = Callable[[Optional[str]], RateLimiterProtocol]
QueryOptimizerFactory = Callable[[Optional[str]], QueryOptimizerProtocol]
AuditLoggerFactory = Callable[[], AuditLoggerProtocol]
QueryCacheFactory = Callable[[Optional[str]], QueryCacheBackendProtocol]

_rate_limiter_factory: Optional[RateLimiterFactory] = None
_query_optimizer_factory: Optional[QueryOptimizerFactory] = None
_audit_logger_factory: Optional[AuditLoggerFactory] = None
_query_cache_factory: Optional[QueryCacheFactory] = None


def set_rate_limiter_factory(factory: Optional[RateLimiterFactory]) -> None:
    global _rate_limiter_factory
    _rate_limiter_factory = factory


def set_query_optimizer_factory(factory: Optional[QueryOptimizerFactory]) -> None:
    global _query_optimizer_factory
    _query_optimizer_factory = factory


def set_audit_logger_factory(factory: Optional[AuditLoggerFactory]) -> None:
    global _audit_logger_factory
    _audit_logger_factory = factory


def set_query_cache_factory(factory: Optional[QueryCacheFactory]) -> None:
    global _query_cache_factory
    _query_cache_factory = factory


def get_rate_limiter(schema_name: Optional[str] = None) -> RateLimiterProtocol:
    if _rate_limiter_factory is not None:
        return _rate_limiter_factory(schema_name)
    from .rate_limiting import get_rate_limiter as default_get_rate_limiter

    return default_get_rate_limiter(schema_name)


def get_query_optimizer(schema_name: Optional[str] = None) -> QueryOptimizerProtocol:
    if _query_optimizer_factory is not None:
        return _query_optimizer_factory(schema_name)
    from .performance import get_query_optimizer as default_get_query_optimizer

    return default_get_query_optimizer(schema_name)


def get_audit_logger() -> AuditLoggerProtocol:
    if _audit_logger_factory is not None:
        return _audit_logger_factory()
    try:
        from ..security.audit_logging import audit_logger
    except Exception:
        from ..extensions.audit import audit_logger

    return audit_logger


def get_query_cache_backend(schema_name: Optional[str] = None) -> Optional[QueryCacheBackendProtocol]:
    if _query_cache_factory is not None:
        return _query_cache_factory(schema_name)
    return None

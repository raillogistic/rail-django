"""
Middleware package for Django GraphQL Auto.

This package contains middleware components for:
- Performance monitoring
- Query optimization
- Caching integration
- Security enhancements
- Authentication and authorization
- Rate limiting and audit logging
"""

from .auth_middleware import GraphQLAuthenticationMiddleware, GraphQLRateLimitMiddleware
from .performance import (
    GraphQLPerformanceMiddleware,
    GraphQLPerformanceView,
    get_performance_aggregator,
    monitor_performance,
    setup_performance_monitoring,
)

__all__ = [
    'GraphQLPerformanceMiddleware',
    'GraphQLPerformanceView',
    'get_performance_aggregator',
    'setup_performance_monitoring',
    'monitor_performance',
    'GraphQLAuthenticationMiddleware',
    'GraphQLRateLimitMiddleware'
]

"""
Configuration classes for query optimization.
"""

from dataclasses import dataclass


@dataclass
class QueryOptimizationConfig:
    """Configuration for query optimization features."""

    # N+1 Query Prevention
    enable_select_related: bool = True
    enable_prefetch_related: bool = True
    max_prefetch_depth: int = 3
    auto_optimize_queries: bool = True

    # Caching
    enable_schema_caching: bool = False
    enable_query_caching: bool = False
    enable_field_caching: bool = False
    cache_timeout: int = 300  # 5 minutes
    query_cache_user_specific: bool = False
    query_cache_scope: str = "schema"

    # Query Optimization
    enable_complexity_analysis: bool = True
    max_query_complexity: int = 1000
    max_query_depth: int = 10
    query_timeout: int = 30  # seconds

    # Resource Monitoring
    enable_performance_monitoring: bool = True
    log_slow_queries: bool = True
    slow_query_threshold: float = 1.0  # seconds

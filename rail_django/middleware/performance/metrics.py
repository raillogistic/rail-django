"""
Data classes for performance metrics and alerts.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from django.conf import settings


@dataclass
class RequestMetrics:
    """Métriques pour une requête individuelle."""

    request_id: str
    query_name: str
    start_time: float
    end_time: Optional[float] = None
    execution_time: Optional[float] = None

    # Métriques de performance
    database_queries: int = 0
    database_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    n_plus_one_queries: list[dict[str, Any]] = field(default_factory=list)
    n_plus_one_count: int = 0

    # Métriques de ressources
    memory_usage: float = 0.0
    cpu_usage: float = 0.0

    # Informations sur la requête
    query_complexity: Optional[int] = None
    query_depth: Optional[int] = None
    user_id: Optional[int] = None

    # Erreurs
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_slow_query(self) -> bool:
        """Détermine si la requête est considérée comme lente."""
        slow_threshold = getattr(settings, "GRAPHQL_SLOW_QUERY_THRESHOLD", 1.0)
        return self.execution_time and self.execution_time > slow_threshold

    @property
    def is_complex_query(self) -> bool:
        """Détermine si la requête est considérée comme complexe."""
        complexity_threshold = getattr(settings, "GRAPHQL_COMPLEXITY_THRESHOLD", 100)
        return self.query_complexity and self.query_complexity > complexity_threshold


@dataclass
class PerformanceAlert:
    """Alerte de performance."""

    alert_type: str  # 'slow_query', 'high_complexity', 'memory_usage', etc.
    severity: str  # 'low', 'medium', 'high', 'critical'
    message: str
    timestamp: datetime
    request_metrics: RequestMetrics
    threshold_value: Optional[float] = None
    actual_value: Optional[float] = None

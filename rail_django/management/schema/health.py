"""
Schema health models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SchemaHealth:
    """Schema health status."""
    schema_name: str
    status: str  # 'healthy', 'warning', 'critical'
    last_check: datetime
    issues: list[str] = field(default_factory=list)
    performance_score: float = 100.0
    error_rate: float = 0.0
    usage_stats: dict[str, Any] = field(default_factory=dict)

"""
GraphQL security configuration.
"""

from dataclasses import dataclass
from enum import Enum
from django.conf import settings


class SecurityThreatLevel(Enum):
    """Niveaux de menace de sécurité."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityConfig:
    """Configuration de sécurité GraphQL."""
    max_query_complexity: int = 1000
    max_query_depth: int = 15
    max_field_count: int = 100
    max_operation_count: int = 10
    enable_introspection: bool = False
    introspection_roles: list[str] = None
    query_timeout: int = 30  # secondes
    enable_query_cost_analysis: bool = True
    enable_depth_limiting: bool = True
    enable_field_suggestions: bool = False
    rate_limit_per_minute: int = 60
    complexity_multipliers: dict[str, float] = None

    def __post_init__(self):
        """Initialise les valeurs par défaut."""
        if self.introspection_roles is None:
            self.introspection_roles = ['admin', 'developer']

        if self.complexity_multipliers is None:
            self.complexity_multipliers = {
                'connection': 2.0,  # Les connexions sont plus coûteuses
                'mutation': 3.0,    # Les mutations sont plus coûteuses
                'nested_object': 1.5,  # Les objets imbriqués
                'list_field': 2.0,  # Les champs de liste
            }


# Configuration par défaut
default_security_config = SecurityConfig(
    max_query_complexity=getattr(settings, 'GRAPHQL_MAX_QUERY_COMPLEXITY', 1000),
    max_query_depth=getattr(settings, 'GRAPHQL_MAX_QUERY_DEPTH', 15),
    max_field_count=getattr(settings, 'GRAPHQL_MAX_FIELD_COUNT', 100),
    enable_introspection=getattr(settings, 'GRAPHQL_ENABLE_INTROSPECTION', False),
    query_timeout=getattr(settings, 'GRAPHQL_QUERY_TIMEOUT', 30),
    rate_limit_per_minute=getattr(settings, 'GRAPHQL_RATE_LIMIT_PER_MINUTE', 60)
)

"""
GraphQL security package for Rail Django.
"""

from .analyzer import GraphQLSecurityAnalyzer, QueryAnalysisResult
from .config import SecurityConfig, SecurityThreatLevel, default_security_config
from .decorators import require_introspection_permission
from .middleware import create_security_middleware
from .rules import QueryComplexityValidationRule

# Global analyzer instance
security_analyzer = GraphQLSecurityAnalyzer(default_security_config)

__all__ = [
    "GraphQLSecurityAnalyzer",
    "QueryAnalysisResult",
    "SecurityConfig",
    "SecurityThreatLevel",
    "default_security_config",
    "require_introspection_permission",
    "create_security_middleware",
    "QueryComplexityValidationRule",
    "security_analyzer",
]

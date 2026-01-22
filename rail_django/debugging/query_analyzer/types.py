"""
Query analyzer types and results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


class QueryIssueType(Enum):
    """Types of query issues that can be detected."""
    HIGH_COMPLEXITY = "high_complexity"
    DEEP_NESTING = "deep_nesting"
    LARGE_RESULT_SET = "large_result_set"
    EXPENSIVE_FIELD = "expensive_field"
    DEPRECATED_FIELD = "deprecated_field"
    SECURITY_RISK = "security_risk"
    INEFFICIENT_PATTERN = "inefficient_pattern"
    MISSING_FRAGMENT = "missing_fragment"
    UNUSED_FRAGMENT = "unused_fragment"
    DUPLICATE_FIELDS = "duplicate_fields"


class QuerySeverity(Enum):
    """Severity levels for query issues."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QueryIssue:
    """Represents an issue found in a GraphQL query."""
    issue_type: QueryIssueType
    severity: QuerySeverity
    message: str
    location: Optional[dict[str, Any]] = None
    suggestion: Optional[str] = None
    field_path: Optional[str] = None
    complexity_score: Optional[int] = None


@dataclass
class QueryComplexity:
    """Query complexity analysis result."""
    total_score: int
    max_depth: int
    field_count: int
    fragment_count: int
    operation_count: int
    expensive_fields: list[str] = field(default_factory=list)
    complexity_by_field: dict[str, int] = field(default_factory=dict)


@dataclass
class QueryAnalysisResult:
    """Complete query analysis result."""
    query: str
    is_valid: bool
    complexity: QueryComplexity
    issues: list[QueryIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    security_score: float = 0.0
    performance_score: float = 0.0
    estimated_execution_time_ms: Optional[float] = None

"""Production query profiling helpers built on the GraphQL query analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .analyzer import QueryAnalyzer
from .types import (
    QueryAnalysisResult,
    QueryIssue,
    QueryIssueType,
    QuerySeverity,
)


@dataclass(frozen=True)
class QueryProfileInput:
    """A GraphQL query sample captured from logs or telemetry."""

    query: str
    operation_name: str | None = None
    source: str | None = None
    count: int = 1
    duration_ms: float | None = None


@dataclass
class QueryProfileEntry:
    """Analysis for one captured query sample."""

    query: str
    operation_name: str | None
    source: str | None
    count: int
    duration_ms: float | None
    analysis: QueryAnalysisResult
    n_plus_one_issues: list[QueryIssue] = field(default_factory=list)

    @property
    def has_n_plus_one_risk(self) -> bool:
        """Return whether this sample has an N+1-related risk signal."""
        return bool(self.n_plus_one_issues)

    @property
    def highest_severity(self) -> QuerySeverity | None:
        """Return the highest severity across all analyzer issues."""
        if not self.analysis.issues:
            return None
        return max(
            self.analysis.issues, key=lambda issue: _severity_rank(issue.severity)
        ).severity

    def to_dict(self) -> dict[str, Any]:
        """Serialize this entry for JSON reports."""
        return {
            "operation_name": self.operation_name,
            "source": self.source,
            "count": self.count,
            "duration_ms": self.duration_ms,
            "is_valid": self.analysis.is_valid,
            "performance_score": self.analysis.performance_score,
            "security_score": self.analysis.security_score,
            "estimated_execution_time_ms": self.analysis.estimated_execution_time_ms,
            "complexity": {
                "total_score": self.analysis.complexity.total_score,
                "max_depth": self.analysis.complexity.max_depth,
                "field_count": self.analysis.complexity.field_count,
                "fragment_count": self.analysis.complexity.fragment_count,
                "operation_count": self.analysis.complexity.operation_count,
            },
            "n_plus_one_risk": self.has_n_plus_one_risk,
            "n_plus_one_issues": [
                _issue_to_dict(issue) for issue in self.n_plus_one_issues
            ],
            "issues": [_issue_to_dict(issue) for issue in self.analysis.issues],
            "suggestions": list(self.analysis.suggestions),
        }


@dataclass
class QueryProfileReport:
    """Aggregated analysis for a batch of production query samples."""

    entries: list[QueryProfileEntry]

    @property
    def total_queries(self) -> int:
        return len(self.entries)

    @property
    def total_observations(self) -> int:
        return sum(entry.count for entry in self.entries)

    @property
    def n_plus_one_risk_count(self) -> int:
        return sum(1 for entry in self.entries if entry.has_n_plus_one_risk)

    @property
    def high_risk_count(self) -> int:
        return sum(
            1
            for entry in self.entries
            if entry.highest_severity in {QuerySeverity.HIGH, QuerySeverity.CRITICAL}
        )

    @property
    def worst_performance_score(self) -> float:
        if not self.entries:
            return 100.0
        return min(entry.analysis.performance_score for entry in self.entries)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this report for JSON output."""
        return {
            "total_queries": self.total_queries,
            "total_observations": self.total_observations,
            "n_plus_one_risk_count": self.n_plus_one_risk_count,
            "high_risk_count": self.high_risk_count,
            "worst_performance_score": self.worst_performance_score,
            "entries": [entry.to_dict() for entry in self.entries],
        }


class ProductionQueryProfiler:
    """Profile captured production GraphQL queries for N+1 risk signals."""

    def __init__(self, analyzer: QueryAnalyzer | None = None):
        self.analyzer = analyzer or QueryAnalyzer()

    def profile(
        self, samples: Iterable[QueryProfileInput | dict[str, Any] | str]
    ) -> QueryProfileReport:
        """Analyze query samples and aggregate N+1 risk signals."""
        entries: list[QueryProfileEntry] = []

        for sample in samples:
            profile_input = _normalize_sample(sample)
            analysis = self.analyzer.analyze_query(
                profile_input.query,
                operation_name=profile_input.operation_name,
            )
            n_plus_one_issues = [
                issue for issue in analysis.issues if _is_n_plus_one_risk(issue)
            ]
            entries.append(
                QueryProfileEntry(
                    query=profile_input.query,
                    operation_name=profile_input.operation_name,
                    source=profile_input.source,
                    count=profile_input.count,
                    duration_ms=profile_input.duration_ms,
                    analysis=analysis,
                    n_plus_one_issues=n_plus_one_issues,
                )
            )

        return QueryProfileReport(entries=entries)


def _normalize_sample(
    sample: QueryProfileInput | dict[str, Any] | str,
) -> QueryProfileInput:
    if isinstance(sample, QueryProfileInput):
        return sample
    if isinstance(sample, str):
        return QueryProfileInput(query=sample)
    if not isinstance(sample, dict):
        raise TypeError(
            "Query samples must be strings, dictionaries, or QueryProfileInput values."
        )

    query = sample.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError(
            "Query sample dictionaries must include a non-empty 'query' string."
        )

    operation_name = sample.get("operation_name", sample.get("operationName"))
    source = sample.get("source")
    count = _positive_int(sample.get("count", sample.get("occurrences", 1)), default=1)
    duration_ms = _optional_float(sample.get("duration_ms", sample.get("durationMs")))

    return QueryProfileInput(
        query=query,
        operation_name=str(operation_name) if operation_name else None,
        source=str(source) if source else None,
        count=count,
        duration_ms=duration_ms,
    )


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _severity_rank(severity: QuerySeverity) -> int:
    return {
        QuerySeverity.LOW: 1,
        QuerySeverity.MEDIUM: 2,
        QuerySeverity.HIGH: 3,
        QuerySeverity.CRITICAL: 4,
    }.get(severity, 0)


def _is_n_plus_one_risk(issue: QueryIssue) -> bool:
    if issue.issue_type == QueryIssueType.INEFFICIENT_PATTERN:
        return "n+1" in issue.message.lower()
    return issue.issue_type in {
        QueryIssueType.DEEP_NESTING,
        QueryIssueType.EXPENSIVE_FIELD,
    }


def _issue_to_dict(issue: QueryIssue) -> dict[str, Any]:
    return {
        "type": issue.issue_type.value,
        "severity": issue.severity.value,
        "message": issue.message,
        "location": issue.location,
        "suggestion": issue.suggestion,
        "field_path": issue.field_path,
        "complexity_score": issue.complexity_score,
    }


__all__ = [
    "ProductionQueryProfiler",
    "QueryProfileEntry",
    "QueryProfileInput",
    "QueryProfileReport",
]

"""
Query analyzer module.

This module provides comprehensive analysis of GraphQL queries,
including complexity analysis, security checks, and optimization suggestions.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    GraphQLError,
    InlineFragmentNode,
    OperationDefinitionNode,
    Visitor,
    build_schema,
    parse,
    validate,
    visit,
)

logger = logging.getLogger(__name__)


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
    location: Optional[Dict[str, Any]] = None
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
    expensive_fields: List[str] = field(default_factory=list)
    complexity_by_field: Dict[str, int] = field(default_factory=dict)


@dataclass
class QueryAnalysisResult:
    """Complete query analysis result."""
    query: str
    is_valid: bool
    complexity: QueryComplexity
    issues: List[QueryIssue] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    security_score: float = 0.0
    performance_score: float = 0.0
    estimated_execution_time_ms: Optional[float] = None


class ComplexityVisitor(Visitor):
    """Visitor for calculating query complexity."""

    def __init__(self, field_complexity_map: Dict[str, int] = None,
                 max_depth: int = 15, introspection_cost: int = 1):
        # Initialize parent Visitor class to set up enter_leave_map
        super().__init__()

        self.field_complexity_map = field_complexity_map or {}
        self.max_depth = max_depth
        self.introspection_cost = introspection_cost

        self.complexity = 0
        self.depth = 0
        self.max_depth_reached = 0
        self.field_count = 0
        self.fragment_count = 0
        self.field_path = []
        self.complexity_by_field = {}
        self.expensive_fields = []

    def enter_field(self, node: FieldNode, *_):
        """Enter a field node."""
        field_name = node.name.value
        self.field_count += 1
        self.depth += 1
        self.max_depth_reached = max(self.max_depth_reached, self.depth)

        # Build field path
        self.field_path.append(field_name)
        current_path = '.'.join(self.field_path)

        # Calculate field complexity
        field_complexity = self._calculate_field_complexity(node, current_path)
        self.complexity += field_complexity
        self.complexity_by_field[current_path] = field_complexity

        # Track expensive fields
        if field_complexity > 10:  # Configurable threshold
            self.expensive_fields.append(current_path)

        return node

    def leave_field(self, node: FieldNode, *_):
        """Leave a field node."""
        self.depth -= 1
        if self.field_path:
            self.field_path.pop()
        return node

    def enter_fragment_definition(self, node: FragmentDefinitionNode, *_):
        """Enter a fragment definition."""
        self.fragment_count += 1
        return node

    def enter_inline_fragment(self, node: InlineFragmentNode, *_):
        """Enter an inline fragment."""
        self.fragment_count += 1
        return node

    def _calculate_field_complexity(self, node: FieldNode, field_path: str) -> int:
        """Calculate complexity for a specific field."""
        field_name = node.name.value

        # Check if it's an introspection field
        if field_name.startswith('__'):
            return self.introspection_cost

        # Use configured complexity if available
        if field_path in self.field_complexity_map:
            base_complexity = self.field_complexity_map[field_path]
        elif field_name in self.field_complexity_map:
            base_complexity = self.field_complexity_map[field_name]
        else:
            # Default complexity based on field characteristics
            base_complexity = self._estimate_field_complexity(node)

        # Apply multipliers based on arguments
        multiplier = self._calculate_argument_multiplier(node)

        return int(base_complexity * multiplier)

    def _estimate_field_complexity(self, node: FieldNode) -> int:
        """Estimate field complexity based on characteristics."""
        field_name = node.name.value

        # List fields are generally more expensive
        if any(keyword in field_name.lower() for keyword in ['list', 'all', 'search', 'filter']):
            return 5

        # Relation fields
        if any(keyword in field_name.lower() for keyword in ['user', 'users', 'post', 'posts']):
            return 3

        # Simple scalar fields
        return 1

    def _calculate_argument_multiplier(self, node: FieldNode) -> float:
        """Calculate complexity multiplier based on field arguments."""
        if not node.arguments:
            return 1.0

        multiplier = 1.0

        for arg in node.arguments:
            arg_name = arg.name.value.lower()

            # Pagination arguments reduce complexity
            if arg_name in ['first', 'last', 'limit']:
                try:
                    if hasattr(arg.value, 'value'):
                        limit_value = int(arg.value.value)
                        # Cap the multiplier based on limit
                        multiplier *= min(limit_value / 10, 5.0)
                except (ValueError, AttributeError):
                    multiplier *= 2.0  # Unknown limit, assume moderate impact

            # Search/filter arguments increase complexity
            elif arg_name in ['search', 'filter', 'where']:
                multiplier *= 1.5

            # Sorting arguments add slight complexity
            elif arg_name in ['order_by', 'sort']:
                multiplier *= 1.2

        return multiplier


class QueryAnalyzer:
    """
    Comprehensive GraphQL query analyzer.

    Analyzes queries for complexity, security issues, performance problems,
    and provides optimization suggestions.
    """

    def __init__(self,
                 schema_string: str = None,
                 max_complexity: int = 1000,
                 max_depth: int = 15,
                 field_complexity_map: Dict[str, int] = None,
                 expensive_fields: Set[str] = None,
                 deprecated_fields: Set[str] = None):

        self.schema = None
        if schema_string:
            try:
                self.schema = build_schema(schema_string)
            except Exception as e:
                logger.error(f"Failed to build schema: {e}")

        self.max_complexity = max_complexity
        self.max_depth = max_depth
        self.field_complexity_map = field_complexity_map or {}
        self.expensive_fields = expensive_fields or set()
        self.deprecated_fields = deprecated_fields or set()

        # Security patterns to detect
        self.security_patterns = [
            (r'__schema', "Introspection query detected"),
            (r'__type', "Type introspection detected"),
            (r'mutation.*delete.*all', "Potentially dangerous bulk delete"),
            (r'query.*{.*}.*{.*}', "Potential query batching"),
        ]

        # Performance anti-patterns
        self.performance_patterns = [
            (r'(\w+)\s*{\s*\1', "Potential N+1 query pattern"),
            (r'users\s*{\s*posts\s*{\s*comments', "Deep nesting detected"),
            (r'(search|filter).*limit:\s*(\d+)', "Large result set requested"),
        ]

        self.logger = logging.getLogger(__name__)

    def analyze_query(self, query: str, variables: Dict[str, Any] = None,
                      operation_name: str = None) -> QueryAnalysisResult:
        """
        Perform comprehensive analysis of a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables
            operation_name: Name of the operation to analyze

        Returns:
            Complete analysis result
        """
        result = QueryAnalysisResult(query=query, is_valid=False,
                                     complexity=QueryComplexity(0, 0, 0, 0, 0))

        try:
            # Parse the query
            document = parse(query)
            result.is_valid = True

            # Validate against schema if available
            if self.schema:
                validation_errors = validate(self.schema, document)
                if validation_errors:
                    for error in validation_errors:
                        result.issues.append(QueryIssue(
                            issue_type=QueryIssueType.SECURITY_RISK,
                            severity=QuerySeverity.HIGH,
                            message=f"Validation error: {error.message}",
                            location=self._extract_location(error)
                        ))

            # Analyze complexity
            result.complexity = self._analyze_complexity(document)

            # Check for issues
            result.issues.extend(self._check_complexity_issues(result.complexity))
            result.issues.extend(self._check_security_issues(query))
            result.issues.extend(self._check_performance_issues(query, document))
            result.issues.extend(self._check_deprecated_fields(document))

            # Generate suggestions
            result.suggestions = self._generate_suggestions(result)

            # Calculate scores
            result.security_score = self._calculate_security_score(result.issues)
            result.performance_score = self._calculate_performance_score(result)
            result.estimated_execution_time_ms = self._estimate_execution_time(result)

        except Exception as e:
            result.issues.append(QueryIssue(
                issue_type=QueryIssueType.SECURITY_RISK,
                severity=QuerySeverity.CRITICAL,
                message=f"Query parsing failed: {str(e)}"
            ))
            self.logger.error(f"Query analysis failed: {e}")

        return result

    def _analyze_complexity(self, document) -> QueryComplexity:
        """Analyze query complexity."""
        visitor = ComplexityVisitor(
            field_complexity_map=self.field_complexity_map,
            max_depth=self.max_depth
        )

        # Count operations
        operation_count = len([
            node for node in document.definitions
            if isinstance(node, OperationDefinitionNode)
        ])

        # Visit the document to calculate complexity
        visit(document, visitor)

        return QueryComplexity(
            total_score=visitor.complexity,
            max_depth=visitor.max_depth_reached,
            field_count=visitor.field_count,
            fragment_count=visitor.fragment_count,
            operation_count=operation_count,
            expensive_fields=visitor.expensive_fields,
            complexity_by_field=visitor.complexity_by_field
        )

    def _check_complexity_issues(self, complexity: QueryComplexity) -> List[QueryIssue]:
        """Check for complexity-related issues."""
        issues = []

        # High complexity
        if complexity.total_score > self.max_complexity:
            issues.append(QueryIssue(
                issue_type=QueryIssueType.HIGH_COMPLEXITY,
                severity=QuerySeverity.HIGH,
                message=f"Query complexity ({complexity.total_score}) exceeds limit ({self.max_complexity})",
                complexity_score=complexity.total_score,
                suggestion="Consider reducing the number of fields or using fragments"
            ))

        # Deep nesting
        if complexity.max_depth > self.max_depth:
            issues.append(QueryIssue(
                issue_type=QueryIssueType.DEEP_NESTING,
                severity=QuerySeverity.MEDIUM,
                message=f"Query depth ({complexity.max_depth}) exceeds recommended limit ({self.max_depth})",
                suggestion="Consider flattening the query structure or using fragments"
            ))

        # Too many fields
        if complexity.field_count > 100:
            issues.append(QueryIssue(
                issue_type=QueryIssueType.LARGE_RESULT_SET,
                severity=QuerySeverity.MEDIUM,
                message=f"Query requests many fields ({complexity.field_count})",
                suggestion="Consider selecting only necessary fields"
            ))

        # Expensive fields
        for field_path in complexity.expensive_fields:
            issues.append(QueryIssue(
                issue_type=QueryIssueType.EXPENSIVE_FIELD,
                severity=QuerySeverity.MEDIUM,
                message=f"Expensive field detected: {field_path}",
                field_path=field_path,
                complexity_score=complexity.complexity_by_field.get(field_path, 0),
                suggestion="Consider caching or pagination for this field"
            ))

        return issues

    def _check_security_issues(self, query: str) -> List[QueryIssue]:
        """Check for security-related issues."""
        issues = []

        for pattern, message in self.security_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                severity = QuerySeverity.HIGH
                if "introspection" in message.lower():
                    severity = QuerySeverity.MEDIUM  # Introspection might be allowed
                elif "delete" in message.lower():
                    severity = QuerySeverity.CRITICAL

                issues.append(QueryIssue(
                    issue_type=QueryIssueType.SECURITY_RISK,
                    severity=severity,
                    message=message,
                    location={
                        'start': match.start(),
                        'end': match.end(),
                        'text': match.group()
                    },
                    suggestion="Review if this operation is necessary and properly authorized"
                ))

        return issues

    def _check_performance_issues(self, query: str, document) -> List[QueryIssue]:
        """Check for performance-related issues."""
        issues = []

        # Check performance anti-patterns
        for pattern, message in self.performance_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                issues.append(QueryIssue(
                    issue_type=QueryIssueType.INEFFICIENT_PATTERN,
                    severity=QuerySeverity.MEDIUM,
                    message=message,
                    location={
                        'start': match.start(),
                        'end': match.end(),
                        'text': match.group()
                    },
                    suggestion="Consider using DataLoader or optimizing the query structure"
                ))

        # Check for duplicate fields (simplified check)
        field_names = re.findall(r'\b(\w+)\s*{', query)
        field_counts = {}
        for field in field_names:
            field_counts[field] = field_counts.get(field, 0) + 1

        for field, count in field_counts.items():
            if count > 1:
                issues.append(QueryIssue(
                    issue_type=QueryIssueType.DUPLICATE_FIELDS,
                    severity=QuerySeverity.LOW,
                    message=f"Field '{field}' appears {count} times",
                    field_path=field,
                    suggestion="Consider using fragments to avoid duplication"
                ))

        return issues

    def _check_deprecated_fields(self, document) -> List[QueryIssue]:
        """Check for usage of deprecated fields."""
        issues = []

        class DeprecatedFieldVisitor(Visitor):
            def __init__(self, deprecated_fields: Set[str]):
                # Initialize parent Visitor class to set up enter_leave_map
                super().__init__()

                self.deprecated_fields = deprecated_fields
                self.issues = []

            def enter_field(self, node: FieldNode, *_):
                field_name = node.name.value
                if field_name in self.deprecated_fields:
                    self.issues.append(QueryIssue(
                        issue_type=QueryIssueType.DEPRECATED_FIELD,
                        severity=QuerySeverity.LOW,
                        message=f"Deprecated field used: {field_name}",
                        field_path=field_name,
                        suggestion="Consider using the recommended alternative field"
                    ))
                return node

        if self.deprecated_fields:
            visitor = DeprecatedFieldVisitor(self.deprecated_fields)
            visit(document, visitor)
            issues.extend(visitor.issues)

        return issues

    def _generate_suggestions(self, result: QueryAnalysisResult) -> List[str]:
        """Generate optimization suggestions based on analysis."""
        suggestions = []

        # Complexity suggestions
        if result.complexity.total_score > self.max_complexity * 0.8:
            suggestions.append("Consider breaking this query into smaller operations")

        if result.complexity.max_depth > self.max_depth * 0.8:
            suggestions.append("Consider reducing query nesting depth")

        if result.complexity.field_count > 50:
            suggestions.append("Consider selecting only the fields you need")

        # Fragment suggestions
        if result.complexity.field_count > 20 and result.complexity.fragment_count == 0:
            suggestions.append("Consider using fragments to organize and reuse field selections")

        # Performance suggestions
        high_severity_issues = [i for i in result.issues if i.severity == QuerySeverity.HIGH]
        if high_severity_issues:
            suggestions.append("Address high-severity issues to improve performance")

        # Security suggestions
        security_issues = [i for i in result.issues if i.issue_type == QueryIssueType.SECURITY_RISK]
        if security_issues:
            suggestions.append("Review security implications of this query")

        return suggestions

    def _calculate_security_score(self, issues: List[QueryIssue]) -> float:
        """Calculate security score (0-100, higher is better)."""
        security_issues = [i for i in issues if i.issue_type == QueryIssueType.SECURITY_RISK]

        if not security_issues:
            return 100.0

        # Deduct points based on severity
        deductions = 0
        for issue in security_issues:
            if issue.severity == QuerySeverity.CRITICAL:
                deductions += 50
            elif issue.severity == QuerySeverity.HIGH:
                deductions += 25
            elif issue.severity == QuerySeverity.MEDIUM:
                deductions += 10
            else:
                deductions += 5

        return max(0.0, 100.0 - deductions)

    def _calculate_performance_score(self, result: QueryAnalysisResult) -> float:
        """Calculate performance score (0-100, higher is better)."""
        score = 100.0

        # Complexity penalty
        complexity_ratio = result.complexity.total_score / self.max_complexity
        if complexity_ratio > 1.0:
            score -= 30 * (complexity_ratio - 1.0)
        elif complexity_ratio > 0.8:
            score -= 10 * (complexity_ratio - 0.8) / 0.2

        # Depth penalty
        depth_ratio = result.complexity.max_depth / self.max_depth
        if depth_ratio > 1.0:
            score -= 20 * (depth_ratio - 1.0)
        elif depth_ratio > 0.8:
            score -= 10 * (depth_ratio - 0.8) / 0.2

        # Issue penalties
        for issue in result.issues:
            if issue.issue_type in [QueryIssueType.INEFFICIENT_PATTERN,
                                    QueryIssueType.EXPENSIVE_FIELD]:
                if issue.severity == QuerySeverity.HIGH:
                    score -= 15
                elif issue.severity == QuerySeverity.MEDIUM:
                    score -= 10
                else:
                    score -= 5

        return max(0.0, score)

    def _estimate_execution_time(self, result: QueryAnalysisResult) -> float:
        """Estimate query execution time in milliseconds."""
        # Base time
        base_time = 10.0  # 10ms base

        # Complexity factor
        complexity_factor = result.complexity.total_score / 100

        # Field count factor
        field_factor = result.complexity.field_count / 10

        # Depth factor
        depth_factor = result.complexity.max_depth ** 1.5

        # Expensive field factor
        expensive_factor = len(result.complexity.expensive_fields) * 50

        estimated_time = base_time + (complexity_factor * 5) + \
            (field_factor * 2) + depth_factor + expensive_factor

        return estimated_time

    def _extract_location(self, error: GraphQLError) -> Optional[Dict[str, Any]]:
        """Extract location information from GraphQL error."""
        if hasattr(error, 'locations') and error.locations:
            location = error.locations[0]
            return {
                'line': location.line,
                'column': location.column
            }
        return None

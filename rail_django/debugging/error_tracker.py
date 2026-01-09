"""
Error tracking module.

This module provides comprehensive error tracking and analysis for GraphQL operations,
including error categorization, trend analysis, and alerting.
"""

import hashlib
import json
import logging
import threading
import traceback
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors that can be tracked."""
    VALIDATION_ERROR = "validation_error"
    EXECUTION_ERROR = "execution_error"
    SCHEMA_ERROR = "schema_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TIMEOUT_ERROR = "timeout_error"
    NETWORK_ERROR = "network_error"
    DATABASE_ERROR = "database_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """Context information for an error."""
    operation_name: Optional[str] = None
    query: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    client_info: Optional[Dict[str, Any]] = None
    schema_name: Optional[str] = None
    field_path: Optional[str] = None


@dataclass
class ErrorOccurrence:
    """Represents a single error occurrence."""
    error_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    timestamp: datetime
    context: ErrorContext
    stack_trace: Optional[str] = None
    resolved: bool = False
    resolution_notes: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class ErrorPattern:
    """Represents a pattern of similar errors."""
    pattern_id: str
    category: ErrorCategory
    message_pattern: str
    occurrences: List[ErrorOccurrence] = field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    frequency: int = 0
    affected_operations: Set[str] = field(default_factory=set)
    affected_users: Set[str] = field(default_factory=set)


@dataclass
class ErrorTrend:
    """Error trend analysis."""
    category: ErrorCategory
    time_period: str
    error_count: int
    unique_errors: int
    trend_direction: str  # 'increasing', 'decreasing', 'stable'
    change_percentage: float
    top_errors: List[str] = field(default_factory=list)


@dataclass
class ErrorAlert:
    """Error alert when thresholds are exceeded."""
    alert_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    threshold_type: str  # 'rate', 'count', 'new_error'
    current_value: float
    threshold_value: float
    time_window: str
    timestamp: datetime
    affected_operations: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


class ErrorTracker:
    """
    Comprehensive error tracking and analysis system.

    Tracks GraphQL errors, categorizes them, identifies patterns,
    and provides alerting when error rates exceed thresholds.
    """

    def __init__(self,
                 max_errors_per_pattern: int = 1000,
                 error_retention_hours: int = 168,  # 1 week
                 enable_pattern_detection: bool = True,
                 enable_trend_analysis: bool = True,
                 alert_callbacks: List[Callable[[ErrorAlert], None]] = None):

        self.max_errors_per_pattern = max_errors_per_pattern
        self.error_retention_hours = error_retention_hours
        self.enable_pattern_detection = enable_pattern_detection
        self.enable_trend_analysis = enable_trend_analysis
        self.alert_callbacks = alert_callbacks or []

        # Error storage
        self._errors: deque = deque(maxlen=10000)
        self._error_patterns: Dict[str, ErrorPattern] = {}
        self._error_counts: Dict[ErrorCategory, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )

        # Alert thresholds
        self._alert_thresholds = {
            ErrorCategory.CRITICAL: {
                'rate_per_minute': 5.0,
                'count_per_hour': 50
            },
            ErrorCategory.HIGH: {
                'rate_per_minute': 10.0,
                'count_per_hour': 100
            },
            ErrorCategory.MEDIUM: {
                'rate_per_minute': 20.0,
                'count_per_hour': 200
            }
        }

        # Tracking state
        self._lock = threading.RLock()
        self._last_cleanup = datetime.now()

        # Error categorization rules
        self._categorization_rules = self._setup_categorization_rules()

        self.logger = logging.getLogger(__name__)

    def track_error(self, error: Exception, context: ErrorContext = None,
                    severity: ErrorSeverity = None, tags: Dict[str, str] = None) -> str:
        """
        Track a new error occurrence.

        Args:
            error: The exception that occurred
            context: Context information about the error
            severity: Error severity (auto-detected if not provided)
            tags: Additional tags for the error

        Returns:
            Error ID for tracking
        """
        # Generate error ID
        error_message = str(error)
        error_id = self._generate_error_id(error_message, context)

        # Categorize error
        category = self._categorize_error(error, context)

        # Determine severity if not provided
        if severity is None:
            severity = self._determine_severity(error, category, context)

        # Create error occurrence
        occurrence = ErrorOccurrence(
            error_id=error_id,
            category=category,
            severity=severity,
            message=error_message,
            timestamp=datetime.now(),
            context=context or ErrorContext(),
            stack_trace=traceback.format_exc() if error else None,
            tags=tags or {}
        )

        with self._lock:
            # Store error
            self._errors.append(occurrence)

            # Update error counts for trend analysis
            self._error_counts[category].append({
                'timestamp': occurrence.timestamp,
                'severity': severity,
                'operation': context.operation_name if context else None
            })

            # Pattern detection
            if self.enable_pattern_detection:
                self._update_error_patterns(occurrence)

            # Check alert thresholds
            self._check_alert_thresholds(occurrence)

        # Log the error
        log_level = self._get_log_level(severity)
        self.logger.log(
            log_level,
            f"Error tracked: {category.value} - {error_message[:200]}",
            extra={
                'error_id': error_id,
                'category': category.value,
                'severity': severity.value,
                'operation': context.operation_name if context else None
            }
        )

        return error_id

    def get_error(self, error_id: str) -> Optional[ErrorOccurrence]:
        """Get a specific error by ID."""
        with self._lock:
            for error in self._errors:
                if error.error_id == error_id:
                    return error
        return None

    def get_errors(self,
                   category: ErrorCategory = None,
                   severity: ErrorSeverity = None,
                   operation_name: str = None,
                   hours_back: int = 24,
                   limit: int = 100) -> List[ErrorOccurrence]:
        """
        Get errors with optional filtering.

        Args:
            category: Filter by error category
            severity: Filter by error severity
            operation_name: Filter by operation name
            hours_back: How many hours back to search
            limit: Maximum number of errors to return

        Returns:
            List of matching errors
        """
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        with self._lock:
            filtered_errors = []

            for error in reversed(self._errors):  # Most recent first
                if error.timestamp < cutoff_time:
                    continue

                if category and error.category != category:
                    continue

                if severity and error.severity != severity:
                    continue

                if (operation_name and
                        error.context.operation_name != operation_name):
                    continue

                filtered_errors.append(error)

                if len(filtered_errors) >= limit:
                    break

        return filtered_errors

    def get_error_patterns(self,
                           category: ErrorCategory = None,
                           min_occurrences: int = 2,
                           hours_back: int = 24) -> List[ErrorPattern]:
        """Get error patterns with optional filtering."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        with self._lock:
            patterns = []

            for pattern in self._error_patterns.values():
                if category and pattern.category != category:
                    continue

                if pattern.frequency < min_occurrences:
                    continue

                if pattern.last_seen and pattern.last_seen < cutoff_time:
                    continue

                patterns.append(pattern)

        # Sort by frequency (most common first)
        patterns.sort(key=lambda p: p.frequency, reverse=True)
        return patterns

    def get_error_stats(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get comprehensive error statistics."""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        stats = {
            'total_errors': 0,
            'by_category': defaultdict(int),
            'by_severity': defaultdict(int),
            'by_operation': defaultdict(int),
            'unique_errors': 0,
            'resolved_errors': 0,
            'error_rate_per_hour': 0.0,
            'top_operations': [],
            'recent_patterns': []
        }

        with self._lock:
            recent_errors = [
                error for error in self._errors
                if error.timestamp >= cutoff_time
            ]

            stats['total_errors'] = len(recent_errors)

            unique_error_ids = set()

            for error in recent_errors:
                stats['by_category'][error.category.value] += 1
                stats['by_severity'][error.severity.value] += 1

                if error.context.operation_name:
                    stats['by_operation'][error.context.operation_name] += 1

                unique_error_ids.add(error.error_id)

                if error.resolved:
                    stats['resolved_errors'] += 1

            stats['unique_errors'] = len(unique_error_ids)

            # Calculate error rate
            if hours_back > 0:
                stats['error_rate_per_hour'] = stats['total_errors'] / hours_back

            # Top operations by error count
            stats['top_operations'] = sorted(
                stats['by_operation'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            # Recent patterns
            stats['recent_patterns'] = [
                {
                    'pattern_id': p.pattern_id,
                    'category': p.category.value,
                    'frequency': p.frequency,
                    'message_pattern': p.message_pattern[:100]
                }
                for p in self.get_error_patterns(hours_back=hours_back)[:5]
            ]

        return stats

    def get_error_trends(self, hours_back: int = 24,
                         time_buckets: int = 12) -> List[ErrorTrend]:
        """Analyze error trends over time."""
        if not self.enable_trend_analysis:
            return []

        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        bucket_size = timedelta(hours=hours_back / time_buckets)

        trends = []

        with self._lock:
            for category in ErrorCategory:
                category_errors = [
                    error for error in self._errors
                    if (error.timestamp >= cutoff_time and
                        error.category == category)
                ]

                if not category_errors:
                    continue

                # Create time buckets
                buckets = []
                current_time = cutoff_time

                for _ in range(time_buckets):
                    bucket_end = current_time + bucket_size
                    bucket_errors = [
                        error for error in category_errors
                        if current_time <= error.timestamp < bucket_end
                    ]

                    buckets.append(len(bucket_errors))
                    current_time = bucket_end

                # Analyze trend
                if len(buckets) >= 2:
                    recent_avg = sum(buckets[-3:]) / 3 if len(buckets) >= 3 else buckets[-1]
                    earlier_avg = sum(buckets[:3]) / 3 if len(buckets) >= 3 else buckets[0]

                    if recent_avg > earlier_avg * 1.2:
                        trend_direction = 'increasing'
                        change_percentage = ((recent_avg - earlier_avg) / earlier_avg) * 100
                    elif recent_avg < earlier_avg * 0.8:
                        trend_direction = 'decreasing'
                        change_percentage = ((earlier_avg - recent_avg) / earlier_avg) * 100
                    else:
                        trend_direction = 'stable'
                        change_percentage = 0.0

                    # Top errors in this category
                    error_counts = defaultdict(int)
                    for error in category_errors:
                        error_counts[error.message[:50]] += 1

                    top_errors = sorted(
                        error_counts.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:5]

                    trends.append(ErrorTrend(
                        category=category,
                        time_period=f"{hours_back}h",
                        error_count=len(category_errors),
                        unique_errors=len(set(e.error_id for e in category_errors)),
                        trend_direction=trend_direction,
                        change_percentage=change_percentage,
                        top_errors=[error[0] for error in top_errors]
                    ))

        return trends

    def resolve_error(self, error_id: str, resolution_notes: str = None) -> bool:
        """Mark an error as resolved."""
        with self._lock:
            for error in self._errors:
                if error.error_id == error_id:
                    error.resolved = True
                    error.resolution_notes = resolution_notes

                    self.logger.info(
                        f"Error resolved: {error_id}",
                        extra={'resolution_notes': resolution_notes}
                    )
                    return True

        return False

    def add_alert_callback(self, callback: Callable[[ErrorAlert], None]):
        """Add callback for error alerts."""
        self.alert_callbacks.append(callback)

    def set_alert_threshold(self, category: ErrorCategory,
                            threshold_type: str, value: float):
        """Set alert threshold for error category."""
        if category not in self._alert_thresholds:
            self._alert_thresholds[category] = {}

        self._alert_thresholds[category][threshold_type] = value

    def export_errors(self, format: str = 'json', hours_back: int = 24) -> str:
        """Export error data in specified format."""
        errors = self.get_errors(hours_back=hours_back, limit=1000)

        if format == 'json':
            return self._export_json(errors)
        elif format == 'csv':
            return self._export_csv(errors)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def clear_errors(self, category: ErrorCategory = None, hours_back: int = None):
        """Clear error data."""
        with self._lock:
            if category is None and hours_back is None:
                # Clear all
                self._errors.clear()
                self._error_patterns.clear()
                self._error_counts.clear()
            else:
                # Selective clearing
                cutoff_time = None
                if hours_back:
                    cutoff_time = datetime.now() - timedelta(hours=hours_back)

                # Filter errors
                filtered_errors = deque()
                for error in self._errors:
                    keep = True

                    if category and error.category == category:
                        keep = False

                    if cutoff_time and error.timestamp < cutoff_time:
                        keep = False

                    if keep:
                        filtered_errors.append(error)

                self._errors = filtered_errors

    def _generate_error_id(self, message: str, context: ErrorContext = None) -> str:
        """Generate unique error ID based on message and context."""
        # Create a hash based on error message and key context
        hash_input = message

        if context:
            if context.operation_name:
                hash_input += f"|{context.operation_name}"
            if context.field_path:
                hash_input += f"|{context.field_path}"

        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    def _categorize_error(self, error: Exception,
                          context: ErrorContext = None) -> ErrorCategory:
        """Categorize error based on type and context."""
        error_type = type(error).__name__
        error_message = str(error).lower()

        # Apply categorization rules
        for rule_category, rules in self._categorization_rules.items():
            for rule in rules:
                if rule['type'] == 'exception_type' and error_type in rule['patterns']:
                    return rule_category
                elif rule['type'] == 'message_pattern':
                    for pattern in rule['patterns']:
                        if pattern in error_message:
                            return rule_category

        return ErrorCategory.UNKNOWN_ERROR

    def _determine_severity(self, error: Exception, category: ErrorCategory,
                            context: ErrorContext = None) -> ErrorSeverity:
        """Determine error severity based on type and context."""
        # Critical errors
        if category in [ErrorCategory.SCHEMA_ERROR, ErrorCategory.DATABASE_ERROR]:
            return ErrorSeverity.CRITICAL

        # High severity errors
        if category in [ErrorCategory.AUTHENTICATION_ERROR,
                        ErrorCategory.AUTHORIZATION_ERROR,
                        ErrorCategory.TIMEOUT_ERROR]:
            return ErrorSeverity.HIGH

        # Medium severity errors
        if category in [ErrorCategory.VALIDATION_ERROR,
                        ErrorCategory.RATE_LIMIT_ERROR]:
            return ErrorSeverity.MEDIUM

        # Default to low severity
        return ErrorSeverity.LOW

    def _setup_categorization_rules(self) -> Dict[ErrorCategory, List[Dict]]:
        """Setup error categorization rules."""
        return {
            ErrorCategory.VALIDATION_ERROR: [
                {
                    'type': 'exception_type',
                    'patterns': ['ValidationError', 'GraphQLError']
                },
                {
                    'type': 'message_pattern',
                    'patterns': ['validation', 'invalid', 'required field']
                }
            ],
            ErrorCategory.AUTHENTICATION_ERROR: [
                {
                    'type': 'message_pattern',
                    'patterns': ['authentication', 'login', 'unauthorized', 'token']
                }
            ],
            ErrorCategory.AUTHORIZATION_ERROR: [
                {
                    'type': 'message_pattern',
                    'patterns': ['permission', 'forbidden', 'access denied']
                }
            ],
            ErrorCategory.DATABASE_ERROR: [
                {
                    'type': 'exception_type',
                    'patterns': ['DatabaseError', 'IntegrityError', 'OperationalError']
                },
                {
                    'type': 'message_pattern',
                    'patterns': ['database', 'connection', 'sql', 'constraint']
                }
            ],
            ErrorCategory.TIMEOUT_ERROR: [
                {
                    'type': 'message_pattern',
                    'patterns': ['timeout', 'timed out', 'deadline exceeded']
                }
            ],
            ErrorCategory.RATE_LIMIT_ERROR: [
                {
                    'type': 'message_pattern',
                    'patterns': ['rate limit', 'too many requests', 'throttled']
                }
            ]
        }

    def _update_error_patterns(self, occurrence: ErrorOccurrence):
        """Update error patterns with new occurrence."""
        # Create pattern key based on error message (simplified)
        pattern_key = self._create_pattern_key(occurrence.message)

        if pattern_key not in self._error_patterns:
            self._error_patterns[pattern_key] = ErrorPattern(
                pattern_id=pattern_key,
                category=occurrence.category,
                message_pattern=occurrence.message[:100],
                first_seen=occurrence.timestamp
            )

        pattern = self._error_patterns[pattern_key]
        pattern.occurrences.append(occurrence)
        pattern.last_seen = occurrence.timestamp
        pattern.frequency += 1

        if occurrence.context.operation_name:
            pattern.affected_operations.add(occurrence.context.operation_name)

        if occurrence.context.user_id:
            pattern.affected_users.add(occurrence.context.user_id)

        # Limit occurrences per pattern
        if len(pattern.occurrences) > self.max_errors_per_pattern:
            pattern.occurrences = pattern.occurrences[-self.max_errors_per_pattern:]

    def _create_pattern_key(self, message: str) -> str:
        """Create pattern key from error message."""
        # Normalize message for pattern matching
        normalized = message.lower()

        # Remove variable parts (numbers, IDs, etc.)
        import re
        normalized = re.sub(r'\d+', 'N', normalized)
        normalized = re.sub(r'[a-f0-9]{8,}', 'ID', normalized)

        return hashlib.md5(normalized.encode()).hexdigest()[:8]

    def _check_alert_thresholds(self, occurrence: ErrorOccurrence):
        """Check if error occurrence triggers any alerts."""
        category = occurrence.category

        if category not in self._alert_thresholds:
            return

        thresholds = self._alert_thresholds[category]

        # Check rate threshold
        if 'rate_per_minute' in thresholds:
            rate_threshold = thresholds['rate_per_minute']
            recent_errors = self._count_recent_errors(category, minutes=1)

            if recent_errors >= rate_threshold:
                alert = ErrorAlert(
                    alert_id=f"rate_{category.value}_{datetime.now().isoformat()}",
                    category=category,
                    severity=occurrence.severity,
                    message=f"High error rate: {recent_errors} {category.value} errors in 1 minute",
                    threshold_type='rate_per_minute',
                    current_value=recent_errors,
                    threshold_value=rate_threshold,
                    time_window='1 minute',
                    timestamp=datetime.now()
                )

                self._handle_alert(alert)

        # Check count threshold
        if 'count_per_hour' in thresholds:
            count_threshold = thresholds['count_per_hour']
            recent_errors = self._count_recent_errors(category, hours=1)

            if recent_errors >= count_threshold:
                alert = ErrorAlert(
                    alert_id=f"count_{category.value}_{datetime.now().isoformat()}",
                    category=category,
                    severity=occurrence.severity,
                    message=f"High error count: {recent_errors} {category.value} errors in 1 hour",
                    threshold_type='count_per_hour',
                    current_value=recent_errors,
                    threshold_value=count_threshold,
                    time_window='1 hour',
                    timestamp=datetime.now()
                )

                self._handle_alert(alert)

    def _count_recent_errors(self, category: ErrorCategory,
                             minutes: int = None, hours: int = None) -> int:
        """Count recent errors for a category."""
        if minutes:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
        elif hours:
            cutoff_time = datetime.now() - timedelta(hours=hours)
        else:
            return 0

        count = 0
        for error in reversed(self._errors):
            if error.timestamp < cutoff_time:
                break
            if error.category == category:
                count += 1

        return count

    def _handle_alert(self, alert: ErrorAlert):
        """Handle an error alert."""
        # Log the alert
        self.logger.error(
            f"Error alert: {alert.message}",
            extra={
                'alert_id': alert.alert_id,
                'category': alert.category.value,
                'threshold_type': alert.threshold_type,
                'current_value': alert.current_value,
                'threshold_value': alert.threshold_value
            }
        )

        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")

    def _get_log_level(self, severity: ErrorSeverity) -> int:
        """Get Python logging level for error severity."""
        mapping = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }
        return mapping.get(severity, logging.ERROR)

    def _export_json(self, errors: List[ErrorOccurrence]) -> str:
        """Export errors as JSON."""
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'total_errors': len(errors),
            'errors': []
        }

        for error in errors:
            error_data = {
                'error_id': error.error_id,
                'category': error.category.value,
                'severity': error.severity.value,
                'message': error.message,
                'timestamp': error.timestamp.isoformat(),
                'resolved': error.resolved,
                'context': {
                    'operation_name': error.context.operation_name,
                    'user_id': error.context.user_id,
                    'session_id': error.context.session_id,
                    'schema_name': error.context.schema_name,
                    'field_path': error.context.field_path
                },
                'tags': error.tags
            }

            if error.resolution_notes:
                error_data['resolution_notes'] = error.resolution_notes

            export_data['errors'].append(error_data)

        return json.dumps(export_data, indent=2, ensure_ascii=False)

    def _export_csv(self, errors: List[ErrorOccurrence]) -> str:
        """Export errors as CSV."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            'error_id', 'category', 'severity', 'message', 'timestamp',
            'operation_name', 'user_id', 'resolved', 'resolution_notes'
        ])

        # Data
        for error in errors:
            writer.writerow([
                error.error_id,
                error.category.value,
                error.severity.value,
                error.message,
                error.timestamp.isoformat(),
                error.context.operation_name or '',
                error.context.user_id or '',
                error.resolved,
                error.resolution_notes or ''
            ])

        return output.getvalue()

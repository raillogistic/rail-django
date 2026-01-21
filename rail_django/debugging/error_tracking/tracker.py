"""
ErrorTracker implementation.
"""

import hashlib
import json
import logging
import threading
import traceback
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from .types import (
    ErrorAlert,
    ErrorCategory,
    ErrorContext,
    ErrorOccurrence,
    ErrorPattern,
    ErrorSeverity,
    ErrorTrend,
)

logger = logging.getLogger(__name__)


class ErrorTracker:
    """
    Comprehensive error tracking and analysis system.
    """

    def __init__(self,
                 max_errors_per_pattern: int = 1000,
                 error_retention_hours: int = 168,
                 enable_pattern_detection: bool = True,
                 enable_trend_analysis: bool = True,
                 alert_callbacks: list[Callable[[ErrorAlert], None]] = None):

        self.max_errors_per_pattern = max_errors_per_pattern
        self.error_retention_hours = error_retention_hours
        self.enable_pattern_detection = enable_pattern_detection
        self.enable_trend_analysis = enable_trend_analysis
        self.alert_callbacks = alert_callbacks or []

        self._errors: deque = deque(maxlen=10000)
        self._error_patterns: dict[str, ErrorPattern] = {}
        self._error_counts: dict[ErrorCategory, deque] = defaultdict(lambda: deque(maxlen=1000))

        self._alert_thresholds = {
            ErrorCategory.CRITICAL: {'rate_per_minute': 5.0, 'count_per_hour': 50},
            ErrorCategory.HIGH: {'rate_per_minute': 10.0, 'count_per_hour': 100},
            ErrorCategory.MEDIUM: {'rate_per_minute': 20.0, 'count_per_hour': 200}
        }

        self._lock = threading.RLock()
        self._last_cleanup = datetime.now()
        self._categorization_rules = self._setup_categorization_rules()
        self.logger = logging.getLogger(__name__)

    def track_error(self, error: Exception, context: ErrorContext = None,
                    severity: ErrorSeverity = None, tags: dict[str, str] = None) -> str:
        """Track a new error occurrence."""
        error_message = str(error)
        error_id = self._generate_error_id(error_message, context)
        category = self._categorize_error(error, context)
        if severity is None: severity = self._determine_severity(error, category, context)

        occurrence = ErrorOccurrence(
            error_id=error_id, category=category, severity=severity, message=error_message,
            timestamp=datetime.now(), context=context or ErrorContext(),
            stack_trace=traceback.format_exc() if error else None, tags=tags or {}
        )

        with self._lock:
            self._errors.append(occurrence)
            self._error_counts[category].append({'timestamp': occurrence.timestamp, 'severity': severity, 'operation': context.operation_name if context else None})
            if self.enable_pattern_detection: self._update_error_patterns(occurrence)
            self._check_alert_thresholds(occurrence)

        self.logger.log(self._get_log_level(severity), f"Error tracked: {category.value} - {error_message[:200]}", extra={'error_id': error_id, 'category': category.value, 'severity': severity.value, 'operation': context.operation_name if context else None})
        return error_id

    def get_error(self, error_id: str) -> Optional[ErrorOccurrence]:
        with self._lock:
            for error in self._errors:
                if error.error_id == error_id: return error
        return None

    def get_errors(self, category: ErrorCategory = None, severity: ErrorSeverity = None, operation_name: str = None, hours_back: int = 24, limit: int = 100) -> list[ErrorOccurrence]:
        cutoff = datetime.now() - timedelta(hours=hours_back)
        with self._lock:
            filtered = []
            for error in reversed(self._errors):
                if error.timestamp < cutoff: continue
                if category and error.category != category: continue
                if severity and error.severity != severity: continue
                if operation_name and error.context.operation_name != operation_name: continue
                filtered.append(error)
                if len(filtered) >= limit: break
        return filtered

    def get_error_patterns(self, category: ErrorCategory = None, min_occurrences: int = 2, hours_back: int = 24) -> list[ErrorPattern]:
        cutoff = datetime.now() - timedelta(hours=hours_back)
        with self._lock:
            patterns = []
            for pattern in self._error_patterns.values():
                if category and pattern.category != category: continue
                if pattern.frequency < min_occurrences: continue
                if pattern.last_seen and pattern.last_seen < cutoff: continue
                patterns.append(pattern)
        patterns.sort(key=lambda p: p.frequency, reverse=True)
        return patterns

    def get_error_stats(self, hours_back: int = 24) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(hours=hours_back)
        stats = {'total_errors': 0, 'by_category': defaultdict(int), 'by_severity': defaultdict(int), 'by_operation': defaultdict(int), 'unique_errors': 0, 'resolved_errors': 0, 'error_rate_per_hour': 0.0, 'top_operations': [], 'recent_patterns': []}
        with self._lock:
            recent = [e for e in self._errors if e.timestamp >= cutoff]
            stats['total_errors'] = len(recent)
            u_ids = set()
            for e in recent:
                stats['by_category'][e.category.value] += 1
                stats['by_severity'][e.severity.value] += 1
                if e.context.operation_name: stats['by_operation'][e.context.operation_name] += 1
                u_ids.add(e.error_id)
                if e.resolved: stats['resolved_errors'] += 1
            stats['unique_errors'] = len(u_ids)
            if hours_back > 0: stats['error_rate_per_hour'] = len(recent) / hours_back
            stats['top_operations'] = sorted(stats['by_operation'].items(), key=lambda x: x[1], reverse=True)[:10]
            stats['recent_patterns'] = [{'pattern_id': p.pattern_id, 'category': p.category.value, 'frequency': p.frequency, 'message_pattern': p.message_pattern[:100]} for p in self.get_error_patterns(hours_back=hours_back)[:5]]
        return stats

    def get_error_trends(self, hours_back: int = 24, time_buckets: int = 12) -> list[ErrorTrend]:
        if not self.enable_trend_analysis: return []
        cutoff, bucket_size = datetime.now() - timedelta(hours=hours_back), timedelta(hours=hours_back / time_buckets)
        trends = []
        with self._lock:
            for category in ErrorCategory:
                cat_errors = [e for e in self._errors if e.timestamp >= cutoff and e.category == category]
                if not cat_errors: continue
                buckets = []
                cur = cutoff
                for _ in range(time_buckets):
                    nxt = cur + bucket_size
                    buckets.append(len([e for e in cat_errors if cur <= e.timestamp < nxt]))
                    cur = nxt
                if len(buckets) >= 2:
                    rec_avg = sum(buckets[-3:]) / 3 if len(buckets) >= 3 else buckets[-1]
                    ear_avg = sum(buckets[:3]) / 3 if len(buckets) >= 3 else buckets[0]
                    if rec_avg > ear_avg * 1.2: trend, chg = 'increasing', ((rec_avg - ear_avg) / ear_avg) * 100
                    elif rec_avg < ear_avg * 0.8: trend, chg = 'decreasing', ((ear_avg - rec_avg) / ear_avg) * 100
                    else: trend, chg = 'stable', 0.0
                    e_counts = defaultdict(int)
                    for e in cat_errors: e_counts[e.message[:50]] += 1
                    top = sorted(e_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    trends.append(ErrorTrend(category=category, time_period=f"{hours_back}h", error_count=len(cat_errors), unique_errors=len(set(e.error_id for e in cat_errors)), trend_direction=trend, change_percentage=chg, top_errors=[x[0] for x in top]))
        return trends

    def resolve_error(self, error_id: str, resolution_notes: str = None) -> bool:
        with self._lock:
            for error in self._errors:
                if error.error_id == error_id:
                    error.resolved, error.resolution_notes = True, resolution_notes
                    self.logger.info(f"Error resolved: {error_id}", extra={'resolution_notes': resolution_notes})
                    return True
        return False

    def add_alert_callback(self, callback: Callable[[ErrorAlert], None]):
        self.alert_callbacks.append(callback)

    def set_alert_threshold(self, category: ErrorCategory, threshold_type: str, value: float):
        if category not in self._alert_thresholds: self._alert_thresholds[category] = {}
        self._alert_thresholds[category][threshold_type] = value

    def export_errors(self, format: str = 'json', hours_back: int = 24) -> str:
        errors = self.get_errors(hours_back=hours_back, limit=1000)
        if format == 'json': return self._export_json(errors)
        if format == 'csv': return self._export_csv(errors)
        raise ValueError(f"Unsupported format: {format}")

    def clear_errors(self, category: ErrorCategory = None, hours_back: int = None):
        with self._lock:
            if category is None and hours_back is None: self._errors.clear(); self._error_patterns.clear(); self._error_counts.clear()
            else:
                cutoff = datetime.now() - timedelta(hours=hours_back) if hours_back else None
                self._errors = deque([e for e in self._errors if not ((category and e.category == category) or (cutoff and e.timestamp < cutoff))], maxlen=10000)

    def _generate_error_id(self, message: str, context: ErrorContext = None) -> str:
        inp = message
        if context:
            if context.operation_name: inp += f"|{context.operation_name}"
            if context.field_path: inp += f"|{context.field_path}"
        return hashlib.md5(inp.encode()).hexdigest()[:12]

    def _categorize_error(self, error: Exception, context: ErrorContext = None) -> ErrorCategory:
        e_type, e_msg = type(error).__name__, str(error).lower()
        for cat, rules in self._categorization_rules.items():
            for r in rules:
                if r['type'] == 'exception_type' and e_type in r['patterns']: return cat
                if r['type'] == 'message_pattern' and any(p in e_msg for p in r['patterns']): return cat
        return ErrorCategory.UNKNOWN_ERROR

    def _determine_severity(self, error: Exception, category: ErrorCategory, context: ErrorContext = None) -> ErrorSeverity:
        if category in [ErrorCategory.SCHEMA_ERROR, ErrorCategory.DATABASE_ERROR]: return ErrorSeverity.CRITICAL
        if category in [ErrorCategory.AUTHENTICATION_ERROR, ErrorCategory.AUTHORIZATION_ERROR, ErrorCategory.TIMEOUT_ERROR]: return ErrorSeverity.HIGH
        if category in [ErrorCategory.VALIDATION_ERROR, ErrorCategory.RATE_LIMIT_ERROR]: return ErrorSeverity.MEDIUM
        return ErrorSeverity.LOW

    def _setup_categorization_rules(self) -> dict[ErrorCategory, list[dict]]:
        return {
            ErrorCategory.VALIDATION_ERROR: [{'type': 'exception_type', 'patterns': ['ValidationError', 'GraphQLError']}, {'type': 'message_pattern', 'patterns': ['validation', 'invalid', 'required field']}],
            ErrorCategory.AUTHENTICATION_ERROR: [{'type': 'message_pattern', 'patterns': ['authentication', 'login', 'unauthorized', 'token']}],
            ErrorCategory.AUTHORIZATION_ERROR: [{'type': 'message_pattern', 'patterns': ['permission', 'forbidden', 'access denied']}],
            ErrorCategory.DATABASE_ERROR: [{'type': 'exception_type', 'patterns': ['DatabaseError', 'IntegrityError', 'OperationalError']}, {'type': 'message_pattern', 'patterns': ['database', 'connection', 'sql', 'constraint']}],
            ErrorCategory.TIMEOUT_ERROR: [{'type': 'message_pattern', 'patterns': ['timeout', 'timed out', 'deadline exceeded']}],
            ErrorCategory.RATE_LIMIT_ERROR: [{'type': 'message_pattern', 'patterns': ['rate limit', 'too many requests', 'throttled']}]
        }

    def _update_error_patterns(self, occurrence: ErrorOccurrence):
        key = self._create_pattern_key(occurrence.message)
        if key not in self._error_patterns: self._error_patterns[key] = ErrorPattern(pattern_id=key, category=occurrence.category, message_pattern=occurrence.message[:100], first_seen=occurrence.timestamp)
        p = self._error_patterns[key]
        p.occurrences.append(occurrence); p.last_seen, p.frequency = occurrence.timestamp, p.frequency + 1
        if occurrence.context.operation_name: p.affected_operations.add(occurrence.context.operation_name)
        if occurrence.context.user_id: p.affected_users.add(occurrence.context.user_id)
        if len(p.occurrences) > self.max_errors_per_pattern: p.occurrences = p.occurrences[-self.max_errors_per_pattern:]

    def _create_pattern_key(self, message: str) -> str:
        norm = re.sub(r'[a-f0-9]{8,}', 'ID', re.sub(r'\d+', 'N', message.lower()))
        return hashlib.md5(norm.encode()).hexdigest()[:8]

    def _check_alert_thresholds(self, occurrence: ErrorOccurrence):
        cat = occurrence.category
        if cat not in self._alert_thresholds: return
        t = self._alert_thresholds[cat]
        if 'rate_per_minute' in t:
            rate = self._count_recent_errors(cat, minutes=1)
            if rate >= t['rate_per_minute']: self._handle_alert(ErrorAlert(alert_id=f"rate_{cat.value}_{datetime.now().isoformat()}", category=cat, severity=occurrence.severity, message=f"High error rate: {rate} {cat.value} errors in 1 minute", threshold_type='rate_per_minute', current_value=rate, threshold_value=t['rate_per_minute'], time_window='1 minute', timestamp=datetime.now()))
        if 'count_per_hour' in t:
            cnt = self._count_recent_errors(cat, hours=1)
            if cnt >= t['count_per_hour']: self._handle_alert(ErrorAlert(alert_id=f"count_{cat.value}_{datetime.now().isoformat()}", category=cat, severity=occurrence.severity, message=f"High error count: {cnt} {cat.value} errors in 1 hour", threshold_type='count_per_hour', current_value=cnt, threshold_value=t['count_per_hour'], time_window='1 hour', timestamp=datetime.now()))

    def _count_recent_errors(self, category: ErrorCategory, minutes: int = None, hours: int = None) -> int:
        cutoff = datetime.now() - (timedelta(minutes=minutes) if minutes else timedelta(hours=hours))
        count = 0
        for e in reversed(self._errors):
            if e.timestamp < cutoff: break
            if e.category == category: count += 1
        return count

    def _handle_alert(self, alert: ErrorAlert):
        self.logger.error(f"Error alert: {alert.message}", extra={'alert_id': alert.alert_id, 'category': alert.category.value, 'threshold_type': alert.threshold_type, 'current_value': alert.current_value, 'threshold_value': alert.threshold_value})
        for cb in self.alert_callbacks:
            try: cb(alert)
            except Exception as e: self.logger.error(f"Error in alert callback: {e}")

    def _get_log_level(self, severity: ErrorSeverity) -> int:
        return {ErrorSeverity.LOW: logging.INFO, ErrorSeverity.MEDIUM: logging.WARNING, ErrorSeverity.HIGH: logging.ERROR, ErrorSeverity.CRITICAL: logging.CRITICAL}.get(severity, logging.ERROR)

    def _export_json(self, errors: list[ErrorOccurrence]) -> str:
        data = {'export_timestamp': datetime.now().isoformat(), 'total_errors': len(errors), 'errors': [{'error_id': e.error_id, 'category': e.category.value, 'severity': e.severity.value, 'message': e.message, 'timestamp': e.timestamp.isoformat(), 'resolved': e.resolved, 'context': {'operation_name': e.context.operation_name, 'user_id': e.context.user_id, 'session_id': e.context.session_id, 'schema_name': e.context.schema_name, 'field_path': e.context.field_path}, 'tags': e.tags, 'resolution_notes': e.resolution_notes} for e in errors]}
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _export_csv(self, errors: list[ErrorOccurrence]) -> str:
        import csv, io
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(['error_id', 'category', 'severity', 'message', 'timestamp', 'operation_name', 'user_id', 'resolved', 'resolution_notes'])
        for e in errors: w.writerow([e.error_id, e.category.value, e.severity.value, e.message, e.timestamp.isoformat(), e.context.operation_name or '', e.context.user_id or '', e.resolved, e.resolution_notes or ''])
        return out.getvalue()

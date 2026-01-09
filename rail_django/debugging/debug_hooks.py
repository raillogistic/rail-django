"""
Debug hooks module.

This module provides comprehensive debugging hooks for GraphQL schema operations,
including query execution, schema registration, and error handling.
"""

import json
import logging
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class DebugLevel(Enum):
    """Debug levels for controlling verbosity."""
    NONE = 0
    ERROR = 1
    WARNING = 2
    INFO = 3
    DEBUG = 4
    TRACE = 5


@dataclass
class DebugEvent:
    """Represents a debug event."""
    event_type: str
    timestamp: datetime
    level: DebugLevel
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[Exception] = None
    stack_trace: Optional[str] = None


@dataclass
class DebugSession:
    """Represents a debug session."""
    session_id: str
    start_time: datetime
    events: List[DebugEvent] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True


class DebugHooks:
    """
    Comprehensive debugging hooks for GraphQL schema operations.

    Provides hooks for schema registration, query execution, error handling,
    and performance monitoring with configurable debug levels.
    """

    def __init__(self, debug_level: DebugLevel = DebugLevel.INFO,
                 enable_performance_tracking: bool = True,
                 enable_query_logging: bool = True,
                 enable_error_tracking: bool = True,
                 max_events_per_session: int = 1000):
        self.debug_level = debug_level
        self.enable_performance_tracking = enable_performance_tracking
        self.enable_query_logging = enable_query_logging
        self.enable_error_tracking = enable_error_tracking
        self.max_events_per_session = max_events_per_session

        # Event storage
        self._sessions: Dict[str, DebugSession] = {}
        self._global_events: List[DebugEvent] = []
        self._lock = threading.RLock()

        # Hook callbacks
        self._pre_hooks: Dict[str, List[Callable]] = {}
        self._post_hooks: Dict[str, List[Callable]] = {}
        self._error_hooks: Dict[str, List[Callable]] = {}

        # Performance tracking
        self._operation_timings: Dict[str, List[float]] = {}

        self.logger = logging.getLogger(__name__)
        self._setup_logging()

    def _setup_logging(self):
        """Set up logging configuration."""
        if self.debug_level == DebugLevel.NONE:
            return

        # Configure logger level based on debug level
        level_mapping = {
            DebugLevel.ERROR: logging.ERROR,
            DebugLevel.WARNING: logging.WARNING,
            DebugLevel.INFO: logging.INFO,
            DebugLevel.DEBUG: logging.DEBUG,
            DebugLevel.TRACE: logging.DEBUG
        }

        self.logger.setLevel(level_mapping.get(self.debug_level, logging.INFO))

    def create_session(self, session_id: str, context: Dict[str, Any] = None) -> DebugSession:
        """
        Create a new debug session.

        Args:
            session_id: Unique identifier for the session
            context: Additional context for the session

        Returns:
            Created debug session
        """
        with self._lock:
            session = DebugSession(
                session_id=session_id,
                start_time=datetime.now(),
                context=context or {}
            )
            self._sessions[session_id] = session

            self._log_event(
                event_type="session_created",
                level=DebugLevel.INFO,
                message=f"Debug session '{session_id}' created",
                context={"session_id": session_id},
                session_id=session_id
            )

            return session

    def end_session(self, session_id: str):
        """End a debug session."""
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.is_active = False

                duration = (datetime.now() - session.start_time).total_seconds()

                self._log_event(
                    event_type="session_ended",
                    level=DebugLevel.INFO,
                    message=f"Debug session '{session_id}' ended after {duration:.2f}s",
                    context={
                        "session_id": session_id,
                        "duration_seconds": duration,
                        "total_events": len(session.events)
                    },
                    session_id=session_id
                )

    def get_session(self, session_id: str) -> Optional[DebugSession]:
        """Get a debug session by ID."""
        return self._sessions.get(session_id)

    def register_pre_hook(self, event_type: str, callback: Callable):
        """Register a pre-execution hook."""
        if event_type not in self._pre_hooks:
            self._pre_hooks[event_type] = []
        self._pre_hooks[event_type].append(callback)

    def register_post_hook(self, event_type: str, callback: Callable):
        """Register a post-execution hook."""
        if event_type not in self._post_hooks:
            self._post_hooks[event_type] = []
        self._post_hooks[event_type].append(callback)

    def register_error_hook(self, event_type: str, callback: Callable):
        """Register an error hook."""
        if event_type not in self._error_hooks:
            self._error_hooks[event_type] = []
        self._error_hooks[event_type].append(callback)

    @contextmanager
    def debug_operation(self, operation_name: str, context: Dict[str, Any] = None,
                        session_id: str = None):
        """
        Context manager for debugging operations.

        Args:
            operation_name: Name of the operation being debugged
            context: Additional context for the operation
            session_id: Optional session ID to associate with
        """
        start_time = time.time()
        operation_context = context or {}

        # Execute pre-hooks
        self._execute_hooks(self._pre_hooks.get(operation_name, []),
                            operation_name, operation_context)

        self._log_event(
            event_type="operation_started",
            level=DebugLevel.DEBUG,
            message=f"Operation '{operation_name}' started",
            context={"operation": operation_name, **operation_context},
            session_id=session_id
        )

        try:
            yield operation_context

            # Success - execute post-hooks
            duration_ms = (time.time() - start_time) * 1000

            if self.enable_performance_tracking:
                self._track_performance(operation_name, duration_ms)

            self._log_event(
                event_type="operation_completed",
                level=DebugLevel.DEBUG,
                message=f"Operation '{operation_name}' completed in {duration_ms:.2f}ms",
                context={"operation": operation_name, **operation_context},
                duration_ms=duration_ms,
                session_id=session_id
            )

            self._execute_hooks(self._post_hooks.get(operation_name, []),
                                operation_name, operation_context, duration_ms)

        except Exception as e:
            # Error - execute error hooks
            duration_ms = (time.time() - start_time) * 1000

            if self.enable_error_tracking:
                self._log_event(
                    event_type="operation_error",
                    level=DebugLevel.ERROR,
                    message=f"Operation '{operation_name}' failed: {str(e)}",
                    context={"operation": operation_name, **operation_context},
                    duration_ms=duration_ms,
                    error=e,
                    stack_trace=traceback.format_exc(),
                    session_id=session_id
                )

            self._execute_hooks(self._error_hooks.get(operation_name, []),
                                operation_name, operation_context, e)

            raise

    def log_schema_registration(self, schema_name: str, schema_config: Dict[str, Any],
                                session_id: str = None):
        """Log schema registration event."""
        if self.debug_level.value < DebugLevel.INFO.value:
            return

        self._log_event(
            event_type="schema_registered",
            level=DebugLevel.INFO,
            message=f"Schema '{schema_name}' registered",
            context={
                "schema_name": schema_name,
                "config": schema_config
            },
            session_id=session_id
        )

    def log_query_execution(self, query: str, variables: Dict[str, Any] = None,
                            operation_name: str = None, session_id: str = None):
        """Log GraphQL query execution."""
        if not self.enable_query_logging or self.debug_level.value < DebugLevel.DEBUG.value:
            return

        # Sanitize query for logging (remove sensitive data)
        sanitized_query = self._sanitize_query(query)
        sanitized_variables = self._sanitize_variables(variables or {})

        self._log_event(
            event_type="query_executed",
            level=DebugLevel.DEBUG,
            message=f"GraphQL query executed: {operation_name or 'unnamed'}",
            context={
                "query": sanitized_query,
                "variables": sanitized_variables,
                "operation_name": operation_name
            },
            session_id=session_id
        )

    def log_mutation_execution(self, mutation: str, variables: Dict[str, Any] = None,
                               operation_name: str = None, session_id: str = None):
        """Log GraphQL mutation execution."""
        if not self.enable_query_logging or self.debug_level.value < DebugLevel.DEBUG.value:
            return

        sanitized_mutation = self._sanitize_query(mutation)
        sanitized_variables = self._sanitize_variables(variables or {})

        self._log_event(
            event_type="mutation_executed",
            level=DebugLevel.DEBUG,
            message=f"GraphQL mutation executed: {operation_name or 'unnamed'}",
            context={
                "mutation": sanitized_mutation,
                "variables": sanitized_variables,
                "operation_name": operation_name
            },
            session_id=session_id
        )

    def log_validation_error(self, error: Exception, context: Dict[str, Any] = None,
                             session_id: str = None):
        """Log validation error."""
        if not self.enable_error_tracking:
            return

        self._log_event(
            event_type="validation_error",
            level=DebugLevel.ERROR,
            message=f"Validation error: {str(error)}",
            context=context or {},
            error=error,
            stack_trace=traceback.format_exc(),
            session_id=session_id
        )

    def log_performance_warning(self, operation: str, duration_ms: float,
                                threshold_ms: float = 1000, session_id: str = None):
        """Log performance warning for slow operations."""
        if duration_ms < threshold_ms:
            return

        self._log_event(
            event_type="performance_warning",
            level=DebugLevel.WARNING,
            message=f"Slow operation detected: '{operation}' took {duration_ms:.2f}ms (threshold: {threshold_ms}ms)",
            context={
                "operation": operation,
                "duration_ms": duration_ms,
                "threshold_ms": threshold_ms
            },
            duration_ms=duration_ms,
            session_id=session_id
        )

    def get_performance_stats(self, operation: str = None) -> Dict[str, Any]:
        """Get performance statistics."""
        with self._lock:
            if operation:
                timings = self._operation_timings.get(operation, [])
                if not timings:
                    return {"operation": operation, "stats": None}

                return {
                    "operation": operation,
                    "stats": {
                        "count": len(timings),
                        "avg_ms": sum(timings) / len(timings),
                        "min_ms": min(timings),
                        "max_ms": max(timings),
                        "total_ms": sum(timings)
                    }
                }
            else:
                # Return stats for all operations
                all_stats = {}
                for op_name, timings in self._operation_timings.items():
                    if timings:
                        all_stats[op_name] = {
                            "count": len(timings),
                            "avg_ms": sum(timings) / len(timings),
                            "min_ms": min(timings),
                            "max_ms": max(timings),
                            "total_ms": sum(timings)
                        }

                return {"all_operations": all_stats}

    def get_events(self, session_id: str = None, event_type: str = None,
                   level: DebugLevel = None, limit: int = None) -> List[DebugEvent]:
        """Get debug events with optional filtering."""
        with self._lock:
            if session_id:
                session = self._sessions.get(session_id)
                events = session.events if session else []
            else:
                events = self._global_events

            # Apply filters
            filtered_events = events

            if event_type:
                filtered_events = [e for e in filtered_events if e.event_type == event_type]

            if level:
                filtered_events = [e for e in filtered_events if e.level == level]

            # Apply limit
            if limit:
                filtered_events = filtered_events[-limit:]

            return filtered_events

    def export_debug_data(self, session_id: str = None, format: str = 'json') -> str:
        """Export debug data in specified format."""
        events = self.get_events(session_id=session_id)

        if format == 'json':
            return self._export_json(events, session_id)
        elif format == 'csv':
            return self._export_csv(events)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def clear_events(self, session_id: str = None):
        """Clear debug events."""
        with self._lock:
            if session_id:
                session = self._sessions.get(session_id)
                if session:
                    session.events.clear()
            else:
                self._global_events.clear()
                self._operation_timings.clear()

    def _log_event(self, event_type: str, level: DebugLevel, message: str,
                   context: Dict[str, Any] = None, duration_ms: float = None,
                   error: Exception = None, stack_trace: str = None,
                   session_id: str = None):
        """Log a debug event."""
        if level.value > self.debug_level.value:
            return

        event = DebugEvent(
            event_type=event_type,
            timestamp=datetime.now(),
            level=level,
            message=message,
            context=context or {},
            duration_ms=duration_ms,
            error=error,
            stack_trace=stack_trace
        )

        with self._lock:
            # Add to session if specified
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                session.events.append(event)

                # Limit events per session
                if len(session.events) > self.max_events_per_session:
                    session.events = session.events[-self.max_events_per_session:]

            # Add to global events
            self._global_events.append(event)

            # Limit global events
            if len(self._global_events) > self.max_events_per_session * 10:
                self._global_events = self._global_events[-self.max_events_per_session * 10:]

        # Log to Python logger
        log_level_mapping = {
            DebugLevel.ERROR: logging.ERROR,
            DebugLevel.WARNING: logging.WARNING,
            DebugLevel.INFO: logging.INFO,
            DebugLevel.DEBUG: logging.DEBUG,
            DebugLevel.TRACE: logging.DEBUG
        }

        python_level = log_level_mapping.get(level, logging.INFO)

        if error:
            self.logger.log(python_level, f"{message} - Error: {str(error)}")
        else:
            self.logger.log(python_level, message)

    def _execute_hooks(self, hooks: List[Callable], *args, **kwargs):
        """Execute a list of hooks safely."""
        for hook in hooks:
            try:
                hook(*args, **kwargs)
            except Exception as e:
                self.logger.error(f"Error executing hook: {e}")

    def _track_performance(self, operation: str, duration_ms: float):
        """Track performance metrics for an operation."""
        with self._lock:
            if operation not in self._operation_timings:
                self._operation_timings[operation] = []

            self._operation_timings[operation].append(duration_ms)

            # Keep only recent timings (last 1000)
            if len(self._operation_timings[operation]) > 1000:
                self._operation_timings[operation] = self._operation_timings[operation][-1000:]

    def _sanitize_query(self, query: str) -> str:
        """Sanitize GraphQL query for logging (remove sensitive data)."""
        # This is a basic implementation - in production, you'd want more sophisticated sanitization
        if len(query) > 1000:
            return query[:1000] + "... (truncated)"
        return query

    def _sanitize_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize variables for logging (remove sensitive data)."""
        sensitive_keys = {'password', 'token', 'secret', 'key', 'auth', 'credential'}

        sanitized = {}
        for key, value in variables.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 100:
                sanitized[key] = value[:100] + "... (truncated)"
            else:
                sanitized[key] = value

        return sanitized

    def _export_json(self, events: List[DebugEvent], session_id: str = None) -> str:
        """Export events as JSON."""
        export_data = {
            "session_id": session_id,
            "export_timestamp": datetime.now().isoformat(),
            "total_events": len(events),
            "events": []
        }

        for event in events:
            event_data = {
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "level": event.level.name,
                "message": event.message,
                "context": event.context,
                "duration_ms": event.duration_ms
            }

            if event.error:
                event_data["error"] = str(event.error)

            if event.stack_trace:
                event_data["stack_trace"] = event.stack_trace

            export_data["events"].append(event_data)

        return json.dumps(export_data, indent=2, ensure_ascii=False)

    def _export_csv(self, events: List[DebugEvent]) -> str:
        """Export events as CSV."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            'timestamp', 'event_type', 'level', 'message',
            'duration_ms', 'error', 'context'
        ])

        # Data
        for event in events:
            writer.writerow([
                event.timestamp.isoformat(),
                event.event_type,
                event.level.name,
                event.message,
                event.duration_ms or '',
                str(event.error) if event.error else '',
                json.dumps(event.context) if event.context else ''
            ])

        return output.getvalue()

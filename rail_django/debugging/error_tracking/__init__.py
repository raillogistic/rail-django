"""
Error tracking package.
"""

from .tracker import ErrorTracker
from .types import (
    ErrorAlert,
    ErrorCategory,
    ErrorContext,
    ErrorOccurrence,
    ErrorPattern,
    ErrorSeverity,
    ErrorTrend,
)

__all__ = [
    "ErrorTracker",
    "ErrorCategory",
    "ErrorSeverity",
    "ErrorContext",
    "ErrorOccurrence",
    "ErrorPattern",
    "ErrorTrend",
    "ErrorAlert",
]

"""
Query analyzer module.

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.debugging.query_analyzer` package.

DEPRECATION NOTICE:
    Importing from `rail_django.debugging.query_analyzer` module is deprecated.
    Please update your imports to use `rail_django.debugging.query_analyzer` package instead.
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.debugging.query_analyzer' module is deprecated. "
    "Use 'rail_django.debugging.query_analyzer' package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .query_analyzer.analyzer import QueryAnalyzer
from .query_analyzer.types import (
    QueryAnalysisResult,
    QueryComplexity,
    QueryIssue,
    QueryIssueType,
    QuerySeverity,
)
from .query_analyzer.visitor import ComplexityVisitor

__all__ = [
    "QueryAnalyzer",
    "ComplexityVisitor",
    "QueryIssueType",
    "QuerySeverity",
    "QueryIssue",
    "QueryComplexity",
    "QueryAnalysisResult",
]
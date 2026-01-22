"""
Custom exceptions for query generators.

This module defines specific exception types for better error handling
and debugging in query generation and filtering.
"""

from typing import Any, Dict, List, Optional


class QueryGeneratorError(Exception):
    """Base exception for query generator errors."""

    def __init__(self, message: str, model_name: Optional[str] = None):
        self.model_name = model_name
        super().__init__(message)


class FilterGenerationError(QueryGeneratorError):
    """Raised when filter input generation fails."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        field_name: Optional[str] = None,
    ):
        self.field_name = field_name
        super().__init__(message, model_name)


class FilterApplicationError(QueryGeneratorError):
    """Raised when applying a filter to a queryset fails."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        filter_key: Optional[str] = None,
        filter_value: Optional[Any] = None,
    ):
        self.filter_key = filter_key
        self.filter_value = filter_value
        super().__init__(message, model_name)


class SavedFilterError(QueryGeneratorError):
    """Raised when loading or applying a saved filter fails."""

    def __init__(
        self,
        message: str,
        filter_id: Optional[str] = None,
        filter_name: Optional[str] = None,
    ):
        self.filter_id = filter_id
        self.filter_name = filter_name
        super().__init__(message)


class PresetFilterError(QueryGeneratorError):
    """Raised when applying filter presets fails."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        preset_names: Optional[List[str]] = None,
    ):
        self.preset_names = preset_names
        super().__init__(message, model_name)


class OrderingError(QueryGeneratorError):
    """Raised when ordering configuration or application fails."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        field_name: Optional[str] = None,
    ):
        self.field_name = field_name
        super().__init__(message, model_name)


class PropertyOrderingError(OrderingError):
    """Raised when property-based ordering fails."""

    pass


class PaginationError(QueryGeneratorError):
    """Raised when pagination parameters are invalid."""

    def __init__(
        self,
        message: str,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
    ):
        self.page = page
        self.per_page = per_page
        super().__init__(message)


class FilterComplexityError(FilterApplicationError):
    """Raised when a filter exceeds complexity limits."""

    def __init__(
        self,
        message: str,
        depth: Optional[int] = None,
        clause_count: Optional[int] = None,
        max_depth: Optional[int] = None,
        max_clauses: Optional[int] = None,
    ):
        self.depth = depth
        self.clause_count = clause_count
        self.max_depth = max_depth
        self.max_clauses = max_clauses
        super().__init__(message)


class RegexPatternError(FilterApplicationError):
    """Raised when a regex pattern is invalid or potentially dangerous."""

    def __init__(
        self,
        message: str,
        pattern: Optional[str] = None,
    ):
        self.pattern = pattern
        super().__init__(message)


class FieldResolutionError(QueryGeneratorError):
    """Raised when a field cannot be resolved on a model."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        field_path: Optional[str] = None,
    ):
        self.field_path = field_path
        super().__init__(message, model_name)


class RelationshipError(QueryGeneratorError):
    """Raised when relationship traversal fails."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        relationship_name: Optional[str] = None,
    ):
        self.relationship_name = relationship_name
        super().__init__(message, model_name)

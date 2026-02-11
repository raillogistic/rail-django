"""Queryset Building and Filter Validation

This module provides mixin functionality for queryset building,
filter validation, and GraphQL filter application.
"""

import warnings
from typing import Any, Iterable, List, Optional, Union

from django.db import models

from ..config import normalize_filter_value
from ..exceptions import ExportError


class QuerysetMixin:
    """Mixin providing queryset building and filter functionality."""

    _LOGICAL_FILTER_KEYS = {"AND", "OR", "NOT"}

    def _normalize_filter_key(self, key: Any) -> Any:
        """Normalize a filter key from GraphQL naming to internal naming."""
        if not isinstance(key, str):
            return key
        if key in self._LOGICAL_FILTER_KEYS:
            return key

        normalized = key.replace(".", "__")
        parts = normalized.split("__")
        normalized_parts = []
        for part in parts:
            if not part:
                normalized_parts.append(part)
                continue
            normalized_parts.append(self._to_snake_case(part))
        return "__".join(normalized_parts)

    def _normalize_where_input(self, filter_input: Any) -> Any:
        """Recursively normalize where input keys to snake_case."""
        if isinstance(filter_input, list):
            return [self._normalize_where_input(item) for item in filter_input]
        if not isinstance(filter_input, dict):
            return filter_input

        normalized: dict[Any, Any] = {}
        for key, value in filter_input.items():
            normalized_key = self._normalize_filter_key(key)
            normalized[normalized_key] = self._normalize_where_input(value)
        return normalized

    def _analyze_filter_tree(
        self, filter_input: Any, *, current_or_depth: int = 0
    ) -> tuple[int, int]:
        """Return (filter_count, max_or_depth) for a filter tree.

        Args:
            filter_input: Filter input structure to analyze.
            current_or_depth: Current OR nesting depth.

        Returns:
            Tuple of (total filter count, max OR depth).
        """
        if not filter_input:
            return 0, current_or_depth

        if isinstance(filter_input, list):
            total = 0
            max_or_depth = current_or_depth
            for item in filter_input:
                count, depth = self._analyze_filter_tree(
                    item, current_or_depth=current_or_depth
                )
                total += count
                max_or_depth = max(max_or_depth, depth)
            return total, max_or_depth

        if not isinstance(filter_input, dict):
            return 0, current_or_depth

        total_filters = 0
        max_or_depth = current_or_depth

        for key, value in filter_input.items():
            if key == "AND":
                count, depth = self._analyze_filter_tree(
                    value, current_or_depth=current_or_depth
                )
                total_filters += count
                max_or_depth = max(max_or_depth, depth)
                continue
            if key == "OR":
                count, depth = self._analyze_filter_tree(
                    value, current_or_depth=current_or_depth + 1
                )
                total_filters += count
                max_or_depth = max(max_or_depth, depth)
                continue
            if key == "NOT":
                count, depth = self._analyze_filter_tree(
                    value, current_or_depth=current_or_depth
                )
                total_filters += count
                max_or_depth = max(max_or_depth, depth)
                continue

            total_filters += 1

        return total_filters, max_or_depth

    def _iter_filter_keys(self, filter_input: Any) -> Iterable[str]:
        """Yield filter keys from a filter tree.

        Args:
            filter_input: Filter input structure.

        Yields:
            Filter key strings.
        """
        if not filter_input:
            return

        if isinstance(filter_input, list):
            for item in filter_input:
                yield from self._iter_filter_keys(item)
            return

        if not isinstance(filter_input, dict):
            return

        for key, value in filter_input.items():
            if key in {"AND", "OR", "NOT"}:
                yield from self._iter_filter_keys(value)
                continue
            yield key

    def _is_filter_key_allowed(self, key: str) -> bool:
        """Check whether a filter key is allowlisted.

        Args:
            key: Filter key to check.

        Returns:
            True if the filter key is allowed.
        """
        if not key:
            return False
        normalized = normalize_filter_value(key)
        parts_for_private = normalized.split("__")
        if any(part.startswith("_") for part in parts_for_private):
            return False
        if normalized in self.filterable_special_fields:
            return True
        # If no filterable_fields configured, allow all (permissive default)
        if not self.filterable_fields:
            return True

        parts = normalized.split("__")
        if parts[-1] in self.allowed_filter_lookups:
            base_parts = parts[:-1]
            while base_parts and base_parts[-1] in self.allowed_filter_transforms:
                base_parts = base_parts[:-1]
            if not base_parts:
                return False
            base = "__".join(base_parts)
            return base in self.filterable_fields

        if parts[-1] in self.allowed_filter_transforms:
            base_parts = parts
            while base_parts and base_parts[-1] in self.allowed_filter_transforms:
                base_parts = base_parts[:-1]
            if not base_parts:
                return False
            base = "__".join(base_parts)
            return base in self.filterable_fields

        return normalized in self.filterable_fields

    def validate_filter_input(
        self,
        where_input: Optional[dict[str, Any]] = None,
        *,
        export_settings: Optional[dict[str, Any]] = None,
    ) -> None:
        """Validate filter input against export allowlists and complexity limits.

        Args:
            where_input: The where filter dictionary.
            export_settings: Optional export settings override.

        Raises:
            ExportError: If filters violate complexity or allowlist rules.
        """
        if not where_input:
            return
        if not isinstance(where_input, dict):
            raise ExportError("where must be an object")
        normalized_where_input = self._normalize_where_input(where_input)
        if not isinstance(normalized_where_input, dict):
            raise ExportError("where must be an object")

        export_settings = export_settings or self.export_settings

        # Import and use complexity validation from filter_inputs
        try:
            from ....generators.filters import validate_filter_complexity

            max_depth = export_settings.get("max_or_depth") or 10
            max_clauses = export_settings.get("max_filters") or 50
            try:
                max_depth = int(max_depth)
            except (TypeError, ValueError):
                max_depth = 10
            try:
                max_clauses = int(max_clauses)
            except (TypeError, ValueError):
                max_clauses = 50
            if max_depth <= 0:
                max_depth = 10
            if max_clauses <= 0:
                max_clauses = 50
            validate_filter_complexity(
                normalized_where_input, max_depth=max_depth, max_clauses=max_clauses
            )
        except ImportError:
            # Fall back to existing validation if filter_inputs unavailable
            max_filters = export_settings.get("max_filters", None)
            max_or_depth = export_settings.get("max_or_depth", None)
            total_filters, max_depth_found = self._analyze_filter_tree(
                normalized_where_input
            )

            if max_filters is not None:
                try:
                    max_filters = int(max_filters)
                except (TypeError, ValueError):
                    max_filters = None
            if max_filters is not None and max_filters <= 0:
                max_filters = None
            if max_filters is not None and total_filters > max_filters:
                raise ExportError("Too many filters were provided")

            if max_or_depth is not None:
                try:
                    max_or_depth = int(max_or_depth)
                except (TypeError, ValueError):
                    max_or_depth = None
            if max_or_depth is not None and max_or_depth <= 0:
                max_or_depth = None
            if max_or_depth is not None and max_depth_found > max_or_depth:
                raise ExportError("Filter OR depth exceeds limit")
        except Exception as e:
            raise ExportError(f"Filter complexity error: {e}")

        # Validate against export-specific field allowlists
        invalid_keys = [
            key
            for key in self._iter_filter_keys(normalized_where_input)
            if not self._is_filter_key_allowed(key)
        ]
        if invalid_keys:
            raise ExportError(
                "Filters not allowed: " + ", ".join(sorted(set(invalid_keys)))
            )

    def validate_filters(
        self,
        variables: Optional[dict[str, Any]] = None,
        *,
        export_settings: Optional[dict[str, Any]] = None,
    ) -> None:
        """Validate filter input against allowlists and guardrails.

        .. deprecated::
            Use :meth:`validate_filter_input` instead.
        """
        warnings.warn(
            "validate_filters() is deprecated; use validate_filter_input() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        if not variables:
            return

        export_settings = export_settings or self.export_settings
        filter_input = variables.get("where") or variables.get("filters", variables)
        self.validate_filter_input(filter_input, export_settings=export_settings)

    def get_queryset(
        self,
        variables: Optional[dict[str, Any]] = None,
        ordering: Optional[Union[str, list[str]]] = None,
        fields: Optional[Iterable[str]] = None,
        max_rows: Optional[int] = None,
        *,
        presets: Optional[List[str]] = None,
        skip_validation: bool = False,
        distinct_on: Optional[List[str]] = None,
    ) -> models.QuerySet:
        """Get the filtered and ordered queryset.

        Args:
            variables: Dictionary of filter kwargs.
            ordering: Django ORM ordering expression(s).
            fields: Field accessors for optimization.
            max_rows: Optional max rows cap.
            presets: Optional list of preset names.
            skip_validation: If True, skip filter validation.
            distinct_on: Optional list of field names for DISTINCT ON.

        Returns:
            Filtered and ordered queryset.

        Raises:
            ExportError: If filtering or ordering fails.
        """
        try:
            queryset = self.model.objects.all()

            # Apply GraphQL filters
            if variables:
                if not skip_validation:
                    where_input = variables.get("where", variables)
                    self.validate_filter_input(where_input)
                queryset = self.apply_graphql_filters(
                    queryset, variables, presets=presets
                )

            # Apply ordering (must come before distinct for PostgreSQL DISTINCT ON)
            ordering_fields = self._normalize_ordering(ordering)
            if ordering_fields:
                queryset = queryset.order_by(*ordering_fields)

            # Apply DISTINCT ON if specified (PostgreSQL only)
            if distinct_on:
                distinct_fields = [
                    f.replace(".", "__")
                    for f in distinct_on
                    if isinstance(f, str) and f
                ]
                if distinct_fields:
                    queryset = queryset.distinct(*distinct_fields)

            # Apply relation optimizations based on requested fields
            if fields:
                queryset = self._apply_related_optimizations(queryset, fields)

            if max_rows is not None and max_rows > 0:
                queryset = queryset[:max_rows]

            return queryset

        except Exception as e:
            raise ExportError(f"Error building queryset: {e}")

    def apply_graphql_filters(
        self,
        queryset: models.QuerySet,
        variables: dict[str, Any],
        *,
        presets: Optional[List[str]] = None,
    ) -> models.QuerySet:
        """Apply GraphQL filters to the queryset.

        Args:
            queryset: Django QuerySet to filter.
            variables: Filter parameters from the request.
            presets: Optional list of preset names.

        Returns:
            Filtered QuerySet.

        Raises:
            ExportError: If filtering fails.
        """
        if not variables:
            return queryset

        # Standardize on "where" key
        where_input = variables.get("where", variables)
        if not where_input:
            return queryset
        if not isinstance(where_input, dict):
            raise ExportError("where must be an object")
        normalized_where_input = self._normalize_where_input(where_input)
        if not normalized_where_input:
            return queryset
        if not isinstance(normalized_where_input, dict):
            raise ExportError("where must be an object")

        if not self.nested_filter_applicator:
            raise ExportError(
                "Nested filter applicator not available. "
                "Ensure filter_inputs module is accessible."
            )

        try:
            # Apply presets if provided
            if presets:
                normalized_where_input = self.nested_filter_applicator.apply_presets(
                    normalized_where_input, presets, self.model
                )
            return self.nested_filter_applicator.apply_where_filter(
                queryset, normalized_where_input, self.model
            )
        except Exception as e:
            raise ExportError(f"Filter application failed: {e}")

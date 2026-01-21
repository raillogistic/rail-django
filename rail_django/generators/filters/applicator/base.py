"""
Base filter applicator with core logic for applying nested filter inputs to Django querysets.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Type

from django.db import models
from django.db.models import Q
from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILTER_DEPTH = 10
DEFAULT_MAX_FILTER_CLAUSES = 100


class BaseFilterApplicatorMixin:
    """Base mixin providing core filter applicator functionality."""

    def __init__(self, schema_name: str = "default"):
        """Initialize the filter applicator with schema name for settings."""
        self.schema_name = schema_name
        self._quick_mixin = None
        self._include_mixin = None
        self._historical_mixin = None
        try:
            from ....core.settings import FilteringSettings
            self.filtering_settings = FilteringSettings.from_schema(self.schema_name)
        except (ImportError, AttributeError, KeyError):
            self.filtering_settings = None

    def _get_quick_mixin(self):
        """Get or create the quick filter mixin instance."""
        if self._quick_mixin is None:
            from ...filter_inputs import QuickFilterMixin
            self._quick_mixin = QuickFilterMixin()
        return self._quick_mixin

    def _get_include_mixin(self):
        """Get or create the include filter mixin instance."""
        if self._include_mixin is None:
            from ...filter_inputs import IncludeFilterMixin
            self._include_mixin = IncludeFilterMixin()
        return self._include_mixin

    def _get_historical_mixin(self):
        """Get or create the historical model mixin instance."""
        if self._historical_mixin is None:
            from ...filter_inputs import HistoricalModelMixin
            self._historical_mixin = HistoricalModelMixin()
        return self._historical_mixin

    def apply_presets(
        self,
        where_input: Dict[str, Any],
        presets: List[str],
        model: Type[models.Model],
    ) -> Dict[str, Any]:
        """Merge preset filters with user-provided filters."""
        if not presets:
            return where_input
        from ....core.meta import get_model_graphql_meta
        graphql_meta = get_model_graphql_meta(model)
        if not graphql_meta or not graphql_meta.filter_presets:
            return where_input
        merged = {}
        for preset_name in presets:
            preset_def = graphql_meta.filter_presets.get(preset_name)
            if preset_def:
                merged = self._deep_merge(merged, preset_def)
        if where_input:
            merged = self._deep_merge(merged, where_input)
        return merged

    def _deep_merge(self, dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries, with dict2 taking precedence."""
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            elif key == "AND" and key in result and isinstance(result[key], list) and isinstance(value, list):
                result[key] = result[key] + value
            else:
                result[key] = value
        return result

    def apply_where_filter(
        self,
        queryset: models.QuerySet,
        where_input: Dict[str, Any],
        model: Optional[Type[models.Model]] = None,
        quick_filter_fields: Optional[List[str]] = None,
    ) -> models.QuerySet:
        """Apply a where filter to a queryset. Main entry point for filter application."""
        from ...filter_inputs import FilterSecurityError, validate_filter_complexity

        if not where_input:
            return queryset

        model = model or queryset.model

        # Get quick fields from GraphQLMeta if not provided
        if quick_filter_fields is None and model:
            try:
                from ....core.meta import get_model_graphql_meta
                meta = get_model_graphql_meta(model)
                if meta and meta.quick_filter_fields:
                    quick_filter_fields = meta.quick_filter_fields
            except (ImportError, AttributeError):
                pass

        # Security validation
        max_depth = DEFAULT_MAX_FILTER_DEPTH
        max_clauses = DEFAULT_MAX_FILTER_CLAUSES
        if self.filtering_settings:
            max_depth = getattr(self.filtering_settings, "max_filter_depth", max_depth)
            max_clauses = getattr(self.filtering_settings, "max_filter_clauses", max_clauses)

        try:
            validate_filter_complexity(where_input, max_depth=max_depth, max_clauses=max_clauses)
        except FilterSecurityError as e:
            logger.warning(f"Rejected filter due to security constraints: {e}",
                          extra={"model": model.__name__ if model else "unknown"})
            return queryset.none()

        # Work on a copy
        where_input = dict(where_input)

        # Extract special filters
        include_ids = where_input.pop("include", None)
        quick_value = where_input.pop("quick", None)
        search_input = where_input.pop("search", None)
        instance_in = where_input.pop("instance_in", None)
        history_type_in = where_input.pop("history_type_in", None)
        window_filter = where_input.pop("_window", None)
        subquery_filter = where_input.pop("_subquery", None)
        exists_filter = where_input.pop("_exists", None)
        compare_filter = where_input.pop("_compare", None)

        # Extract date filters
        date_trunc_filters = {k: where_input.pop(k) for k in list(where_input.keys()) if k.endswith("_trunc")}
        date_extract_filters = {k: where_input.pop(k) for k in list(where_input.keys()) if k.endswith("_extract")}

        # Prepare queryset with annotations
        queryset = self.prepare_queryset_for_aggregation_filters(queryset, where_input)
        queryset = self.prepare_queryset_for_conditional_aggregation_filters(queryset, where_input)
        queryset = self.prepare_queryset_for_count_filters(queryset, where_input)
        queryset = self.prepare_queryset_for_computed_filters(queryset, where_input, model)

        if window_filter and self.filtering_settings and getattr(self.filtering_settings, "enable_window_filters", False):
            queryset = self.prepare_queryset_for_window_filter(queryset, window_filter)

        # Build main Q object
        q_object = self._build_q_from_where(where_input, model)

        # Apply full-text search
        if search_input and self.filtering_settings and self.filtering_settings.enable_full_text_search:
            if isinstance(search_input, str):
                search_input = {"query": search_input}
            search_q, search_annotations = self._build_fts_q(search_input, model)
            if search_annotations:
                queryset = queryset.annotate(**search_annotations)
            if search_q:
                q_object &= search_q

        # Apply quick filter
        if quick_value:
            quick_q = self._get_quick_mixin().build_quick_filter_q(model, quick_value, quick_filter_fields)
            if quick_q:
                q_object &= quick_q

        # Apply historical filters
        if instance_in:
            q_object &= self._get_historical_mixin().build_historical_filter_q("instance_in", instance_in)
        if history_type_in:
            q_object &= self._get_historical_mixin().build_historical_filter_q("history_type_in", history_type_in)

        # Apply window filter
        if window_filter and self.filtering_settings and getattr(self.filtering_settings, "enable_window_filters", False):
            window_q = self._build_window_filter_q(window_filter)
            if window_q:
                q_object &= window_q

        # Apply subquery filter
        if subquery_filter and self.filtering_settings and getattr(self.filtering_settings, "enable_subquery_filters", False):
            subquery_q, subquery_annotations = self._build_subquery_filter_q(subquery_filter, model)
            if subquery_annotations:
                queryset = queryset.annotate(**subquery_annotations)
            if subquery_q:
                q_object &= subquery_q

        # Apply exists filter
        if exists_filter and self.filtering_settings and getattr(self.filtering_settings, "enable_subquery_filters", False):
            exists_q = self._build_exists_filter_q(exists_filter, model)
            if exists_q:
                q_object &= exists_q

        # Apply field comparison filter
        if compare_filter and self.filtering_settings and getattr(self.filtering_settings, "enable_field_comparison", False):
            compare_q = self._build_field_compare_q(compare_filter)
            if compare_q:
                q_object &= compare_q

        # Apply date truncation filters
        if date_trunc_filters and self.filtering_settings and getattr(self.filtering_settings, "enable_date_trunc_filters", False):
            for field_key, trunc_filter in date_trunc_filters.items():
                base_field = field_key[:-6]
                trunc_q, trunc_annotations = self._build_date_trunc_filter_q(base_field, trunc_filter)
                if trunc_annotations:
                    queryset = queryset.annotate(**trunc_annotations)
                if trunc_q:
                    q_object &= trunc_q

        # Apply date extraction filters
        if date_extract_filters and self.filtering_settings and getattr(self.filtering_settings, "enable_extract_date_filters", False):
            for field_key, extract_filter in date_extract_filters.items():
                base_field = field_key[:-8]
                extract_q, extract_annotations = self._build_date_extract_filter_q(base_field, extract_filter)
                if extract_annotations:
                    queryset = queryset.annotate(**extract_annotations)
                if extract_q:
                    q_object &= extract_q

        if q_object:
            queryset = queryset.filter(q_object)

        # Apply include filter last
        if include_ids:
            queryset = self._get_include_mixin().apply_include_filter(queryset, include_ids)

        return queryset

    def _build_q_from_where(
        self, where_input: Dict[str, Any], model: Type[models.Model], prefix: str = ""
    ) -> Q:
        """Build a Q object from where input dictionary."""
        q = Q()
        for key, value in where_input.items():
            if value is None:
                continue
            if key == "AND" and isinstance(value, list):
                for item in value:
                    q &= self._build_q_from_where(item, model, prefix)
            elif key == "OR" and isinstance(value, list):
                or_q = Q()
                for item in value:
                    or_q |= self._build_q_from_where(item, model, prefix)
                q &= or_q
            elif key == "NOT" and isinstance(value, dict):
                q &= ~self._build_q_from_where(value, model, prefix)
            elif isinstance(value, dict):
                field_q = self._build_field_q(key, value, model, prefix)
                if field_q:
                    q &= field_q
        return q

    def _get_lookup_for_operator(self, op: str) -> Optional[str]:
        """Map filter operator to Django lookup."""
        operator_map = {
            "eq": "exact", "neq": "neq", "gt": "gt", "gte": "gte", "lt": "lt", "lte": "lte",
            "contains": "contains", "icontains": "icontains",
            "starts_with": "startswith", "istarts_with": "istartswith",
            "ends_with": "endswith", "iends_with": "iendswith",
            "in_": "in", "not_in": "not_in", "is_null": "isnull",
            "regex": "regex", "iregex": "iregex", "between": "between",
            "date": "date", "year": "year", "month": "month", "day": "day",
            "week_day": "week_day", "hour": "hour",
            "has_key": "has_key", "has_keys": "has_keys", "has_any_keys": "has_any_keys",
            "today": "today", "yesterday": "yesterday",
            "this_week": "this_week", "past_week": "past_week",
            "this_month": "this_month", "past_month": "past_month",
            "this_year": "this_year", "past_year": "past_year",
        }
        return operator_map.get(op)

    def _build_temporal_q(self, field_path: str, temporal_filter: str) -> Optional[Q]:
        """Build Q object for temporal filters (today, yesterday, this_week, etc.)."""
        today = timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()

        if temporal_filter == "today":
            return Q(**{f"{field_path}__date": today})
        elif temporal_filter == "yesterday":
            return Q(**{f"{field_path}__date": today - timedelta(days=1)})
        elif temporal_filter == "this_week":
            week_start = today - timedelta(days=today.weekday())
            return Q(**{f"{field_path}__date__range": [week_start, week_start + timedelta(days=6)]})
        elif temporal_filter == "past_week":
            this_week_start = today - timedelta(days=today.weekday())
            past_week_start = this_week_start - timedelta(days=7)
            return Q(**{f"{field_path}__date__range": [past_week_start, this_week_start - timedelta(days=1)]})
        elif temporal_filter == "this_month":
            month_start = today.replace(day=1)
            if today.month == 12:
                next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_month = today.replace(month=today.month + 1, day=1)
            return Q(**{f"{field_path}__date__range": [month_start, next_month - timedelta(days=1)]})
        elif temporal_filter == "past_month":
            this_month_start = today.replace(day=1)
            if this_month_start.month == 1:
                past_month_start = this_month_start.replace(year=this_month_start.year - 1, month=12, day=1)
            else:
                past_month_start = this_month_start.replace(month=this_month_start.month - 1, day=1)
            return Q(**{f"{field_path}__date__range": [past_month_start, this_month_start - timedelta(days=1)]})
        elif temporal_filter == "this_year":
            return Q(**{f"{field_path}__date__range": [today.replace(month=1, day=1), today.replace(month=12, day=31)]})
        elif temporal_filter == "past_year":
            return Q(**{f"{field_path}__date__range": [
                today.replace(year=today.year - 1, month=1, day=1),
                today.replace(year=today.year - 1, month=12, day=31)
            ]})
        return None

    def _get_relation_field(self, model: Type[models.Model], field_name: str) -> Optional[models.Field]:
        """Get the relation field from model by name (forward or reverse)."""
        try:
            return model._meta.get_field(field_name)
        except FieldDoesNotExist:
            pass
        try:
            for rel in model._meta.related_objects:
                if rel.get_accessor_name() == field_name:
                    return rel
        except (AttributeError, TypeError):
            pass
        return None

    def _get_fk_to_parent(
        self, related_model: Type[models.Model], parent_model: Type[models.Model]
    ) -> Optional[str]:
        """Find the FK field in related_model pointing to parent_model."""
        try:
            for field in related_model._meta.get_fields():
                if hasattr(field, "related_model") and field.related_model == parent_model:
                    return field.name
        except (AttributeError, TypeError):
            pass
        return None

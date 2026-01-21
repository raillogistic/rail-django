"""
Relation and advanced filter applicator methods for subquery, exists, date trunc/extract, and window filters.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Type

from django.db import models
from django.db.models import Exists, F, OuterRef, Q, Subquery, Window
from django.core.exceptions import FieldDoesNotExist
from django.db.models.functions import (
    DenseRank, ExtractDay, ExtractHour, ExtractIsoWeekDay, ExtractIsoYear,
    ExtractMinute, ExtractMonth, ExtractQuarter, ExtractSecond, ExtractWeek,
    ExtractWeekDay, ExtractYear, PercentRank, Rank, RowNumber,
    TruncDay, TruncHour, TruncMinute, TruncMonth, TruncQuarter, TruncWeek, TruncYear,
)
from django.utils import timezone

logger = logging.getLogger(__name__)


class RelationFilterApplicatorMixin:
    """Mixin for relation-level and advanced filter application."""

    def prepare_queryset_for_window_filter(
        self, queryset: models.QuerySet, window_filter: Dict[str, Any]
    ) -> models.QuerySet:
        """Prepare queryset with window function annotation."""
        function_name = window_filter.get("function")
        if isinstance(function_name, str):
            function_name = function_name.lower()
        else:
            function_name = getattr(function_name, "value", str(function_name)).lower()

        partition_by = window_filter.get("partition_by") or []
        order_by_fields = window_filter.get("order_by") or []

        order_by_exprs = []
        for field in order_by_fields:
            if field.startswith("-"):
                order_by_exprs.append(F(field[1:]).desc())
            else:
                order_by_exprs.append(F(field).asc())

        partition_exprs = [F(field) for field in partition_by] if partition_by else None

        window_func_map = {"rank": Rank, "dense_rank": DenseRank, "row_number": RowNumber, "percent_rank": PercentRank}
        func_class = window_func_map.get(function_name, Rank)
        window_expr = Window(expression=func_class(), partition_by=partition_exprs, order_by=order_by_exprs)
        return queryset.annotate(_window_rank=window_expr)

    def _build_window_filter_q(self, window_filter: Dict[str, Any]) -> Q:
        """Build Q object for window function filter."""
        q = Q()
        if window_filter.get("rank"):
            q &= self._build_numeric_q("_window_rank", window_filter["rank"])
        if window_filter.get("percentile"):
            q &= self._build_numeric_q("_window_rank", window_filter["percentile"])
        return q

    def _build_subquery_filter_q(
        self, subquery_filter: Dict[str, Any], model: Type[models.Model]
    ) -> tuple[Q, Dict[str, Any]]:
        """Build Q object and annotations for subquery filter."""
        import json
        annotations, q = {}, Q()
        relation_name = subquery_filter.get("relation")
        if not relation_name:
            return q, annotations

        order_by_fields = subquery_filter.get("order_by") or ["-pk"]
        target_field = subquery_filter.get("field") or "id"
        filter_json = subquery_filter.get("filter")

        try:
            relation_field = self._get_relation_field(model, relation_name)
            if relation_field is None:
                return q, annotations
            related_model = getattr(relation_field, "related_model", None)
            if related_model is None:
                return q, annotations
            fk_field = self._get_fk_to_parent(related_model, model)
            if not fk_field:
                return q, annotations

            subquery_qs = related_model.objects.filter(**{fk_field: OuterRef("pk")})

            if filter_json:
                try:
                    filter_dict = json.loads(filter_json) if isinstance(filter_json, str) else filter_json
                    for k, v in filter_dict.items():
                        if isinstance(v, dict):
                            for op, op_val in v.items():
                                lookup = self._get_lookup_for_operator(op)
                                if lookup == "neq":
                                    subquery_qs = subquery_qs.exclude(**{f"{k}__exact": op_val})
                                elif lookup:
                                    subquery_qs = subquery_qs.filter(**{f"{k}__{lookup}": op_val})
                        else:
                            subquery_qs = subquery_qs.filter(**{k: v})
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.debug(f"Failed to parse subquery filter: {e}")

            order_exprs = [f"-{f[1:]}" if f.startswith("-") else f for f in order_by_fields]
            subquery_qs = subquery_qs.order_by(*order_exprs)
            annotation_name = f"_subquery_{relation_name}_{target_field}"
            annotations[annotation_name] = Subquery(subquery_qs.values(target_field)[:1])

            for op in ("eq", "neq", "gt", "gte", "lt", "lte", "is_null"):
                op_value = subquery_filter.get(op)
                if op_value is None:
                    continue
                if op == "eq":
                    q &= Q(**{annotation_name: op_value})
                elif op == "neq":
                    q &= ~Q(**{annotation_name: op_value})
                elif op == "is_null":
                    q &= Q(**{f"{annotation_name}__isnull": op_value})
                else:
                    q &= Q(**{f"{annotation_name}__{op}": op_value})
        except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Failed to build subquery filter: {e}")
        return q, annotations

    def _build_exists_filter_q(self, exists_filter: Dict[str, Any], model: Type[models.Model]) -> Q:
        """Build Q object for exists filter."""
        import json
        q = Q()
        relation_name = exists_filter.get("relation")
        if not relation_name:
            return q

        should_exist = exists_filter.get("exists", True)
        filter_json = exists_filter.get("filter")

        try:
            relation_field = self._get_relation_field(model, relation_name)
            if relation_field is None:
                return q
            related_model = getattr(relation_field, "related_model", None)
            if related_model is None:
                return q
            fk_field = self._get_fk_to_parent(related_model, model)
            if not fk_field:
                return q

            subquery_qs = related_model.objects.filter(**{fk_field: OuterRef("pk")})

            if filter_json:
                try:
                    filter_dict = json.loads(filter_json) if isinstance(filter_json, str) else filter_json
                    for k, v in filter_dict.items():
                        if isinstance(v, dict):
                            for op, op_val in v.items():
                                lookup = self._get_lookup_for_operator(op)
                                if lookup == "neq":
                                    subquery_qs = subquery_qs.exclude(**{f"{k}__exact": op_val})
                                elif lookup:
                                    subquery_qs = subquery_qs.filter(**{f"{k}__{lookup}": op_val})
                        else:
                            subquery_qs = subquery_qs.filter(**{k: v})
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.debug(f"Failed to parse exists filter: {e}")

            exists_expr = Exists(subquery_qs)
            if should_exist:
                q &= Q(exists_expr)
            else:
                q &= ~Q(exists_expr)
        except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Failed to build exists filter: {e}")
        return q

    def _build_date_trunc_filter_q(
        self, base_field: str, trunc_filter: Dict[str, Any]
    ) -> tuple[Q, Dict[str, Any]]:
        """Build Q object and annotations for date truncation filters."""
        q, annotations = Q(), {}
        precision = trunc_filter.get("precision")
        if not precision:
            return q, annotations
        if hasattr(precision, "value"):
            precision = precision.value

        trunc_functions = {
            "year": TruncYear, "quarter": TruncQuarter, "month": TruncMonth,
            "week": TruncWeek, "day": TruncDay, "hour": TruncHour, "minute": TruncMinute,
        }
        trunc_func = trunc_functions.get(precision)
        if not trunc_func:
            return q, annotations

        annotation_name = f"_{base_field}_trunc_{precision}"
        annotations[annotation_name] = trunc_func(base_field)

        if trunc_filter.get("value"):
            try:
                from dateutil.parser import parse as parse_date
                q &= Q(**{annotation_name: parse_date(trunc_filter["value"])})
            except (ValueError, ImportError):
                try:
                    value_str = trunc_filter["value"]
                    if precision == "year":
                        q &= Q(**{f"{annotation_name}__year": int(value_str[:4])})
                    elif precision == "month":
                        parts = value_str.split("-")
                        if len(parts) >= 2:
                            q &= Q(**{f"{annotation_name}__year": int(parts[0])})
                            q &= Q(**{f"{annotation_name}__month": int(parts[1])})
                except (ValueError, IndexError):
                    pass

        if trunc_filter.get("year") is not None:
            q &= Q(**{f"{annotation_name}__year": trunc_filter["year"]})
        if trunc_filter.get("quarter") is not None:
            quarter = trunc_filter["quarter"]
            if 1 <= quarter <= 4:
                start_month, end_month = (quarter - 1) * 3 + 1, quarter * 3
                q &= Q(**{f"{annotation_name}__month__gte": start_month})
                q &= Q(**{f"{annotation_name}__month__lte": end_month})
        if trunc_filter.get("month") is not None:
            q &= Q(**{f"{annotation_name}__month": trunc_filter["month"]})
        if trunc_filter.get("week") is not None:
            q &= Q(**{f"{annotation_name}__week": trunc_filter["week"]})

        today = timezone.now().date() if timezone.is_aware(timezone.now()) else date.today()
        now = timezone.now() if timezone.is_aware(timezone.now()) else datetime.now()

        if trunc_filter.get("this_period"):
            if precision == "year":
                q &= Q(**{f"{annotation_name}__year": today.year})
            elif precision == "quarter":
                cq = (today.month - 1) // 3 + 1
                q &= Q(**{f"{annotation_name}__year": today.year})
                q &= Q(**{f"{annotation_name}__month__gte": (cq - 1) * 3 + 1})
                q &= Q(**{f"{annotation_name}__month__lte": cq * 3})
            elif precision == "month":
                q &= Q(**{f"{annotation_name}__year": today.year})
                q &= Q(**{f"{annotation_name}__month": today.month})
            elif precision == "week":
                q &= Q(**{f"{annotation_name}__year": today.year})
                q &= Q(**{f"{annotation_name}__week": today.isocalendar()[1]})
            elif precision in ("day", "hour"):
                q &= Q(**{annotation_name: trunc_func(now)})

        if trunc_filter.get("last_period"):
            if precision == "year":
                q &= Q(**{f"{annotation_name}__year": today.year - 1})
            elif precision == "quarter":
                cq = (today.month - 1) // 3 + 1
                lq, yr = (4, today.year - 1) if cq == 1 else (cq - 1, today.year)
                q &= Q(**{f"{annotation_name}__year": yr})
                q &= Q(**{f"{annotation_name}__month__gte": (lq - 1) * 3 + 1})
                q &= Q(**{f"{annotation_name}__month__lte": lq * 3})
            elif precision == "month":
                if today.month == 1:
                    q &= Q(**{f"{annotation_name}__year": today.year - 1})
                    q &= Q(**{f"{annotation_name}__month": 12})
                else:
                    q &= Q(**{f"{annotation_name}__year": today.year})
                    q &= Q(**{f"{annotation_name}__month": today.month - 1})
            elif precision == "week":
                lw = today.isocalendar()[1] - 1
                if lw == 0:
                    q &= Q(**{f"{annotation_name}__year": today.year - 1})
                    q &= Q(**{f"{annotation_name}__week": 52})
                else:
                    q &= Q(**{f"{annotation_name}__year": today.year})
                    q &= Q(**{f"{annotation_name}__week": lw})
            elif precision == "day":
                q &= Q(**{f"{base_field}__date": today - timedelta(days=1)})
        return q, annotations

    def _build_date_extract_filter_q(
        self, base_field: str, extract_filter: Dict[str, Any]
    ) -> tuple[Q, Dict[str, Any]]:
        """Build Q object and annotations for date extraction filters."""
        q, annotations = Q(), {}
        extract_functions = {
            "year": ExtractYear, "month": ExtractMonth, "day": ExtractDay,
            "quarter": ExtractQuarter, "week": ExtractWeek, "day_of_week": ExtractWeekDay,
            "iso_week_day": ExtractIsoWeekDay, "iso_year": ExtractIsoYear,
            "hour": ExtractHour, "minute": ExtractMinute, "second": ExtractSecond,
        }

        for extract_key, filter_value in extract_filter.items():
            if filter_value is None:
                continue
            extract_func = extract_functions.get(extract_key)
            if not extract_func:
                continue
            annotation_name = f"_{base_field}_extract_{extract_key}"

            if extract_key == "day_of_year":
                from django.db.models import Func, IntegerField as DjIntegerField
                class ExtractDayOfYear(Func):
                    function = "EXTRACT"
                    template = "%(function)s(DOY FROM %(expressions)s)"
                    output_field = DjIntegerField()
                annotations[annotation_name] = ExtractDayOfYear(base_field)
            else:
                annotations[annotation_name] = extract_func(base_field)

            extract_q = self._build_numeric_q(annotation_name, filter_value)
            if extract_q:
                q &= extract_q
        return q, annotations

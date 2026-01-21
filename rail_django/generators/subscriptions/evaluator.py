"""
Filter evaluation logic for subscriptions.
"""

import copy
import logging
import re
from datetime import timedelta
from typing import Any, Iterable, Optional

from django.db import models
from django.utils import timezone

from .utils import _coerce_date

logger = logging.getLogger(__name__)

_DATE_SUFFIXES = ("today", "yesterday", "this_week", "past_week", "this_month", "past_month", "this_year", "past_year")


def _coerce_model_value(value: Any) -> Any:
    if isinstance(value, models.Model): return value.pk
    return value


def _coerce_expected(value: Any) -> Any:
    if isinstance(value, models.Model): return value.pk
    if isinstance(value, (list, tuple, set)):
        coerced = [item.pk if isinstance(item, models.Model) else item for item in value]
        return tuple(coerced) if isinstance(value, tuple) else coerced
    return value


def _coerce_iterable(value: Any) -> Iterable:
    if value is None: return []
    if hasattr(value, "all") and callable(value.all):
        try: return list(value.all())
        except Exception: return []
    if isinstance(value, (list, tuple, set)): return list(value)
    return [value]


def _resolve_values(obj: Any, path_parts: Iterable[str]) -> list:
    values = [obj]
    for part in path_parts:
        next_values = []
        for value in values:
            if value is None: continue
            for item in _coerce_iterable(value):
                try: attr = getattr(item, part)
                except Exception: attr = None
                if hasattr(attr, "all") and callable(attr.all):
                    try: next_values.extend(list(attr.all()))
                    except Exception: continue
                else: next_values.append(attr)
        values = next_values
    return values


def _compare_value(value: Any, lookup: str, expected: Any) -> bool:
    value = _coerce_model_value(value)
    expected = _coerce_expected(expected)
    if lookup == "exact": return value == expected
    if lookup == "iexact":
        if value is None or expected is None: return False
        return str(value).lower() == str(expected).lower()
    if lookup in {"contains", "icontains"}:
        if value is None or expected is None: return False
        haystack, needle = str(value), str(expected)
        if lookup == "icontains": haystack, needle = haystack.lower(), needle.lower()
        return needle in haystack
    if lookup in {"startswith", "istartswith"}:
        if value is None or expected is None: return False
        haystack, needle = str(value), str(expected)
        if lookup == "istartswith": haystack, needle = haystack.lower(), needle.lower()
        return haystack.startswith(needle)
    if lookup in {"endswith", "iendswith"}:
        if value is None or expected is None: return False
        haystack, needle = str(value), str(expected)
        if lookup == "iendswith": haystack, needle = haystack.lower(), needle.lower()
        return haystack.endswith(needle)
    if lookup == "in":
        if expected is None: return False
        try: return value in expected
        except Exception: return False
    if lookup == "isnull": return bool(expected) == (value is None)
    if lookup in {"gt", "gte", "lt", "lte"}:
        if value is None or expected is None: return False
        if lookup == "gt": return value > expected
        if lookup == "gte": return value >= expected
        if lookup == "lt": return value < expected
        return value <= expected
    if lookup == "range":
        if value is None or expected is None: return False
        try: lower, upper = expected
        except Exception: return False
        return lower <= value <= upper
    if lookup == "year": return getattr(value, "year", None) == expected
    if lookup == "month": return getattr(value, "month", None) == expected
    if lookup == "day": return getattr(value, "day", None) == expected
    if lookup in {"regex", "iregex"}:
        if value is None or expected is None: return False
        flags = re.IGNORECASE if lookup == "iregex" else 0
        try: return re.search(str(expected), str(value), flags) is not None
        except Exception: return False
    if lookup in {"has_key", "has_keys", "has_any_keys"}:
        if not isinstance(value, dict): return False
        if lookup == "has_key": return expected in value
        if lookup == "has_keys": return all(key in value for key in (expected or []))
        return any(key in value for key in (expected or []))
    if lookup == "week_day":
        date_value = _coerce_date(value)
        if date_value is None or expected is None: return False
        try: expected_day = int(expected)
        except (TypeError, ValueError): return False
        return ((date_value.isoweekday() % 7) + 1) == expected_day
    if lookup in {"today", "yesterday", "this_week", "past_week", "this_month", "past_month", "this_year", "past_year"}:
        if not expected: return True
        date_value = _coerce_date(value)
        if date_value is None: return False
        today = timezone.localdate()
        if lookup == "today": return date_value == today
        if lookup == "yesterday": return date_value == (today - timedelta(days=1))
        if lookup in {"this_week", "past_week"}:
            this_week_start = today - timedelta(days=today.weekday())
            if lookup == "this_week": return this_week_start <= date_value <= (this_week_start + timedelta(days=6))
            return (this_week_start - timedelta(days=7)) <= date_value <= (this_week_start - timedelta(days=1))
        if lookup in {"this_month", "past_month"}:
            this_month_start = today.replace(day=1)
            if lookup == "this_month":
                if today.month == 12: next_start = today.replace(year=today.year + 1, month=1, day=1)
                else: next_start = today.replace(month=today.month + 1, day=1)
                return this_month_start <= date_value <= (next_start - timedelta(days=1))
            if this_month_start.month == 1: past_start = this_month_start.replace(year=this_month_start.year - 1, month=12, day=1)
            else: past_start = this_month_start.replace(month=this_month_start.month - 1, day=1)
            return past_start <= date_value <= (this_month_start - timedelta(days=1))
        if lookup in {"this_year", "past_year"}:
            this_year_start = today.replace(month=1, day=1)
            if lookup == "this_year": return this_year_start <= date_value <= today.replace(month=12, day=31)
            past_start = this_year_start.replace(year=this_year_start.year - 1)
            return past_start <= date_value <= (this_year_start - timedelta(days=1))
    return False


def _evaluate_filter_dict(instance: Any, filter_dict: dict[str, Any]) -> bool:
    if not filter_dict: return True
    if "AND" in filter_dict:
        if not all(_evaluate_filter_dict(instance, item) for item in (filter_dict.get("AND") or [])): return False
    if "OR" in filter_dict:
        or_items = filter_dict.get("OR") or []
        if or_items and not any(_evaluate_filter_dict(instance, item) for item in or_items): return False
    if "NOT" in filter_dict:
        if _evaluate_filter_dict(instance, filter_dict.get("NOT") or {}): return False

    for key, expected in filter_dict.items():
        if key in {"AND", "OR", "NOT"}: continue
        suffix_match = None
        for suffix in _DATE_SUFFIXES:
            suffix_token = f"_{suffix}"
            if key.endswith(suffix_token):
                suffix_match = suffix
                field_path = key[: -len(suffix_token)]
                if not expected: break
                values = _resolve_values(instance, field_path.split("__")) if field_path else []
                if not any(_compare_value(value, suffix, True) for value in values): return False
                break
        if suffix_match is not None: continue
        parts = key.split("__")
        lookup = "exact"
        lookups = {"exact", "iexact", "contains", "icontains", "startswith", "istartswith", "endswith", "iendswith", "in", "gt", "gte", "lt", "lte", "range", "isnull", "year", "month", "day", "regex", "iregex", "has_key", "has_keys", "has_any_keys", "week_day", "today", "yesterday", "this_week", "past_week", "this_month", "past_month", "this_year", "past_year"}
        if parts[-1] in lookups: lookup = parts.pop()
        field_path = "__".join(parts)
        if field_path.endswith("_count"):
            base_field = field_path[: -len("_count")]
            count_val = len(_resolve_values(instance, base_field.split("__")) if base_field else [])
            if not _compare_value(count_val, lookup, expected): return False
            continue
        values = _resolve_values(instance, parts)
        if lookup == "isnull" and not values: values = [None]
        if not any(_compare_value(value, lookup, expected) for value in values): return False
    return True


def _matches_filters(instance: models.Model, model: type[models.Model], filters: Optional[dict[str, Any]], nested_filter_applicator: Any, *, use_db: bool) -> bool:
    if not filters: return True
    if use_db and getattr(instance, "pk", None) is not None:
        try:
            queryset = model._default_manager.filter(pk=instance.pk)
            if filters: queryset = nested_filter_applicator.apply_where_filter(queryset, copy.deepcopy(filters), model)
            return queryset.exists()
        except Exception as exc: logger.warning("Subscription filter evaluation failed for %s: %s", model.__name__, exc)
    try: return _evaluate_filter_dict(instance, copy.deepcopy(filters) or {})
    except Exception as exc: logger.warning("Fallback subscription filter evaluation failed for %s: %s", model.__name__, exc)
    return False

"""
Field-level filter applicator methods for regular fields, count, computed, array, and FTS filters.
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Type

from django.db import models
from django.db.models import Count, Exists, F, OuterRef, Q
from django.core.exceptions import FieldDoesNotExist

logger = logging.getLogger(__name__)
DEFAULT_MAX_REGEX_LENGTH = 500


class FieldFilterApplicatorMixin:
    """Mixin for field-level filter application."""

    def _build_field_q(
        self,
        field_name: str,
        filter_value: Dict[str, Any],
        model: Type[models.Model],
        prefix: str = "",
        property_context: Optional[Dict[str, Any]] = None,
    ) -> Q:
        """Build a Q object for a field filter."""
        from ..security import FilterSecurityError, validate_regex_pattern

        q = Q()
        full_field_path = f"{prefix}{field_name}" if prefix else field_name

        # Handle relation suffixes
        if field_name.endswith("_rel"):
            relation_name = field_name[:-4]
            relation_field = self._get_relation_field(model, relation_name)
            related_model = getattr(relation_field, "related_model", None)
            return self._build_q_from_where(
                filter_value,
                related_model or model,
                f"{prefix}{relation_name}__",
                property_context=property_context,
            )

        if field_name.endswith("_some"):
            relation_name = field_name[:-5]
            relation_field = self._get_relation_field(model, relation_name)
            related_model = getattr(relation_field, "related_model", None)
            return self._build_q_from_where(
                filter_value,
                related_model or model,
                f"{prefix}{relation_name}__",
                property_context=property_context,
            )

        if field_name.endswith("_every"):
            base_field = field_name[:-6]
            try:
                relation_field = self._get_relation_field(model, base_field)
                if relation_field is not None:
                    related_model = getattr(relation_field, "related_model", None)
                    if related_model is not None:
                        matching_q = self._build_q_from_where(
                            filter_value,
                            related_model,
                            "",
                            property_context=property_context,
                        )
                        fk_field = self._get_fk_to_parent(related_model, model)
                        if fk_field:
                            non_matching = related_model.objects.filter(
                                **{fk_field: OuterRef("pk")}
                            ).exclude(matching_q)
                            has_children = related_model.objects.filter(**{fk_field: OuterRef("pk")})
                            return Q(Exists(has_children)) & ~Q(Exists(non_matching))
            except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
                logger.debug(f"Could not build optimized _every filter for {base_field}: {e}")
            relation_field = self._get_relation_field(model, base_field)
            related_model = getattr(relation_field, "related_model", None)
            return self._build_q_from_where(
                filter_value,
                related_model or model,
                f"{prefix}{base_field}__",
                property_context=property_context,
            )

        if field_name.endswith("_none"):
            relation_name = field_name[:-5]
            relation_field = self._get_relation_field(model, relation_name)
            related_model = getattr(relation_field, "related_model", None)
            return ~self._build_q_from_where(
                filter_value,
                related_model or model,
                f"{prefix}{relation_name}__",
                property_context=property_context,
            )

        if field_name.endswith("_cond_agg"):
            return self._build_conditional_aggregation_q(full_field_path[:-9], filter_value)

        if field_name.endswith("_agg"):
            return self._build_aggregation_q(full_field_path[:-4], filter_value)

        # Check ArrayField
        try:
            field_obj = model._meta.get_field(field_name)
            try:
                from django.contrib.postgres.fields import ArrayField
                if isinstance(field_obj, ArrayField):
                    return self._build_array_field_q(full_field_path, filter_value)
            except ImportError:
                pass
        except FieldDoesNotExist:
            pass

        # Count filter
        if field_name.endswith("_count"):
            is_real_field = False
            try:
                model._meta.get_field(field_name)
                is_real_field = True
            except FieldDoesNotExist:
                pass
            if not is_real_field:
                return self._build_count_q(field_name[:-6], filter_value)

        if (
            prefix == ""
            and self._is_property_field(model, field_name)
            and property_context is not None
        ):
            return self._build_property_q(
                field_name,
                filter_value,
                property_context=property_context,
            )

        if not self._is_filter_field_allowed(model, field_name):
            return q

        # Regular field filter
        for op, op_value in filter_value.items():
            if op_value is None:
                continue
            lookup = self._get_lookup_for_operator(op)
            if not lookup:
                continue

            # Validate regex patterns
            if lookup in ("regex", "iregex"):
                max_regex_len = DEFAULT_MAX_REGEX_LENGTH
                reject_unsafe = True
                if self.filtering_settings:
                    max_regex_len = getattr(self.filtering_settings, "max_regex_length", max_regex_len)
                    reject_unsafe = getattr(self.filtering_settings, "reject_unsafe_regex", True)
                try:
                    op_value = validate_regex_pattern(op_value, max_length=max_regex_len, check_redos=reject_unsafe)
                except FilterSecurityError as e:
                    logger.warning(f"Rejected unsafe regex filter: {e}")
                    continue

            if lookup == "between" and isinstance(op_value, list) and len(op_value) == 2:
                q &= Q(**{f"{full_field_path}__gte": op_value[0]})
                q &= Q(**{f"{full_field_path}__lte": op_value[1]})
            elif lookup in ("today", "yesterday", "this_week", "past_week", "this_month", "past_month", "this_year", "past_year"):
                if op_value:
                    date_q = self._build_temporal_q(full_field_path, lookup)
                    if date_q:
                        q &= date_q
            elif lookup == "in":
                q &= Q(**{f"{full_field_path}__in": op_value})
            elif lookup == "not_in":
                q &= ~Q(**{f"{full_field_path}__in": op_value})
            elif lookup == "neq":
                q &= ~Q(**{f"{full_field_path}__exact": op_value})
            else:
                q &= Q(**{f"{full_field_path}__{lookup}": op_value})
        return q

    def _is_property_field(self, model: Type[models.Model], field_name: str) -> bool:
        try:
            model._meta.get_field(field_name)
            return False
        except FieldDoesNotExist:
            descriptor = getattr(model, field_name, None)
            return isinstance(descriptor, property)

    def _build_property_q(
        self,
        field_name: str,
        filter_value: Dict[str, Any],
        *,
        property_context: Dict[str, Any],
    ) -> Q:
        base_queryset = property_context.get("queryset")
        if base_queryset is None:
            return Q()

        cache = property_context.setdefault("cache", {})
        cache_key = (
            field_name,
            self._freeze_filter_value(filter_value),
        )
        if cache_key not in cache:
            matching_ids: list[Any] = []
            for instance in base_queryset:
                try:
                    value = getattr(instance, field_name)
                except Exception:
                    continue
                if self._property_value_matches(value, filter_value):
                    matching_ids.append(getattr(instance, "pk", None))
            cache[cache_key] = [pk for pk in matching_ids if pk is not None]

        return Q(pk__in=cache[cache_key])

    def _freeze_filter_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(
                (str(k), self._freeze_filter_value(v))
                for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            )
        if isinstance(value, (list, tuple)):
            return tuple(self._freeze_filter_value(item) for item in value)
        if isinstance(value, set):
            return tuple(
                sorted(
                    (self._freeze_filter_value(item) for item in value),
                    key=lambda item: str(item),
                )
            )
        return value

    def _normalize_operator_name(self, operator: str) -> str:
        raw = str(operator or "").strip()
        if not raw:
            return raw
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", raw).lower()
        return snake

    def _property_value_matches(
        self,
        value: Any,
        filter_value: Dict[str, Any],
    ) -> bool:
        from ..security import FilterSecurityError, validate_regex_pattern

        for operator, raw_operand in filter_value.items():
            if raw_operand is None:
                continue

            normalized_operator = self._normalize_operator_name(operator)
            lookup = self._get_lookup_for_operator(normalized_operator)
            if not lookup:
                lookup = self._get_lookup_for_operator(str(operator))
            if not lookup:
                continue

            operand = raw_operand
            if lookup in ("regex", "iregex"):
                max_regex_len = DEFAULT_MAX_REGEX_LENGTH
                reject_unsafe = True
                if self.filtering_settings:
                    max_regex_len = getattr(
                        self.filtering_settings,
                        "max_regex_length",
                        max_regex_len,
                    )
                    reject_unsafe = getattr(
                        self.filtering_settings,
                        "reject_unsafe_regex",
                        True,
                    )
                try:
                    operand = validate_regex_pattern(
                        operand,
                        max_length=max_regex_len,
                        check_redos=reject_unsafe,
                    )
                except FilterSecurityError:
                    return False

            if not self._evaluate_property_lookup(value, lookup, operand):
                return False

        return True

    def _evaluate_property_lookup(
        self,
        value: Any,
        lookup: str,
        operand: Any,
    ) -> bool:
        if lookup == "exact":
            return value == operand
        if lookup == "neq":
            return value != operand
        if lookup == "gt":
            try:
                return value > operand
            except Exception:
                return False
        if lookup == "gte":
            try:
                return value >= operand
            except Exception:
                return False
        if lookup == "lt":
            try:
                return value < operand
            except Exception:
                return False
        if lookup == "lte":
            try:
                return value <= operand
            except Exception:
                return False
        if lookup == "contains":
            if value is None:
                return False
            if isinstance(value, (list, tuple, set)):
                return operand in value
            return str(operand) in str(value)
        if lookup == "icontains":
            if value is None:
                return False
            return str(operand).lower() in str(value).lower()
        if lookup == "startswith":
            if value is None:
                return False
            return str(value).startswith(str(operand))
        if lookup == "istartswith":
            if value is None:
                return False
            return str(value).lower().startswith(str(operand).lower())
        if lookup == "endswith":
            if value is None:
                return False
            return str(value).endswith(str(operand))
        if lookup == "iendswith":
            if value is None:
                return False
            return str(value).lower().endswith(str(operand).lower())
        if lookup == "in":
            if not isinstance(operand, (list, tuple, set)):
                return False
            return value in operand
        if lookup == "not_in":
            if not isinstance(operand, (list, tuple, set)):
                return False
            return value not in operand
        if lookup == "isnull":
            return (value is None) == bool(operand)
        if lookup == "regex":
            if value is None:
                return False
            try:
                return re.search(str(operand), str(value)) is not None
            except re.error:
                return False
        if lookup == "iregex":
            if value is None:
                return False
            try:
                return re.search(str(operand), str(value), flags=re.IGNORECASE) is not None
            except re.error:
                return False
        if lookup == "between":
            if not isinstance(operand, (list, tuple)) or len(operand) != 2:
                return False
            lower, upper = operand
            try:
                return value >= lower and value <= upper
            except Exception:
                return False
        if lookup == "year":
            if value is None or not hasattr(value, "year"):
                return False
            try:
                return int(value.year) == int(operand)
            except Exception:
                return False
        if lookup == "month":
            if value is None or not hasattr(value, "month"):
                return False
            try:
                return int(value.month) == int(operand)
            except Exception:
                return False
        if lookup == "day":
            if value is None or not hasattr(value, "day"):
                return False
            try:
                return int(value.day) == int(operand)
            except Exception:
                return False
        if lookup == "week_day":
            if value is None or not hasattr(value, "isoweekday"):
                return False
            try:
                django_week_day = (int(value.isoweekday()) % 7) + 1
                return django_week_day == int(operand)
            except Exception:
                return False
        if lookup == "hour":
            if value is None or not hasattr(value, "hour"):
                return False
            try:
                return int(value.hour) == int(operand)
            except Exception:
                return False
        if lookup == "date":
            if value is None:
                return False
            if isinstance(value, datetime):
                candidate = value.date()
            elif isinstance(value, date):
                candidate = value
            else:
                return False
            if isinstance(operand, datetime):
                expected = operand.date()
            elif isinstance(operand, date):
                expected = operand
            else:
                return False
            return candidate == expected
        if lookup == "today":
            if not operand:
                return True
            today = date.today()
            if isinstance(value, datetime):
                return value.date() == today
            if isinstance(value, date):
                return value == today
            return False
        if lookup == "yesterday":
            if not operand:
                return True
            yesterday = date.today() - timedelta(days=1)
            if isinstance(value, datetime):
                return value.date() == yesterday
            if isinstance(value, date):
                return value == yesterday
            return False
        return False

    def _build_numeric_q(self, field_path: str, filter_value: Dict[str, Any]) -> Q:
        """Build Q object for numeric-like filters."""
        q = Q()
        for op, op_value in filter_value.items():
            if op_value is None:
                continue
            lookup = self._get_lookup_for_operator(op)
            if not lookup:
                continue
            if lookup == "between" and isinstance(op_value, list) and len(op_value) == 2:
                q &= Q(**{f"{field_path}__gte": op_value[0]})
                q &= Q(**{f"{field_path}__lte": op_value[1]})
            elif lookup == "in":
                q &= Q(**{f"{field_path}__in": op_value})
            elif lookup == "not_in":
                q &= ~Q(**{f"{field_path}__in": op_value})
            elif lookup == "neq":
                q &= ~Q(**{f"{field_path}__exact": op_value})
            else:
                q &= Q(**{f"{field_path}__{lookup}": op_value})
        return q

    def _build_count_q(self, field_name: str, filter_value: Dict[str, Any]) -> Q:
        """Build Q object for count filter."""
        q = Q()
        annotation_name = f"{field_name}_count_annotation"
        for op, op_value in filter_value.items():
            if op_value is None:
                continue
            if op == "eq":
                q &= Q(**{annotation_name: op_value})
            elif op == "neq":
                q &= ~Q(**{annotation_name: op_value})
            elif op == "gt":
                q &= Q(**{f"{annotation_name}__gt": op_value})
            elif op == "gte":
                q &= Q(**{f"{annotation_name}__gte": op_value})
            elif op == "lt":
                q &= Q(**{f"{annotation_name}__lt": op_value})
            elif op == "lte":
                q &= Q(**{f"{annotation_name}__lte": op_value})
        return q

    def prepare_queryset_for_count_filters(
        self, queryset: models.QuerySet, where_input: Dict[str, Any]
    ) -> models.QuerySet:
        """Prepare queryset with annotations for count filters."""
        annotations = self._collect_count_annotations(where_input, model=queryset.model)
        for annotation_name, field_name in annotations.items():
            queryset = queryset.annotate(**{annotation_name: Count(field_name)})
        return queryset

    def _collect_count_annotations(
        self, where_input: Dict[str, Any],
        annotations: Optional[Dict[str, str]] = None,
        model: Optional[Type[models.Model]] = None
    ) -> Dict[str, str]:
        """Collect all count annotations needed."""
        if annotations is None:
            annotations = {}
        for key, value in where_input.items():
            if key in ("AND", "OR") and isinstance(value, list):
                for item in value:
                    self._collect_count_annotations(item, annotations, model)
            elif key == "NOT" and isinstance(value, dict):
                self._collect_count_annotations(value, annotations, model)
            elif key.endswith("_count") and isinstance(value, dict):
                is_real_field = False
                if model:
                    try:
                        model._meta.get_field(key)
                        is_real_field = True
                    except FieldDoesNotExist:
                        pass
                if not is_real_field:
                    base_field = key[:-6]
                    annotations[f"{base_field}_count_annotation"] = base_field
        return annotations

    def prepare_queryset_for_computed_filters(
        self, queryset: models.QuerySet, where_input: Dict[str, Any], model: Type[models.Model]
    ) -> models.QuerySet:
        """Prepare queryset with annotations for computed fields."""
        try:
            from ....core.meta import get_model_graphql_meta
            graphql_meta = get_model_graphql_meta(model)
            computed_defs = getattr(graphql_meta, "computed_filters", {})
        except Exception:
            return queryset
        if not computed_defs:
            return queryset

        def collect_keys(d, keys):
            for k, v in d.items():
                keys.add(k)
                if isinstance(v, dict):
                    collect_keys(v, keys)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            collect_keys(item, keys)

        used_keys = set()
        collect_keys(where_input, used_keys)
        annotations = {}
        for field_name, definition in computed_defs.items():
            if field_name in used_keys:
                expression = definition.get("expression")
                if expression:
                    annotations[field_name] = expression
        if annotations:
            queryset = queryset.annotate(**annotations)
        return queryset

    def _build_array_field_q(self, field_name: str, array_filter: Dict[str, Any]) -> Q:
        """Build Q object for PostgreSQL ArrayField filters."""
        q = Q()
        if array_filter.get("contains"):
            q &= Q(**{f"{field_name}__contains": array_filter["contains"]})
        if array_filter.get("contained_by"):
            q &= Q(**{f"{field_name}__contained_by": array_filter["contained_by"]})
        if array_filter.get("overlaps"):
            q &= Q(**{f"{field_name}__overlap": array_filter["overlaps"]})
        if array_filter.get("is_null") is not None:
            q &= Q(**{f"{field_name}__isnull": array_filter["is_null"]})
        return q

    def _build_fts_q(
        self, search_input: Dict[str, Any], model: Type[models.Model]
    ) -> tuple[Q, Dict[str, Any]]:
        """Build full-text search Q object and annotations."""
        from django.db import connection

        query_text = search_input.get("query") if isinstance(search_input, dict) else None
        if not query_text:
            return Q(), {}

        fields = search_input.get("fields") if isinstance(search_input, dict) else None
        if isinstance(fields, str):
            fields = [fields]
        if not fields:
            fields = self._get_quick_mixin().get_default_quick_filter_fields(model)
        fields = [
            field_path
            for field_path in fields
            if isinstance(field_path, str)
            and field_path
            and self._resolve_filter_path(model, field_path)
        ]
        if not fields:
            return Q(), {}

        config = search_input.get("config") or (
            self.filtering_settings.fts_config if self.filtering_settings else "english"
        )
        search_type = search_input.get("search_type") or (
            self.filtering_settings.fts_search_type if self.filtering_settings else "websearch"
        )
        if search_type is not None and not isinstance(search_type, str):
            search_type = getattr(search_type, "value", str(search_type))
        rank_threshold = search_input.get("rank_threshold")
        if rank_threshold is None and self.filtering_settings:
            rank_threshold = self.filtering_settings.fts_rank_threshold

        if connection.vendor == "postgresql":
            try:
                from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
                vector = SearchVector(*fields, config=config)
                query = SearchQuery(query_text, config=config, search_type=search_type)
                annotations = {"_search_vector": vector, "_search_rank": SearchRank(vector, query)}
                q = Q(_search_vector=query)
                if rank_threshold is not None:
                    q &= Q(_search_rank__gte=rank_threshold)
                return q, annotations
            except (ImportError, TypeError, ValueError) as e:
                logger.debug(f"Full-text search setup failed, falling back: {e}")

        fallback_q = Q()
        for field_path in fields:
            field = self._get_quick_mixin()._get_field_from_path(model, field_path)
            if field and isinstance(field, (models.CharField, models.TextField, models.EmailField)):
                fallback_q |= Q(**{f"{field_path}__icontains": query_text})
        return fallback_q, {}

    def _build_field_compare_q(
        self,
        compare_filter: Dict[str, Any],
        model: Type[models.Model],
    ) -> Q:
        """Build Q object for F() expression field comparisons."""
        q = Q()
        left_field = compare_filter.get("left")
        operator = compare_filter.get("operator")
        right_field = compare_filter.get("right")
        if not left_field or not operator or not right_field:
            return q

        if hasattr(operator, "value"):
            operator = operator.value

        if not self._resolve_filter_path(model, left_field):
            return q
        if not self._resolve_filter_path(model, right_field):
            return q

        right_expr = F(right_field)
        multiplier = compare_filter.get("right_multiplier")
        if multiplier is not None:
            right_expr = right_expr * multiplier
        offset = compare_filter.get("right_offset")
        if offset is not None:
            right_expr = right_expr + offset

        operator_map = {"eq": "exact", "neq": "exact", "gt": "gt", "gte": "gte", "lt": "lt", "lte": "lte"}
        lookup = operator_map.get(operator)
        if not lookup:
            return q

        if operator == "neq":
            return ~Q(**{f"{left_field}__{lookup}": right_expr})
        return Q(**{f"{left_field}__{lookup}": right_expr})

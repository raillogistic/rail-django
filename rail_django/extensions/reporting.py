"""
BI reporting module integrated with the GraphQL auto schema.

This extension lets us declare reusable datasets, drive rich visualizations, and
manage export jobs (PDF/CSV/JSON) without custom resolvers. Everything is stored
as Django models so the GraphQL generator can expose CRUD plus method mutations
used by the frontend to render tables, charts, and document exports.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from django.apps import apps
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import connection, models
from django.db.models import (
    Avg,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Max,
    Min,
    Q,
    Sum,
    Value,
)
from django.contrib.postgres.aggregates import (
    ArrayAgg,
    BitAnd,
    BitOr,
    BitXor,
    BoolAnd,
    BoolOr,
    JSONBAgg,
    StringAgg,
)
from django.db.models.functions import (
    ExtractDay,
    ExtractMonth,
    ExtractQuarter,
    ExtractWeek,
    ExtractWeekDay,
    ExtractYear,
    Lower,
    TruncDate,
    TruncDay,
    TruncHour,
    TruncMonth,
    TruncQuarter,
    TruncWeek,
    TruncYear,
    Upper,
)
from django.utils.encoding import force_str
from django.utils.functional import Promise
from django.utils import timezone

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase
from rail_django.decorators import action_form, confirm_action

logger = logging.getLogger(__name__)


class ReportingError(Exception):
    """Raised when a reporting configuration cannot be executed."""


@dataclass
class FilterSpec:
    """Declarative filter used by the execution engine."""

    field: str
    lookup: str = "exact"
    value: Any = None
    connector: str = "and"
    negate: bool = False


@dataclass
class DimensionSpec:
    """Dimension exposed to the frontend for grouping/pivoting."""

    name: str
    field: str
    label: str = ""
    transform: Optional[str] = None
    help_text: str = ""


@dataclass
class MetricSpec:
    """Numeric metric declared for the dataset."""

    name: str
    field: str
    aggregation: str = "sum"
    label: str = ""
    help_text: str = ""
    format: Optional[str] = None
    filter: Optional[Any] = None
    options: Optional[Dict[str, Any]] = None


@dataclass
class ComputedFieldSpec:
    """Client-side computed value derived from dimension/metric columns."""

    name: str
    formula: str
    label: str = ""
    help_text: str = ""
    stage: str = "post"


DEFAULT_ALLOWED_LOOKUPS = {
    "exact",
    "iexact",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "in",
    "range",
    "isnull",
    "gt",
    "gte",
    "lt",
    "lte",
}

DEFAULT_MAX_LIMIT = 5_000

AGGREGATION_MAP = {
    "count": Count,
    "distinct_count": lambda expr, *, filter_q=None: Count(
        expr, distinct=True, filter=filter_q
    ),
    "sum": lambda expr, *, filter_q=None: Sum(expr, filter=filter_q),
    "avg": lambda expr, *, filter_q=None: Avg(expr, filter=filter_q),
    "min": lambda expr, *, filter_q=None: Min(expr, filter=filter_q),
    "max": lambda expr, *, filter_q=None: Max(expr, filter=filter_q),
}

POSTGRES_AGGREGATIONS = {
    "array_agg",
    "bit_and",
    "bit_or",
    "bit_xor",
    "bool_and",
    "bool_or",
    "jsonb_agg",
    "string_agg",
}

SAFE_EXPR_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.Load,
    ast.Name,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.BoolOp,
    ast.And,
    ast.Or,
)


SAFE_QUERY_EXPR_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.Load,
    ast.Name,
)


def _safe_query_expression(formula: str, *, allowed_names: set[str]) -> Any:
    """
    Build a Django ORM expression from a simple arithmetic formula.

    Supported:
    - arithmetic operators: +, -, *, /, %, **
    - variables: any name in `allowed_names` (resolved as `F(name)`)
    - constants: numbers / booleans / nulls
    """

    try:
        tree = ast.parse(formula, mode="eval")
    except Exception as exc:
        raise ReportingError(f"Expression invalide '{formula}': {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, SAFE_QUERY_EXPR_NODES):
            raise ReportingError(
                f"Expression non supportee dans '{formula}': {node.__class__.__name__}"
            )

    def build(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return build(node.body)
        if isinstance(node, ast.Num):  # pragma: no cover (py<3.8)
            return Value(node.n)
        if isinstance(node, ast.Constant):
            return Value(node.value)
        if isinstance(node, ast.Name):
            if node.id not in allowed_names:
                raise ReportingError(
                    f"Variable non autorisee '{node.id}' dans '{formula}'."
                )
            return F(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -build(node.operand)
        if isinstance(node, ast.BinOp):
            left = build(node.left)
            right = build(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left**right
            if isinstance(node.op, ast.Div):
                return ExpressionWrapper(left / right, output_field=FloatField())
        raise ReportingError(
            f"Expression non supportee dans '{formula}': {node.__class__.__name__}"
        )

    return build(tree)


def _safe_formula_eval(formula: str, context: Dict[str, Any]) -> Any:
    """Evaluate simple arithmetic/boolean expressions without builtins."""

    try:
        tree = ast.parse(formula, mode="eval")
    except Exception as exc:
        raise ReportingError(f"Expression invalide '{formula}': {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, SAFE_EXPR_NODES):
            raise ReportingError(
                f"Expression non supportee dans '{formula}': {node.__class__.__name__}"
            )
        if isinstance(node, ast.Name) and node.id not in context:
            context[node.id] = 0

    compiled = compile(tree, "<reporting-formula>", "eval")
    return eval(compiled, {"__builtins__": {}}, context)


def _to_filter_list(
    raw_filters: Optional[Iterable[Dict[str, Any]]],
) -> List[FilterSpec]:
    if not raw_filters:
        return []

    normalized: List[FilterSpec] = []
    for item in raw_filters:
        if not isinstance(item, dict):
            continue
        field_name = item.get("field")
        lookup = item.get("lookup") or "exact"
        value = item.get("value")
        connector = item.get("connector") or "and"
        negate = bool(item.get("negate") or item.get("not"))
        if not field_name:
            continue
        normalized.append(
            FilterSpec(
                field=str(field_name),
                lookup=str(lookup),
                value=value,
                connector=str(connector).lower(),
                negate=negate,
            )
        )
    return normalized


def _to_ordering(ordering: Optional[Iterable[str]]) -> List[str]:
    if ordering is None:
        return []
    if isinstance(ordering, str):
        ordering = [ordering]
    return [str(value) for value in ordering if value]


def _coerce_int(value: Any, *, default: int) -> int:
    """
    Coerce a GraphQL input value to an integer.

    The reporting extension is consumed through the auto-generated GraphQL
    schema, where action form inputs can reach the backend as strings even when
    declared as numbers. This helper makes BI preview/render endpoints tolerant
    to that behavior.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return default

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "":
            return default
        try:
            return int(cleaned)
        except ValueError:
            try:
                return int(float(cleaned))
            except ValueError as exc:
                raise ReportingError(
                    f"Limite invalide '{value}'. Valeur attendue: entier."
                ) from exc

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ReportingError(
            f"Limite invalide '{value}'. Valeur attendue: entier."
        ) from exc


def _stable_json_dumps(value: Any) -> str:
    """
    Serialize a Python object to JSON in a stable way.

    Used to build deterministic cache keys for BI queries.
    """

    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )


def _hash_query_payload(payload: Any) -> str:
    """Return a short stable hash for a query spec/payload."""

    digest = hashlib.sha256(_stable_json_dumps(payload).encode("utf-8")).hexdigest()
    return digest[:24]


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: Any, *, fallback: str) -> str:
    """
    Normalize user-provided names (JSON) into a Python/Django-friendly identifier.

    `annotate(**{name: ...})` and `values(**{name: ...})` require keyword-safe keys.
    """

    raw = str(value or "").strip()
    candidate = raw.replace("__", "_")
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if not candidate:
        candidate = fallback
    if candidate[0].isdigit():
        candidate = f"{fallback}_{candidate}"
    if not _IDENTIFIER_PATTERN.match(candidate):
        candidate = fallback
    return candidate


def _combine_q(conditions: Sequence[Q], *, op: str) -> Optional[Q]:
    if not conditions:
        return None
    op = (op or "and").lower()
    combined = conditions[0]
    for condition in conditions[1:]:
        combined = (combined | condition) if op == "or" else (combined & condition)
    return combined


def _json_sanitize(value: Any) -> Any:
    """
    Convert values to JSON-serializable primitives.

    The reporting engine returns dict payloads as GraphQL Generic scalars.
    Graphene-Django serializes the full response with `json.dumps(...)` (no
    DjangoJSONEncoder), so we must ensure all nested values are compatible with
    the standard library encoder (including lazy translations).
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Promise):
        return force_str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        try:
            return float(value)
        except Exception:
            return str(value)

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, dict):
        return {
            str(_json_sanitize(key)): _json_sanitize(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_sanitize(item) for item in value]

    return force_str(value)


class DatasetExecutionEngine:
    """
    Executes a ReportingDataset definition against its underlying model.

    The engine converts JSON definitions (dimensions, metrics, filters, computed
    fields) into QuerySets and serializable payloads used by GraphQL mutations.
    """

    def __init__(self, dataset: "ReportingDataset"):
        self.dataset = dataset
        self.model = self._load_model()
        self.dimensions = self._load_dimensions()
        self.metrics = self._load_metrics()
        self.computed_fields = self._load_computed_fields()

    def _load_model(self) -> models.Model:
        try:
            return apps.get_model(
                self.dataset.source_app_label, self.dataset.source_model
            )
        except LookupError as exc:
            raise ReportingError(
                f"Impossible de trouver le modele {self.dataset.source_app_label}.{self.dataset.source_model}"
            ) from exc

    def _meta(self) -> dict:
        return dict(self.dataset.metadata or {})

    def _default_pk_field(self) -> str:
        pk = getattr(self.model._meta, "pk", None)
        name = getattr(pk, "name", None)
        return name or "id"

    def _allow_ad_hoc(self) -> bool:
        return bool(self._meta().get("allow_ad_hoc"))

    def _max_limit(self) -> int:
        return _coerce_int(self._meta().get("max_limit"), default=DEFAULT_MAX_LIMIT)

    def _cache_ttl_seconds(self) -> int:
        return _coerce_int(self._meta().get("cache_ttl_seconds"), default=0)

    def _allowed_lookups(self) -> set[str]:
        configured = self._meta().get("allowed_lookups")
        if isinstance(configured, list) and configured:
            return {str(item).strip() for item in configured if item}
        return set(DEFAULT_ALLOWED_LOOKUPS)

    def _allowed_ad_hoc_fields(self) -> set[str]:
        configured = self._meta().get("allowed_fields") or []
        if not isinstance(configured, list):
            return set()
        return {str(item).strip() for item in configured if item}

    def _allowed_where_fields(self) -> set[str]:
        """
        Base allow-list for WHERE filters.

        By default we allow filtering by any field referenced by the dataset
        dimensions/metrics, plus optional `metadata.allowed_fields`.
        """

        allowed = {dim.field for dim in self.dimensions if dim.field} | {
            metric.field for metric in self.metrics if metric.field
        }
        allowed |= self._allowed_ad_hoc_fields()
        return {value for value in allowed if value and isinstance(value, str)}

    def _record_field_allowlist(self) -> Optional[set[str]]:
        """
        Allow-list for records mode field selection.

        Priority:
        - explicit `metadata.record_fields`
        - fallback to `metadata.fields`
        - if allow_ad_hoc + allowed_fields configured, use allowed fields
        - if allow_ad_hoc and no allowlist, allow any valid field
        - otherwise, restrict to dataset dimensions/metrics + allowed_fields
        """

        meta = self._meta()
        configured = meta.get("record_fields")
        if isinstance(configured, list) and configured:
            return {str(item).strip() for item in configured if item}

        configured = meta.get("fields")
        if isinstance(configured, list) and configured:
            return {str(item).strip() for item in configured if item}

        if self._allow_ad_hoc():
            if self._allowed_ad_hoc_fields():
                return self._allowed_where_fields()
            return None

        return self._allowed_where_fields()

    def _normalize_field_list(
        self,
        fields: Iterable[Any],
        *,
        warnings: List[str],
        allowlist: Optional[set[str]] = None,
        label: str = "Champ",
    ) -> List[str]:
        normalized: List[str] = []
        for value in fields:
            if not value:
                continue
            field_name = str(value)
            if not self._validate_field_path(field_name):
                warnings.append(f"{label} invalide: {field_name}")
                continue
            if allowlist is not None and field_name not in allowlist:
                warnings.append(f"{label} non autorise: {field_name}")
                continue
            normalized.append(field_name)
        return normalized

    def _validate_field_path(self, field_path: str) -> bool:
        """
        Validate a Django ORM field path (including relations via `__`).

        This prevents typos and rejects reverse relations / unsupported segments.
        """

        if not field_path or not isinstance(field_path, str):
            return False
        if field_path.startswith("_"):
            return False
        parts = [part for part in field_path.split("__") if part]
        if not parts:
            return False

        current_model = self.model
        for part in parts:
            try:
                field = current_model._meta.get_field(part)
            except FieldDoesNotExist:
                return False
            if field.is_relation and getattr(field, "related_model", None):
                current_model = field.related_model
        return True

    def _is_allowed_where_field(self, field_path: str) -> bool:
        if self._allow_ad_hoc():
            return self._validate_field_path(field_path) and (
                not self._allowed_ad_hoc_fields()
                or field_path in self._allowed_where_fields()
            )
        return field_path in self._allowed_where_fields()

    def _merge_default_filters(self, where: Any) -> Any:
        default_filters_raw: Any = self.dataset.default_filters or []
        if not default_filters_raw:
            return where
        if where:
            return {"op": "and", "items": [default_filters_raw, where]}
        return default_filters_raw

    def _load_dimensions(self) -> List[DimensionSpec]:
        entries = self.dataset.dimensions or []
        parsed: List[DimensionSpec] = []
        for item in entries:
            try:
                field_path = item.get("field")
                raw_name = item.get("name") or field_path
                transform = item.get("transform")
                name = (
                    _safe_identifier(
                        raw_name, fallback=_safe_identifier(field_path, fallback="dim")
                    )
                    if (
                        transform
                        or (raw_name and field_path and raw_name != field_path)
                    )
                    else raw_name
                )
                parsed.append(
                    DimensionSpec(
                        name=name,
                        field=field_path,
                        label=item.get("label")
                        or item.get("name")
                        or item.get("field"),
                        transform=transform,
                        help_text=item.get("help_text", ""),
                    )
                )
            except Exception:
                continue
        return parsed

    def _load_metrics(self) -> List[MetricSpec]:
        entries = self.dataset.metrics or []
        parsed: List[MetricSpec] = []
        for item in entries:
            try:
                field_path = item.get("field")
                raw_name = item.get("name") or field_path
                parsed.append(
                    MetricSpec(
                        name=_safe_identifier(raw_name, fallback="metric"),
                        field=field_path,
                        aggregation=item.get("aggregation") or "sum",
                        label=item.get("label")
                        or item.get("name")
                        or item.get("field"),
                        help_text=item.get("help_text", ""),
                        format=item.get("format"),
                        filter=item.get("filter"),
                        options=item.get("options")
                        if isinstance(item.get("options"), dict)
                        else None,
                    )
                )
            except Exception:
                continue
        return parsed

    def _load_computed_fields(self) -> List[ComputedFieldSpec]:
        entries = self.dataset.computed_fields or []
        parsed: List[ComputedFieldSpec] = []
        for item in entries:
            name = item.get("name")
            formula = item.get("formula")
            if not name or not formula:
                continue
            stage = str(item.get("stage") or "post").lower()
            parsed.append(
                ComputedFieldSpec(
                    name=_safe_identifier(name, fallback="computed")
                    if stage == "query"
                    else name,
                    formula=formula,
                    label=item.get("label") or name,
                    help_text=item.get("help_text", ""),
                    stage=stage,
                )
            )
        return parsed

    def _build_dimension_values(
        self, dimensions: List[DimensionSpec]
    ) -> Tuple[dict, List[str]]:
        """
        Build `values()` kwargs for dimensions.

        Returns (values_kwargs, ordering_aliases), where ordering aliases maps
        original field paths to their dimension names when required.
        """

        values_kwargs: dict = {}
        ordering_aliases: List[str] = []
        for dim in dimensions:
            if not dim.field:
                continue
            expr = self._dimension_expression(dim)
            if dim.transform or dim.name != dim.field:
                values_kwargs[dim.name] = expr
                ordering_aliases.append(dim.field)
            else:
                values_kwargs[dim.field] = expr
        return values_kwargs, ordering_aliases

    def _dimension_expression(self, dim: DimensionSpec) -> Any:
        base = F(dim.field)
        transform = (dim.transform or "").strip().lower()
        if not transform:
            return base

        if transform == "lower":
            return Lower(base)
        if transform == "upper":
            return Upper(base)
        if transform == "date":
            return TruncDate(base)

        if transform.startswith("trunc:"):
            grain = transform.split(":", 1)[1].strip()
            trunc_map = {
                "hour": TruncHour,
                "day": TruncDay,
                "week": TruncWeek,
                "month": TruncMonth,
                "quarter": TruncQuarter,
                "year": TruncYear,
            }
            trunc = trunc_map.get(grain)
            if not trunc:
                raise ReportingError(f"Grain temporel non supporte: {grain}")
            return trunc(base)

        extract_map = {
            "year": ExtractYear,
            "quarter": ExtractQuarter,
            "month": ExtractMonth,
            "day": ExtractDay,
            "week": ExtractWeek,
            "weekday": ExtractWeekDay,
        }
        extractor = extract_map.get(transform)
        if extractor:
            return extractor(base)

        raise ReportingError(f"Transformation non supportee: {transform}")

    def _build_postgres_aggregation(
        self,
        agg_name: str,
        expr_field: str,
        *,
        filter_q: Optional[Q],
        options: Optional[dict],
    ) -> Any:
        if connection.vendor != "postgresql":
            raise ReportingError(
                f"Agregation '{agg_name}' requiert PostgreSQL."
            )

        options = options or {}
        ordering = _to_ordering(
            options.get("ordering") or options.get("order_by") or options.get("order")
        )
        extra: Dict[str, Any] = {}
        if filter_q is not None:
            extra["filter"] = filter_q
        if options.get("distinct"):
            extra["distinct"] = True
        if ordering:
            extra["ordering"] = ordering
        if "default" in options:
            extra["default"] = options.get("default")

        if agg_name == "string_agg":
            delimiter = options.get("delimiter", ", ")
            return StringAgg(expr_field, delimiter, **extra)
        if agg_name == "array_agg":
            return ArrayAgg(expr_field, **extra)
        if agg_name == "jsonb_agg":
            return JSONBAgg(expr_field, **extra)
        if agg_name == "bool_and":
            return BoolAnd(expr_field, **extra)
        if agg_name == "bool_or":
            return BoolOr(expr_field, **extra)
        if agg_name == "bit_and":
            return BitAnd(expr_field, **extra)
        if agg_name == "bit_or":
            return BitOr(expr_field, **extra)
        if agg_name == "bit_xor":
            return BitXor(expr_field, **extra)

        raise ReportingError(f"Agregation non supportee: {agg_name}")

    def _build_annotations(
        self,
        metrics: List[MetricSpec],
        *,
        allowed_where_fields: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        annotations: Dict[str, Any] = {}
        for metric in metrics:
            agg_name = (metric.aggregation or "sum").lower()
            expr_field = metric.field
            if agg_name in {"count", "distinct_count"} and (
                not expr_field or expr_field == "*"
            ):
                expr_field = "pk"

            options = metric.options or {}
            filter_q = None
            if metric.filter:
                filter_q, _, _ = self._compile_filter_tree(
                    metric.filter,
                    quick_search="",
                    allowed_fields=allowed_where_fields,
                )

            if agg_name == "count":
                annotations[metric.name] = Count(expr_field, filter=filter_q)
                continue

            if agg_name in POSTGRES_AGGREGATIONS:
                if not expr_field:
                    raise ReportingError(
                        f"Agregation '{agg_name}' requiert un champ."
                    )
                annotations[metric.name] = self._build_postgres_aggregation(
                    agg_name, expr_field, filter_q=filter_q, options=options
                )
                continue

            agg_factory = AGGREGATION_MAP.get(agg_name)
            if not agg_factory:
                raise ReportingError(f"Agregation non supportee: {agg_name}")
            annotations[metric.name] = agg_factory(expr_field, filter_q=filter_q)
        return annotations

    def _get_quick_fields(self) -> List[str]:
        meta_quick = (self.dataset.metadata or {}).get("quick_fields") or []
        if meta_quick:
            return [str(field) for field in meta_quick]
        if self.dimensions:
            return [dim.field for dim in self.dimensions[:3]]
        return []

    def _compile_filter_specs(
        self,
        specs: Sequence[FilterSpec],
        *,
        warnings: List[str],
        allowed_fields: set[str],
        allowed_lookups: set[str],
    ) -> Optional[Q]:
        combined: Optional[Q] = None
        for spec in specs:
            lookup = (spec.lookup or "exact").lower()
            if lookup not in allowed_lookups or "__" in lookup:
                warnings.append(f"Lookup non autorise: {lookup}")
                continue

            field_path = str(spec.field)
            if field_path not in allowed_fields and not self._is_allowed_where_field(
                field_path
            ):
                warnings.append(f"Champ non autorise: {field_path}")
                continue

            try:
                condition = Q(**{f"{field_path}__{lookup}": spec.value})
            except Exception as exc:
                warnings.append(f"Filtre ignore ({field_path}): {exc}")
                continue

            if spec.negate:
                condition = ~condition

            if combined is None:
                combined = condition
            else:
                combined = (
                    (combined | condition)
                    if spec.connector == "or"
                    else (combined & condition)
                )
        return combined

    def _flatten_filter_tree(self, raw: Any) -> List[FilterSpec]:
        if raw is None:
            return []
        if isinstance(raw, FilterSpec):
            return [raw]
        if isinstance(raw, list):
            flattened: List[FilterSpec] = []
            for item in raw:
                flattened.extend(self._flatten_filter_tree(item))
            return flattened
        if isinstance(raw, dict):
            if "items" in raw:
                return self._flatten_filter_tree(raw.get("items") or [])
            if "field" in raw:
                return _to_filter_list([raw])
        return []

    def _compile_filter_tree(
        self,
        raw_filters: Any,
        *,
        quick_search: str,
        allowed_fields: Optional[set[str]] = None,
        allowed_lookups: Optional[set[str]] = None,
    ) -> Tuple[Optional[Q], List[FilterSpec], List[str]]:
        warnings: List[str] = []
        allowed_fields = allowed_fields or self._allowed_where_fields()
        allowed_lookups = allowed_lookups or self._allowed_lookups()

        compiled = self._compile_filter_node(
            raw_filters,
            warnings=warnings,
            allowed_fields=allowed_fields,
            allowed_lookups=allowed_lookups,
        )

        quick_fields = self._get_quick_fields()
        if quick_search and quick_fields:
            quick_q = Q()
            for field_name in quick_fields:
                quick_q |= Q(**{f"{field_name}__icontains": quick_search})
            compiled = quick_q if compiled is None else (compiled & quick_q)

        return compiled, self._flatten_filter_tree(raw_filters), warnings

    def _compile_filter_node(
        self,
        node: Any,
        *,
        warnings: List[str],
        allowed_fields: set[str],
        allowed_lookups: set[str],
    ) -> Optional[Q]:
        if node is None:
            return None
        if isinstance(node, FilterSpec):
            return self._compile_filter_specs(
                [node],
                warnings=warnings,
                allowed_fields=allowed_fields,
                allowed_lookups=allowed_lookups,
            )
        if isinstance(node, list):
            if all(isinstance(item, FilterSpec) for item in node):
                return self._compile_filter_specs(
                    node,
                    warnings=warnings,
                    allowed_fields=allowed_fields,
                    allowed_lookups=allowed_lookups,
                )
            if all(isinstance(item, dict) and "field" in item for item in node):
                return self._compile_filter_specs(
                    _to_filter_list(node),
                    warnings=warnings,
                    allowed_fields=allowed_fields,
                    allowed_lookups=allowed_lookups,
                )
            compiled_children = [
                child
                for child in (
                    self._compile_filter_node(
                        item,
                        warnings=warnings,
                        allowed_fields=allowed_fields,
                        allowed_lookups=allowed_lookups,
                    )
                    for item in node
                )
                if child is not None
            ]
            return _combine_q(compiled_children, op="and")
        if isinstance(node, dict):
            if "items" in node:
                op = str(node.get("op") or node.get("connector") or "and").lower()
                negate = bool(node.get("negate") or node.get("not"))
                compiled_children = [
                    child
                    for child in (
                        self._compile_filter_node(
                            item,
                            warnings=warnings,
                            allowed_fields=allowed_fields,
                            allowed_lookups=allowed_lookups,
                        )
                        for item in (node.get("items") or [])
                    )
                    if child is not None
                ]
                compiled = _combine_q(compiled_children, op=op)
                return (~compiled) if (negate and compiled is not None) else compiled
            if "field" in node:
                specs = _to_filter_list([node])
                return self._compile_filter_specs(
                    specs,
                    warnings=warnings,
                    allowed_fields=allowed_fields,
                    allowed_lookups=allowed_lookups,
                )
        return None

    def _apply_where(
        self,
        queryset: models.QuerySet,
        *,
        where: Any,
        quick_search: str,
        allowed_fields: Optional[set[str]] = None,
    ) -> Tuple[models.QuerySet, List[FilterSpec], List[str]]:
        q, flat, warnings = self._compile_filter_tree(
            where,
            quick_search=quick_search,
            allowed_fields=allowed_fields,
        )
        if q is None:
            return queryset, flat, warnings
        return queryset.filter(q), flat, warnings

    def _apply_computed_fields(self, rows: List[Dict[str, Any]]) -> None:
        computed_post = [
            computed for computed in self.computed_fields if computed.stage != "query"
        ]
        if not computed_post:
            return

        for row in rows:
            context = {key: row.get(key, 0) for key in row.keys()}
            for computed in computed_post:
                try:
                    row[computed.name] = _safe_formula_eval(
                        computed.formula, dict(context)
                    )
                except ReportingError as exc:
                    row[computed.name] = None
                    row.setdefault("_warnings", []).append(str(exc))

    def describe_columns_for(
        self,
        dimensions: List[DimensionSpec],
        metrics: List[MetricSpec],
        computed_fields: List[ComputedFieldSpec],
    ) -> List[Dict[str, Any]]:
        columns: List[Dict[str, Any]] = []
        for dim in dimensions:
            columns.append(
                {
                    "name": dim.name,
                    "label": dim.label or dim.name,
                    "kind": "dimension",
                    "help_text": dim.help_text,
                    "field": dim.field,
                    "transform": dim.transform,
                }
            )
        for metric in metrics:
            columns.append(
                {
                    "name": metric.name,
                    "label": metric.label or metric.name,
                    "kind": "metric",
                    "help_text": metric.help_text,
                    "format": metric.format,
                    "field": metric.field,
                    "aggregation": metric.aggregation,
                    "options": metric.options,
                }
            )
        for computed in computed_fields:
            columns.append(
                {
                    "name": computed.name,
                    "label": computed.label or computed.name,
                    "kind": "computed",
                    "help_text": computed.help_text,
                    "stage": computed.stage,
                }
            )
        return columns

    def describe_columns(self) -> List[Dict[str, Any]]:
        return self.describe_columns_for(
            self.dimensions, self.metrics, self.computed_fields
        )

    def run(
        self,
        *,
        runtime_filters: Optional[Any] = None,
        limit: Optional[int] = None,
        ordering: Optional[List[str]] = None,
        quick_search: str = "",
    ) -> Dict[str, Any]:
        queryset = self.model.objects.all()
        default_filters_raw: Any = self.dataset.default_filters or []
        runtime_filters_raw: Any = runtime_filters or []
        if isinstance(runtime_filters_raw, list) and all(
            isinstance(item, FilterSpec) for item in runtime_filters_raw
        ):
            runtime_filters_raw = [item.__dict__ for item in runtime_filters_raw]
        where = (
            default_filters_raw
            if not runtime_filters_raw
            else {"op": "and", "items": [default_filters_raw, runtime_filters_raw]}
        )
        queryset, applied_filters, warnings = self._apply_where(
            queryset,
            where=where,
            quick_search=quick_search,
        )

        simple_dimension_fields = [
            dim.field
            for dim in self.dimensions
            if dim.field and not dim.transform and dim.name == dim.field
        ]
        alias_dimensions = [
            dim
            for dim in self.dimensions
            if dim.field and (dim.transform or dim.name != dim.field)
        ]
        alias_exprs = {
            dim.name: self._dimension_expression(dim) for dim in alias_dimensions
        }
        alias_map = {dim.field: dim.name for dim in alias_dimensions}

        annotations = self._build_annotations(
            self.metrics,
            allowed_where_fields={dim.field for dim in self.dimensions if dim.field}
            | {metric.field for metric in self.metrics if metric.field},
        )

        if simple_dimension_fields or alias_exprs:
            queryset = queryset.values(*simple_dimension_fields, **alias_exprs)
        elif not annotations:
            fallback_fields = (self.dataset.metadata or {}).get("fields") or [
                self._default_pk_field()
            ]
            queryset = queryset.values(*fallback_fields)

        if annotations:
            queryset = queryset.annotate(**annotations)

        computed_query = [
            computed for computed in self.computed_fields if computed.stage == "query"
        ]
        if computed_query:
            allowed_names = (
                set(simple_dimension_fields)
                | set(alias_exprs.keys())
                | set(annotations.keys())
            )
            computed_annotations: Dict[str, Any] = {}
            for computed in computed_query:
                try:
                    computed_annotations[computed.name] = _safe_query_expression(
                        computed.formula, allowed_names=allowed_names
                    )
                except ReportingError as exc:
                    warnings.append(str(exc))
            if computed_annotations:
                queryset = queryset.annotate(**computed_annotations)

        applied_ordering = _to_ordering(ordering) or _to_ordering(self.dataset.ordering)
        resolved_ordering: List[str] = []
        for token in applied_ordering:
            desc = token.startswith("-")
            name = token[1:] if desc else token
            resolved = alias_map.get(name, name)
            resolved_ordering.append(f"-{resolved}" if desc else resolved)
        if applied_ordering:
            queryset = queryset.order_by(*resolved_ordering)

        bounded_limit = None
        if limit is not None:
            limit_value = _coerce_int(limit, default=0)
            if limit_value < 0:
                warnings.append(f"Limite negative ignoree: {limit}")
                limit_value = 0
            bounded_limit = min(limit_value, self._max_limit())
            queryset = queryset[:bounded_limit]

        rows = list(queryset)
        self._apply_computed_fields(rows)

        payload = {
            "rows": rows,
            "columns": self.describe_columns(),
            "dimensions": [dim.__dict__ for dim in self.dimensions],
            "metrics": [metric.__dict__ for metric in self.metrics],
            "computed_fields": [comp.__dict__ for comp in self.computed_fields],
            "applied_filters": [spec.__dict__ for spec in applied_filters],
            "warnings": warnings,
            "ordering": resolved_ordering,
            "limit": bounded_limit if bounded_limit is not None else limit,
            "source": {
                "app_label": self.dataset.source_app_label,
                "model": self.dataset.source_model,
            },
        }
        return _json_sanitize(payload)

    def _resolve_dimensions(self, raw: Any) -> Tuple[List[DimensionSpec], List[str]]:
        warnings: List[str] = []
        if raw is None:
            return list(self.dimensions), warnings

        if not isinstance(raw, list):
            warnings.append("Dimensions invalides: liste attendue.")
            return list(self.dimensions), warnings

        by_name = {dim.name: dim for dim in self.dimensions}
        by_field = {dim.field: dim for dim in self.dimensions if dim.field}
        resolved: List[DimensionSpec] = []

        for entry in raw:
            if isinstance(entry, str):
                dim = by_name.get(entry) or by_field.get(entry)
                if not dim:
                    warnings.append(f"Dimension inconnue: {entry}")
                    continue
                resolved.append(dim)
                continue

            if isinstance(entry, dict):
                field_path = entry.get("field")
                raw_name = entry.get("name") or field_path
                transform = entry.get("transform")
                if not field_path:
                    warnings.append("Dimension incomplete: champ manquant.")
                    continue
                if not self._allow_ad_hoc() and raw_name not in by_name:
                    warnings.append(f"Dimension ad-hoc refusee: {raw_name}")
                    continue
                name = (
                    _safe_identifier(
                        raw_name, fallback=_safe_identifier(field_path, fallback="dim")
                    )
                    if (transform or (raw_name and raw_name != field_path))
                    else raw_name
                )
                resolved.append(
                    DimensionSpec(
                        name=name,
                        field=field_path,
                        label=entry.get("label") or raw_name or field_path,
                        transform=transform,
                        help_text=entry.get("help_text", ""),
                    )
                )
                continue

            warnings.append("Dimension invalide: string/dict attendu.")

        return resolved, warnings

    def _resolve_metrics(self, raw: Any) -> Tuple[List[MetricSpec], List[str]]:
        warnings: List[str] = []
        if raw is None:
            return list(self.metrics), warnings

        if not isinstance(raw, list):
            warnings.append("Mesures invalides: liste attendue.")
            return list(self.metrics), warnings

        by_name = {metric.name: metric for metric in self.metrics}
        resolved: List[MetricSpec] = []
        for entry in raw:
            if isinstance(entry, str):
                metric = by_name.get(entry)
                if not metric:
                    warnings.append(f"Mesure inconnue: {entry}")
                    continue
                resolved.append(metric)
                continue

            if isinstance(entry, dict):
                field_path = entry.get("field")
                raw_name = entry.get("name") or field_path
                if not raw_name:
                    warnings.append("Mesure incomplete: nom manquant.")
                    continue
                if not field_path and (entry.get("aggregation") or "").lower() not in {
                    "count"
                }:
                    warnings.append(f"Mesure incomplete ({raw_name}): champ manquant.")
                    continue
                if not self._allow_ad_hoc() and raw_name not in by_name:
                    warnings.append(f"Mesure ad-hoc refusee: {raw_name}")
                    continue
                resolved.append(
                    MetricSpec(
                        name=_safe_identifier(raw_name, fallback="metric"),
                        field=field_path or "pk",
                        aggregation=entry.get("aggregation") or "sum",
                        label=entry.get("label") or raw_name,
                        help_text=entry.get("help_text", ""),
                        format=entry.get("format"),
                        filter=entry.get("filter"),
                        options=entry.get("options")
                        if isinstance(entry.get("options"), dict)
                        else None,
                    )
                )
                continue

            warnings.append("Mesure invalide: string/dict attendu.")

        return resolved, warnings

    def _resolve_computed_fields(
        self, raw: Any
    ) -> Tuple[List[ComputedFieldSpec], List[str]]:
        warnings: List[str] = []
        if raw is None:
            return list(self.computed_fields), warnings

        if not isinstance(raw, list):
            warnings.append("Champs calcules invalides: liste attendue.")
            return list(self.computed_fields), warnings

        by_name = {computed.name: computed for computed in self.computed_fields}
        resolved: List[ComputedFieldSpec] = []
        for entry in raw:
            if isinstance(entry, str):
                computed = by_name.get(entry)
                if not computed:
                    warnings.append(f"Champ calcule inconnu: {entry}")
                    continue
                resolved.append(computed)
                continue

            if isinstance(entry, dict):
                name = entry.get("name")
                formula = entry.get("formula")
                if not name or not formula:
                    warnings.append("Champ calcule incomplet: name/formula requis.")
                    continue
                stage = str(entry.get("stage") or "post").lower()
                resolved.append(
                    ComputedFieldSpec(
                        name=_safe_identifier(name, fallback="computed")
                        if stage == "query"
                        else name,
                        formula=formula,
                        label=entry.get("label") or name,
                        help_text=entry.get("help_text", ""),
                        stage=stage,
                    )
                )
                continue

            warnings.append("Champ calcule invalide: string/dict attendu.")

        return resolved, warnings

    def _compile_annotation_filter_specs(
        self,
        specs: Sequence[FilterSpec],
        *,
        warnings: List[str],
        allowed_names: set[str],
        allowed_lookups: set[str],
    ) -> Optional[Q]:
        combined: Optional[Q] = None
        for spec in specs:
            lookup = (spec.lookup or "exact").lower()
            if lookup not in allowed_lookups or "__" in lookup:
                warnings.append(f"Lookup non autorise: {lookup}")
                continue

            name = str(spec.field)
            if name not in allowed_names:
                warnings.append(f"Champ non autorise: {name}")
                continue

            try:
                condition = Q(**{f"{name}__{lookup}": spec.value})
            except Exception as exc:
                warnings.append(f"Filtre ignore ({name}): {exc}")
                continue

            if spec.negate:
                condition = ~condition

            if combined is None:
                combined = condition
            else:
                combined = (
                    (combined | condition)
                    if spec.connector == "or"
                    else (combined & condition)
                )
        return combined

    def _compile_annotation_filter_tree(
        self,
        raw_filters: Any,
        *,
        allowed_names: set[str],
        allowed_lookups: Optional[set[str]] = None,
    ) -> Tuple[Optional[Q], List[str]]:
        warnings: List[str] = []
        allowed_lookups = allowed_lookups or self._allowed_lookups()

        if raw_filters is None:
            return None, warnings

        if isinstance(raw_filters, list) and all(
            isinstance(item, dict) and "field" in item for item in raw_filters
        ):
            q = self._compile_annotation_filter_specs(
                _to_filter_list(raw_filters),
                warnings=warnings,
                allowed_names=allowed_names,
                allowed_lookups=allowed_lookups,
            )
            return q, warnings

        if isinstance(raw_filters, dict) and "items" in raw_filters:
            op = str(
                raw_filters.get("op") or raw_filters.get("connector") or "and"
            ).lower()
            negate = bool(raw_filters.get("negate") or raw_filters.get("not"))
            compiled_children: List[Q] = []
            for item in raw_filters.get("items") or []:
                child_q, child_warnings = self._compile_annotation_filter_tree(
                    item,
                    allowed_names=allowed_names,
                    allowed_lookups=allowed_lookups,
                )
                warnings.extend(child_warnings)
                if child_q is not None:
                    compiled_children.append(child_q)
            q = _combine_q(compiled_children, op=op)
            return ((~q) if (negate and q is not None) else q), warnings

        if isinstance(raw_filters, dict) and "field" in raw_filters:
            q = self._compile_annotation_filter_specs(
                _to_filter_list([raw_filters]),
                warnings=warnings,
                allowed_names=allowed_names,
                allowed_lookups=allowed_lookups,
            )
            return q, warnings

        warnings.append("Filtres HAVING invalides.")
        return None, warnings

    def _apply_computed_fields_runtime(
        self, rows: List[Dict[str, Any]], computed_fields: List[ComputedFieldSpec]
    ) -> None:
        computed_post = [
            computed for computed in computed_fields if computed.stage != "query"
        ]
        if not computed_post:
            return

        for row in rows:
            context = {key: row.get(key, 0) for key in row.keys()}
            for computed in computed_post:
                try:
                    row[computed.name] = _safe_formula_eval(
                        computed.formula, dict(context)
                    )
                except ReportingError as exc:
                    row[computed.name] = None
                    row.setdefault("_warnings", []).append(str(exc))

    def run_query(self, spec: Optional[dict] = None) -> Dict[str, Any]:
        """
        Execute a dynamic query (semantic layer) for dashboards.

        Spec (JSON) keys:
        - `mode`: "aggregate" (default) or "records"
        - `dimensions` / `metrics` / `computed_fields`: list of names or dict specs
        - `filters`: filter tree (WHERE)
        - `having`: filter tree (HAVING) applied on metric/computed aliases
        - `ordering`: list or string (e.g. ["-total_cost"])
        - `limit`, `offset`, `quick`
        - `pivot`: {index, columns, values} (optional)
        - `cache`: bool (optional, defaults to true)
        """

        spec = dict(spec or {})
        mode = str(spec.get("mode") or "aggregate").lower()
        quick_search = str(spec.get("quick") or "")
        limit = _coerce_int(spec.get("limit"), default=self.dataset.preview_limit)
        offset = _coerce_int(spec.get("offset"), default=0)
        ordering = _to_ordering(spec.get("ordering")) or _to_ordering(
            self.dataset.ordering
        )
        where = spec.get("filters") if "filters" in spec else spec.get("where")
        having = spec.get("having")
        where = self._merge_default_filters(where)

        cache_enabled = spec.get("cache", True)
        ttl = self._cache_ttl_seconds()
        cache_key = None
        if cache_enabled and ttl > 0:
            cache_key = (
                f"rail_django:reporting:{self.dataset.id}:{self.dataset.updated_at.isoformat()}:"
                f"{_hash_query_payload(spec)}"
            )
            cached = cache.get(cache_key)
            if cached:
                payload = dict(cached)
                payload["cache"] = {"hit": True, "key": cache_key, "ttl_seconds": ttl}
                return payload

        warnings: List[str] = []

        if mode == "records":
            queryset = self.model.objects.all()
            queryset, applied_filters, where_warnings = self._apply_where(
                queryset,
                where=where,
                quick_search=quick_search,
            )
            warnings.extend(where_warnings)

            meta_fields = self._meta().get("fields") or []
            if isinstance(meta_fields, str):
                meta_fields = [meta_fields]
            if not isinstance(meta_fields, list):
                meta_fields = []

            fields_specified = "fields" in spec
            pk_field = self._default_pk_field()
            fields = (
                spec.get("fields")
                if fields_specified
                else (meta_fields or [pk_field])
            )
            if isinstance(fields, str):
                fields = [fields]
            if not isinstance(fields, list):
                fields = [pk_field]

            allowed_record_fields = self._record_field_allowlist()
            selected_fields = self._normalize_field_list(
                fields,
                warnings=warnings,
                allowlist=allowed_record_fields,
                label="Champ",
            )
            if not selected_fields and fields_specified and meta_fields:
                selected_fields = self._normalize_field_list(
                    meta_fields,
                    warnings=warnings,
                    allowlist=allowed_record_fields,
                    label="Champ",
                )
            if not selected_fields:
                if allowed_record_fields is None or pk_field in (
                    allowed_record_fields or set()
                ):
                    selected_fields = [pk_field]
                else:
                    raise ReportingError(
                        "Aucun champ autorise pour le mode records."
                    )

            resolved_ordering: List[str] = []
            for token in ordering:
                name = token.lstrip("-")
                if not self._validate_field_path(name):
                    warnings.append(f"Tri invalide: {token}")
                    continue
                if allowed_record_fields is not None and name not in allowed_record_fields:
                    warnings.append(f"Tri non autorise: {token}")
                    continue
                resolved_ordering.append(token)
            if resolved_ordering:
                queryset = queryset.order_by(*resolved_ordering)

            bounded_limit = min(int(limit), self._max_limit())
            if offset:
                queryset = queryset[offset : offset + bounded_limit]
            else:
                queryset = queryset[:bounded_limit]

            payload = {
                "mode": "records",
                "rows": list(queryset.values(*selected_fields)),
                "fields": selected_fields,
                "applied_filters": [spec.__dict__ for spec in applied_filters],
                "ordering": resolved_ordering,
                "limit": bounded_limit,
                "offset": offset,
                "warnings": warnings,
                "source": {
                    "app_label": self.dataset.source_app_label,
                    "model": self.dataset.source_model,
                },
                "query": spec,
                "dataset": {
                    "id": getattr(self.dataset, "id", None),
                    "code": self.dataset.code,
                    "title": self.dataset.title,
                },
            }
            if cache_key:
                cache.set(cache_key, payload, ttl)
                payload["cache"] = {"hit": False, "key": cache_key, "ttl_seconds": ttl}
            return _json_sanitize(payload)

        dimensions, dim_warnings = self._resolve_dimensions(spec.get("dimensions"))
        metrics, metric_warnings = self._resolve_metrics(spec.get("metrics"))
        computed_fields, computed_warnings = self._resolve_computed_fields(
            spec.get("computed_fields")
        )
        warnings.extend(dim_warnings + metric_warnings + computed_warnings)

        queryset = self.model.objects.all()
        allowed_where_fields = {dim.field for dim in dimensions if dim.field} | {
            metric.field for metric in metrics if metric.field
        }
        queryset, applied_filters, where_warnings = self._apply_where(
            queryset,
            where=where,
            quick_search=quick_search,
            allowed_fields=allowed_where_fields,
        )
        warnings.extend(where_warnings)

        simple_dimension_fields = [
            dim.field
            for dim in dimensions
            if dim.field and not dim.transform and dim.name == dim.field
        ]
        alias_dimensions = [
            dim
            for dim in dimensions
            if dim.field and (dim.transform or dim.name != dim.field)
        ]
        alias_exprs = {
            dim.name: self._dimension_expression(dim) for dim in alias_dimensions
        }
        alias_map = {dim.field: dim.name for dim in alias_dimensions}

        annotations = self._build_annotations(
            metrics, allowed_where_fields=allowed_where_fields
        )

        fallback_fields: List[str] = []
        if simple_dimension_fields or alias_exprs:
            queryset = queryset.values(*simple_dimension_fields, **alias_exprs)
        elif not annotations:
            fallback_fields = self._normalize_field_list(
                self._meta().get("fields") or [self._default_pk_field()],
                warnings=warnings,
                allowlist=None,
                label="Champ",
            )
            if not fallback_fields:
                fallback_fields = [self._default_pk_field()]
            queryset = queryset.values(*fallback_fields)

        if annotations:
            queryset = queryset.annotate(**annotations)

        computed_query = [
            computed for computed in computed_fields if computed.stage == "query"
        ]
        if computed_query:
            allowed_names = (
                set(simple_dimension_fields)
                | set(alias_exprs.keys())
                | set(annotations.keys())
                | set(fallback_fields)
            )
            computed_annotations: Dict[str, Any] = {}
            for computed in computed_query:
                try:
                    computed_annotations[computed.name] = _safe_query_expression(
                        computed.formula, allowed_names=allowed_names
                    )
                except ReportingError as exc:
                    warnings.append(str(exc))
            if computed_annotations:
                queryset = queryset.annotate(**computed_annotations)

        allowed_having_names = set(annotations.keys()) | {
            comp.name for comp in computed_query
        }
        having_q, having_warnings = self._compile_annotation_filter_tree(
            having, allowed_names=allowed_having_names
        )
        warnings.extend(having_warnings)
        if having_q is not None:
            queryset = queryset.filter(having_q)

        resolved_ordering: List[str] = []
        allowed_ordering_names = (
            set(simple_dimension_fields)
            | set(alias_exprs.keys())
            | set(annotations.keys())
            | {comp.name for comp in computed_query}
        )
        for token in ordering:
            desc = token.startswith("-")
            name = token[1:] if desc else token
            resolved = alias_map.get(name, name)
            if resolved not in allowed_ordering_names:
                warnings.append(f"Tri ignore: {token}")
                continue
            resolved_ordering.append(f"-{resolved}" if desc else resolved)

        if resolved_ordering:
            queryset = queryset.order_by(*resolved_ordering)

        bounded_limit = min(int(limit), self._max_limit())
        if offset:
            queryset = queryset[offset : offset + bounded_limit]
        else:
            queryset = queryset[:bounded_limit]

        rows = list(queryset)
        self._apply_computed_fields_runtime(rows, computed_fields)

        payload: Dict[str, Any] = {
            "mode": "aggregate",
            "rows": rows,
            "columns": self.describe_columns_for(dimensions, metrics, computed_fields),
            "dimensions": [dim.__dict__ for dim in dimensions],
            "metrics": [metric.__dict__ for metric in metrics],
            "computed_fields": [comp.__dict__ for comp in computed_fields],
            "applied_filters": [spec.__dict__ for spec in applied_filters],
            "ordering": resolved_ordering,
            "limit": bounded_limit,
            "offset": offset,
            "warnings": warnings,
            "source": {
                "app_label": self.dataset.source_app_label,
                "model": self.dataset.source_model,
            },
            "query": spec,
            "dataset": {
                "id": getattr(self.dataset, "id", None),
                "code": self.dataset.code,
                "title": self.dataset.title,
            },
        }

        pivot = spec.get("pivot")
        if isinstance(pivot, dict):
            pivot_index = pivot.get("index")
            pivot_columns = pivot.get("columns")
            pivot_values = pivot.get("values")
            if isinstance(pivot_values, str):
                pivot_values = [pivot_values]
            if (
                isinstance(pivot_index, str)
                and isinstance(pivot_columns, str)
                and isinstance(pivot_values, list)
            ):
                payload["pivot"] = self._pivot_rows(
                    rows,
                    index=pivot_index,
                    columns=pivot_columns,
                    values=[str(value) for value in pivot_values if value],
                )

        if cache_key:
            cache.set(cache_key, payload, ttl)
            payload["cache"] = {"hit": False, "key": cache_key, "ttl_seconds": ttl}

        return _json_sanitize(payload)

    def describe_dataset(
        self,
        *,
        include_model_fields: bool = True,
    ) -> Dict[str, Any]:
        """
        Return a description payload used by dashboard builders.

        The payload exposes the dataset semantic layer plus an optional snapshot
        of the underlying Django model fields.
        """

        meta = self._meta()
        payload: Dict[str, Any] = {
            "dataset": {
                "id": getattr(self.dataset, "id", None),
                "code": self.dataset.code,
                "title": self.dataset.title,
                "description": self.dataset.description,
                "source_kind": self.dataset.source_kind,
                "source": {
                    "app_label": self.dataset.source_app_label,
                    "model": self.dataset.source_model,
                },
                "ui": meta,
            },
            "semantic_layer": {
                "dimensions": [dim.__dict__ for dim in self.dimensions],
                "metrics": [metric.__dict__ for metric in self.metrics],
                "computed_fields": [
                    computed.__dict__ for computed in self.computed_fields
                ],
                "allowed_lookups": sorted(self._allowed_lookups()),
                "allow_ad_hoc": self._allow_ad_hoc(),
                "allowed_fields": sorted(self._allowed_ad_hoc_fields()),
                "max_limit": self._max_limit(),
                "cache_ttl_seconds": self._cache_ttl_seconds(),
            },
        }

        if not include_model_fields:
            return _json_sanitize(payload)

        fields: List[Dict[str, Any]] = []
        for field in self.model._meta.get_fields():
            if getattr(field, "auto_created", False) and not getattr(
                field, "concrete", False
            ):
                continue
            if getattr(field, "many_to_many", False) and getattr(
                field, "auto_created", False
            ):
                continue
            related_model = getattr(field, "related_model", None)
            info: Dict[str, Any] = {
                "name": getattr(field, "name", None),
                "verbose_name": str(getattr(field, "verbose_name", "")),
                "type": field.__class__.__name__,
                "internal_type": getattr(field, "get_internal_type", lambda: "")(),
                "is_relation": bool(getattr(field, "is_relation", False)),
                "many_to_many": bool(getattr(field, "many_to_many", False)),
                "many_to_one": bool(getattr(field, "many_to_one", False)),
                "one_to_one": bool(getattr(field, "one_to_one", False)),
                "null": bool(getattr(field, "null", False)),
                "blank": bool(getattr(field, "blank", False)),
            }
            if related_model is not None:
                info["related_model"] = (
                    f"{related_model._meta.app_label}.{related_model.__name__}"
                )
            choices = getattr(field, "choices", None)
            if choices:
                info["choices"] = [
                    {"value": _json_sanitize(value), "label": _json_sanitize(label)}
                    for value, label in choices[:50]
                ]
            fields.append(info)

        payload["model_fields"] = fields
        return _json_sanitize(payload)

    def _pivot_rows(
        self,
        rows: List[Dict[str, Any]],
        *,
        index: str,
        columns: str,
        values: List[str],
    ) -> Dict[str, Any]:
        """
        Pivot an aggregated result into a matrix-like payload.

        Returns a dictionary containing:
        - `index_values`, `column_values`
        - `rows`: list of row dicts with dynamic value keys
        """

        index_values: List[Any] = []
        column_values: List[Any] = []
        table: Dict[Any, Dict[str, Any]] = {}

        def ensure_list_add(target: List[Any], value: Any) -> None:
            if value not in target:
                target.append(value)

        for row in rows:
            idx = row.get(index)
            col = row.get(columns)
            ensure_list_add(index_values, idx)
            ensure_list_add(column_values, col)
            table.setdefault(idx, {index: idx})
            for metric in values:
                table[idx][f"{col}:{metric}"] = row.get(metric)

        return _json_sanitize(
            {
                "index": index,
                "columns": columns,
                "values": values,
                "index_values": index_values,
                "column_values": column_values,
                "rows": [table[idx] for idx in index_values],
            }
        )


def _reporting_roles() -> Dict[str, GraphQLMetaBase.Role]:
    return {
        "reporting_admin": GraphQLMetaBase.Role(
            name="reporting_admin",
            description="Administrateur BI (modeles, exports, securite)",
            permissions=[
                "rail_django.add_reportingdataset",
                "rail_django.change_reportingdataset",
                "rail_django.delete_reportingdataset",
                "rail_django.view_reportingdataset",
            ],
            parent_roles=[],
        ),
        "reporting_author": GraphQLMetaBase.Role(
            name="reporting_author",
            description="Concepteur de rapports (datasets et visuels)",
            permissions=[
                "rail_django.add_reportingdataset",
                "rail_django.change_reportingdataset",
                "rail_django.view_reportingdataset",
                "rail_django.add_reportingvisualization",
                "rail_django.change_reportingvisualization",
                "rail_django.view_reportingvisualization",
            ],
            parent_roles=["reporting_admin"],
        ),
        "reporting_viewer": GraphQLMetaBase.Role(
            name="reporting_viewer",
            description="Consultation des rapports et exports",
            permissions=[
                "rail_django.view_reportingdataset",
                "rail_django.view_reportingvisualization",
                "rail_django.view_reportingreport",
            ],
            parent_roles=["reporting_author"],
        ),
    }


def _reporting_operations() -> Dict[str, GraphQLMetaBase.OperationGuard]:
    return {
        "list": GraphQLMetaBase.OperationGuard(
            name="list",
            roles=["reporting_viewer", "reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "retrieve": GraphQLMetaBase.OperationGuard(
            name="retrieve",
            roles=["reporting_viewer", "reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "create": GraphQLMetaBase.OperationGuard(
            name="create",
            roles=["reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "update": GraphQLMetaBase.OperationGuard(
            name="update",
            roles=["reporting_author", "reporting_admin"],
            permissions=[],
        ),
        "delete": GraphQLMetaBase.OperationGuard(
            name="delete",
            roles=["reporting_admin"],
            permissions=[],
        ),
    }


class ReportingDataset(models.Model):
    """Stores reusable dataset definitions for BI rendering."""

    class SourceKind(models.TextChoices):
        MODEL = "model", "Modele Django"
        SQL = "sql", "SQL"
        GRAPHQL = "graphql", "GraphQL"
        PYTHON = "python", "Python"

    code = models.SlugField(unique=True, max_length=80, verbose_name="Code")
    title = models.CharField(max_length=120, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description detaillee")
    source_app_label = models.CharField(
        max_length=120, verbose_name="Application source"
    )
    source_model = models.CharField(max_length=120, verbose_name="Modele source")
    source_kind = models.CharField(
        max_length=30,
        choices=SourceKind.choices,
        default=SourceKind.MODEL,
        verbose_name="Type de source",
    )
    default_filters = models.JSONField(
        default=list,
        verbose_name="Filtres par defaut",
        help_text="Liste de filtres {field, lookup, value}.",
    )
    dimensions = models.JSONField(
        default=list,
        verbose_name="Dimensions",
        help_text="Colonnes pour regroupements/axes.",
    )
    metrics = models.JSONField(
        default=list,
        verbose_name="Mesures",
        help_text="Agregations (sum, avg, count...).",
    )
    computed_fields = models.JSONField(
        default=list,
        verbose_name="Champs calcules",
        help_text="Formules basees sur dimensions/mesures.",
    )
    ordering = models.JSONField(
        default=list,
        verbose_name="Tri par defaut",
        help_text="Expressions order_by appliquees lors des executions.",
    )
    preview_limit = models.PositiveIntegerField(
        default=50, verbose_name="Limite apercu"
    )
    metadata = models.JSONField(
        default=dict,
        verbose_name="Metadonnees UI",
        help_text="Sections, quick fields, champs favorises.",
    )
    last_materialized_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Derniere materialisation"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mise a jour")

    class Meta:
        app_label = "rail_django"
        verbose_name = "Jeu de donnees BI"
        verbose_name_plural = "Jeux de donnees BI"
        ordering = ["title", "code"]
        permissions = [
            ("run_dataset_preview", "Peut executer un apercu de dataset"),
            ("materialize_dataset", "Peut materialiser un dataset"),
        ]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["code", "title", "description"],
            fields={
                "code": GraphQLMetaBase.FilterField(lookups=["icontains", "exact"]),
                "title": GraphQLMetaBase.FilterField(lookups=["icontains"]),
                "source_app_label": GraphQLMetaBase.FilterField(lookups=["exact"]),
                "source_model": GraphQLMetaBase.FilterField(lookups=["exact"]),
            },
        )
        fields = GraphQLMetaBase.Fields(
            read_only=[
                "created_at",
                "updated_at",
                "last_materialized_at",
            ]
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "code", "title", "created_at", "updated_at"],
            default=["title"],
        )
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.code})"

    def clean(self) -> None:
        if not self.source_app_label or not self.source_model:
            raise ValidationError(
                "L application et le modele source sont obligatoires."
            )
        try:
            apps.get_model(self.source_app_label, self.source_model)
        except LookupError:
            raise ValidationError(
                f"Impossible de resoudre {self.source_app_label}.{self.source_model}"
            )

    def build_engine(self) -> DatasetExecutionEngine:
        from django.db import connection

        if connection.vendor == "postgresql":
            try:
                from .reporting_psql import PostgresDatasetExecutionEngine

                return PostgresDatasetExecutionEngine(self)
            except ImportError:
                pass
        return DatasetExecutionEngine(self)

    def _runtime_filters(self, filters: Optional[dict]) -> List[FilterSpec]:
        if not filters:
            return []
        if isinstance(filters, dict):
            items = filters.get("items") or filters.get("filters") or []
        else:
            items = filters
        return _to_filter_list(items)

    @action_form(
        title="Previsualiser le dataset",
        description="Execute le dataset avec filtres rapides pour alimenter un tableau ou un graphique.",
        submit_label="Lancer l apercu",
        fields={
            "quick": {"label": "Recherche rapide", "type": "text"},
            "limit": {"label": "Nombre de lignes", "type": "number"},
            "ordering": {
                "label": "Tri",
                "type": "text",
                "help_text": "Expression order_by (ex: -created_at).",
            },
            "filters": {
                "label": "Filtres additionnels",
                "type": "json",
                "help_text": "Liste {field, lookup, value}.",
            },
        },
    )
    def preview(
        self,
        quick: str = "",
        limit: Any = 50,
        ordering: str = "",
        filters: Optional[dict] = None,
    ) -> dict:
        engine = self.build_engine()
        runtime_filters = self._runtime_filters(filters)
        coerced_limit = _coerce_int(limit, default=self.preview_limit)
        result = engine.run(
            runtime_filters=runtime_filters,
            limit=coerced_limit or self.preview_limit,
            ordering=_to_ordering(ordering),
            quick_search=quick,
        )
        return result

    @action_form(
        title="Executer une requete BI",
        description="Moteur dynamique (dimensions, mesures, pivot, having) pour dashboards.",
        submit_label="Executer",
        fields={
            "spec": {
                "label": "Spec JSON",
                "type": "json",
                "help_text": "Spec: {mode, dimensions, metrics, computed_fields, filters, having, ordering, limit, offset, pivot, cache}.",
            }
        },
    )
    def run_query(self, spec: Optional[dict] = None) -> dict:
        engine = self.build_engine()
        return engine.run_query(spec or {})

    @action_form(
        title="Decrire le dataset",
        description="Retourne le semantic layer et (optionnellement) les champs du modele source.",
        submit_label="Decrire",
        fields={
            "include_model_fields": {
                "label": "Inclure champs modele",
                "type": "boolean",
                "help_text": "Active pour builder des filtres/dimensions ad-hoc.",
            }
        },
    )
    def describe(self, include_model_fields: bool = True) -> dict:
        engine = self.build_engine()
        return engine.describe_dataset(include_model_fields=bool(include_model_fields))

    @confirm_action(
        title="Materialiser l apercu",
        message="Capture un snapshot pour reutiliser le dataset hors ligne.",
        confirm_label="Materialiser",
        severity="primary",
    )
    def materialize(self) -> bool:
        engine = self.build_engine()
        snapshot = engine.run(limit=self.preview_limit)
        meta = dict(self.metadata or {})
        meta["materialized_snapshot"] = snapshot
        self.metadata = meta
        self.last_materialized_at = timezone.now()
        self.save(update_fields=["metadata", "last_materialized_at", "updated_at"])
        return True


class ReportingVisualization(models.Model):
    """Visualization attached to a dataset (table, chart, KPI, pivot)."""

    class VisualizationKind(models.TextChoices):
        TABLE = "table", "Tableau"
        BAR = "bar", "Histogramme"
        LINE = "line", "Courbe"
        PIE = "pie", "Camembert"
        KPI = "kpi", "Indicateur"
        AREA = "area", "Aire"
        PIVOT = "pivot", "Pivot"
        HEATMAP = "heatmap", "Heatmap"
        PDF = "pdf", "Export PDF"

    dataset = models.ForeignKey(
        ReportingDataset,
        related_name="visualizations",
        on_delete=models.CASCADE,
        verbose_name="Jeu de donnees",
    )
    code = models.SlugField(max_length=80, verbose_name="Code")
    title = models.CharField(max_length=120, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    kind = models.CharField(
        max_length=30,
        choices=VisualizationKind.choices,
        default=VisualizationKind.TABLE,
        verbose_name="Type",
    )
    config = models.JSONField(
        default=dict,
        verbose_name="Configuration",
        help_text="Axes, colonnes, legende, couleurs.",
    )
    default_filters = models.JSONField(
        default=list,
        verbose_name="Filtres par defaut",
        help_text="Filtres appliques avant l execution.",
    )
    options = models.JSONField(
        default=dict,
        verbose_name="Options UI",
        help_text="Preferences de rendu (theme, animations).",
    )
    is_default = models.BooleanField(
        default=False, verbose_name="Visualisation par defaut"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mise a jour")

    class Meta:
        app_label = "rail_django"
        verbose_name = "Visualisation BI"
        verbose_name_plural = "Visualisations BI"
        ordering = ["dataset__title", "title"]
        unique_together = ("dataset", "code")

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["code", "title", "description"],
            fields={
                "dataset_id": GraphQLMetaBase.FilterField(lookups=["exact"]),
                "kind": GraphQLMetaBase.FilterField(lookups=["exact"]),
            },
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "title", "code", "created_at"],
            default=["title"],
        )
        fields = GraphQLMetaBase.Fields(
            read_only=["created_at", "updated_at"],
        )
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.kind})"

    def _merge_filters(self, runtime_filters: Optional[dict]) -> List[FilterSpec]:
        base = _to_filter_list(self.default_filters)
        merged = base + _to_filter_list(
            runtime_filters.get("filters", runtime_filters) if runtime_filters else []
        )
        return merged

    @action_form(
        title="Rendre la visualisation",
        description="Prepare les donnees et la configuration pour le frontend.",
        submit_label="Executer",
        fields={
            "quick": {"label": "Recherche rapide", "type": "text"},
            "limit": {"label": "Limite", "type": "number"},
            "filters": {"label": "Filtres runtime", "type": "json"},
            "spec": {
                "label": "Spec BI (optionnel)",
                "type": "json",
                "help_text": "Permet de surcharger dimensions/mesures/pivot/having sans modifier la visualisation.",
            },
        },
    )
    def render(
        self,
        quick: str = "",
        limit: Any = 200,
        filters: Optional[dict] = None,
        spec: Optional[dict] = None,
    ) -> dict:
        engine = self.dataset.build_engine()
        merged_filters = self._merge_filters(filters)
        coerced_limit = _coerce_int(limit, default=self.dataset.preview_limit)
        base_spec = {}
        if isinstance(self.config, dict) and isinstance(self.config.get("query"), dict):
            base_spec = dict(self.config.get("query") or {})
        if isinstance(spec, dict):
            base_spec.update(spec)

        runtime_filters_payload = [item.__dict__ for item in merged_filters]
        existing_where = (
            base_spec.get("filters")
            if "filters" in base_spec
            else base_spec.get("where")
        )
        if existing_where and runtime_filters_payload:
            base_spec["filters"] = {
                "op": "and",
                "items": [existing_where, runtime_filters_payload],
            }
        elif runtime_filters_payload:
            base_spec["filters"] = runtime_filters_payload

        base_spec["quick"] = quick
        base_spec["limit"] = coerced_limit or self.dataset.preview_limit
        payload = engine.run_query(base_spec)
        return {
            "visualization": {
                "id": self.id,
                "code": self.code,
                "title": self.title,
                "kind": self.kind,
                "config": self.config,
                "options": self.options,
                "dataset_id": self.dataset_id,
            },
            "dataset": payload,
        }


class ReportingReport(models.Model):
    """Report container aggregating multiple visualizations."""

    code = models.SlugField(unique=True, max_length=80, verbose_name="Code")
    title = models.CharField(max_length=140, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    layout = models.JSONField(
        default=list,
        verbose_name="Layout",
        help_text="Disposition des visualisations {visualization_id, position}.",
    )
    filters = models.JSONField(
        default=list,
        verbose_name="Filtres applicables",
        help_text="Filtres globaux appliques a toutes les visualisations.",
    )
    theme = models.CharField(
        max_length=60, default="light", verbose_name="Theme", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mise a jour")
    visualizations = models.ManyToManyField(
        ReportingVisualization,
        through="ReportingReportBlock",
        related_name="reports",
        verbose_name="Visualisations",
    )

    class Meta:
        app_label = "rail_django"
        verbose_name = "Rapport BI"
        verbose_name_plural = "Rapports BI"
        ordering = ["title"]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["code", "title", "description"],
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "title", "code", "created_at"],
            default=["title"],
        )
        fields = GraphQLMetaBase.Fields(read_only=["created_at", "updated_at"])
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.code})"

    def _resolved_blocks(self) -> List["ReportingReportBlock"]:
        return list(
            self.blocks.select_related("visualization", "visualization__dataset")
        )

    def _render_visualizations(
        self, quick: str, limit: int, filters: Optional[dict]
    ) -> List[dict]:
        rendered: List[dict] = []
        for block in self._resolved_blocks():
            payload = block.visualization.render(
                quick=quick,
                limit=limit,
                filters=filters,
            )
            rendered.append(
                {
                    "block_id": block.id,
                    "visualization": payload["visualization"],
                    "dataset": payload["dataset"],
                    "layout": block.layout,
                }
            )
        return rendered

    @action_form(
        title="Assembler le rapport",
        description="Retourne toutes les visualisations et le layout pour un rendu unique.",
        submit_label="Construire",
        fields={
            "quick": {"label": "Recherche rapide", "type": "text"},
            "limit": {"label": "Limite par visualisation", "type": "number"},
            "filters": {"label": "Filtres globaux", "type": "json"},
        },
    )
    def build_payload(
        self,
        quick: str = "",
        limit: int = 200,
        filters: Optional[dict] = None,
    ) -> dict:
        visualizations = self._render_visualizations(
            quick=quick, limit=limit, filters=filters
        )
        return {
            "report": {
                "code": self.code,
                "title": self.title,
                "description": self.description,
                "layout": self.layout,
                "theme": self.theme,
            },
            "visualizations": visualizations,
            "filters": self.filters,
        }


class ReportingReportBlock(models.Model):
    """Through table used to assign visualizations to a report with layout hints."""

    report = models.ForeignKey(
        ReportingReport,
        related_name="blocks",
        on_delete=models.CASCADE,
        verbose_name="Rapport",
    )
    visualization = models.ForeignKey(
        ReportingVisualization,
        related_name="blocks",
        on_delete=models.CASCADE,
        verbose_name="Visualisation",
    )
    position = models.PositiveIntegerField(default=1, verbose_name="Position")
    layout = models.JSONField(
        default=dict,
        verbose_name="Layout",
        help_text="Coordonnees (x,y,width,height) pour le frontend.",
    )
    title_override = models.CharField(
        max_length=140, blank=True, verbose_name="Titre alternatif"
    )

    class Meta:
        app_label = "rail_django"
        verbose_name = "Bloc de rapport"
        verbose_name_plural = "Blocs de rapport"
        ordering = ["position"]
        unique_together = ("report", "visualization")

    class GraphQLMeta(GraphQLMetaBase):
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "position"],
            default=["position"],
        )

    def __str__(self) -> str:
        return f"{self.report.code} -> {self.visualization.code}"


class ReportingExportJob(models.Model):
    """Tracks export runs (PDF/CSV/JSON) for datasets, visualizations or full reports."""

    class ExportStatus(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        COMPLETED = "completed", "Termine"
        FAILED = "failed", "Echec"

    class ExportFormat(models.TextChoices):
        PDF = "pdf", "PDF"
        CSV = "csv", "CSV"
        JSON = "json", "JSON"
        XLSX = "xlsx", "Excel"

    title = models.CharField(max_length=140, verbose_name="Titre")
    dataset = models.ForeignKey(
        ReportingDataset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="export_jobs",
        verbose_name="Dataset",
    )
    visualization = models.ForeignKey(
        ReportingVisualization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="export_jobs",
        verbose_name="Visualisation",
    )
    report = models.ForeignKey(
        ReportingReport,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="export_jobs",
        verbose_name="Rapport",
    )
    format = models.CharField(
        max_length=10,
        choices=ExportFormat.choices,
        default=ExportFormat.PDF,
        verbose_name="Format",
    )
    status = models.CharField(
        max_length=20,
        choices=ExportStatus.choices,
        default=ExportStatus.PENDING,
        verbose_name="Statut",
    )
    filters = models.JSONField(
        default=dict,
        verbose_name="Filtres",
        help_text="Filtres appliques lors de l export.",
    )
    payload = models.JSONField(
        default=dict,
        verbose_name="Payload",
        help_text="Snapshot utilise par le frontend (donnees et layout).",
    )
    error_message = models.TextField(blank=True, verbose_name="Erreur")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Debut")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Fin")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creation")

    class Meta:
        app_label = "rail_django"
        verbose_name = "Export BI"
        verbose_name_plural = "Exports BI"
        ordering = ["-created_at"]

    class GraphQLMeta(GraphQLMetaBase):
        filtering = GraphQLMetaBase.Filtering(
            quick=["title", "status", "format"],
        )
        ordering = GraphQLMetaBase.Ordering(
            allowed=["id", "created_at", "status", "title"],
            default=["-created_at"],
        )
        fields = GraphQLMetaBase.Fields(read_only=["started_at", "finished_at"])
        access = GraphQLMetaBase.AccessControl(
            roles=_reporting_roles(),
            operations=_reporting_operations(),
        )

    def __str__(self) -> str:
        return f"{self.title} ({self.format})"

    def _build_payload(self) -> dict:
        if self.report:
            return self.report.build_payload(quick="", limit=500, filters=self.filters)
        if self.visualization:
            return self.visualization.render(quick="", limit=500, filters=self.filters)
        if self.dataset:
            return self.dataset.preview(
                quick="",
                limit=self.dataset.preview_limit,
                ordering="",
                filters=self.filters,
            )
        raise ReportingError("Aucune cible d export n est renseignee.")

    @confirm_action(
        title="Lancer l export",
        message="Prepare un payload pour PDF/CSV/JSON.",
        confirm_label="Lancer",
        severity="primary",
    )
    def run_export(self) -> bool:
        self.status = self.ExportStatus.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])
        try:
            self.payload = self._build_payload()
            self.status = self.ExportStatus.COMPLETED
            self.finished_at = timezone.now()
            self.save(update_fields=["payload", "status", "finished_at"])
            return True
        except Exception as exc:  # pragma: no cover - defensive
            self.status = self.ExportStatus.FAILED
            self.error_message = str(exc)
            self.finished_at = timezone.now()
            self.save(
                update_fields=["status", "error_message", "finished_at", "payload"]
            )
            return False


__all__ = [
    "ReportingDataset",
    "ReportingVisualization",
    "ReportingReport",
    "ReportingReportBlock",
    "ReportingExportJob",
    "ReportingError",
    "DatasetExecutionEngine",
]

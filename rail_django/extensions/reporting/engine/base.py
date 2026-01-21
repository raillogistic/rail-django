"""
Base DatasetExecutionEngine class with core initialization and utility methods.

This module contains the foundation of the execution engine including model
loading, configuration access, and field validation methods.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Iterable, Optional

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models

from ..types import (
    ComputedFieldSpec,
    DimensionSpec,
    MetricSpec,
    ReportingError,
    DEFAULT_ALLOWED_LOOKUPS,
    DEFAULT_MAX_LIMIT,
)
from ..utils import _coerce_int, _safe_identifier

if TYPE_CHECKING:
    from ..models.dataset import ReportingDataset

logger = logging.getLogger(__name__)


class DatasetExecutionEngineBase:
    """
    Base class for DatasetExecutionEngine with initialization and utility methods.

    This class handles model loading, configuration parsing, and field validation.
    The full engine is built by combining this base with query building, aggregation,
    and export mixins.
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
        warnings: list[str],
        allowlist: Optional[set[str]] = None,
        label: str = "Champ",
    ) -> list[str]:
        normalized: list[str] = []
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

    def _load_dimensions(self) -> list[DimensionSpec]:
        entries = self.dataset.dimensions or []
        parsed: list[DimensionSpec] = []
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

    def _load_metrics(self) -> list[MetricSpec]:
        entries = self.dataset.metrics or []
        parsed: list[MetricSpec] = []
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

    def _load_computed_fields(self) -> list[ComputedFieldSpec]:
        entries = self.dataset.computed_fields or []
        parsed: list[ComputedFieldSpec] = []
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


__all__ = ["DatasetExecutionEngineBase"]

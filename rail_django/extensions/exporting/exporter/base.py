"""Model Exporter Base

This module provides the base ModelExporter class with core functionality
for field extraction and model loading.
"""

import logging
from typing import Any, Iterable, Optional, Union

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from django.db.models.fields.reverse_related import (
    ManyToManyRel,
    ManyToOneRel,
    OneToOneRel,
)

from ..config import (
    get_export_exclude,
    get_export_fields,
    get_export_settings,
    get_field_formatters,
    get_filterable_fields,
    get_orderable_fields,
    normalize_filter_value,
)
from ..exceptions import ExportError
from .formatters import FieldFormatter

# Import GraphQL filter generator
try:
    from ....generators.filter_inputs import NestedFilterApplicator
except ImportError:
    NestedFilterApplicator = None


class ModelExporterBase:
    """Base class for model export functionality.

    Provides core methods for model loading, field parsing,
    and field value extraction.
    """

    def __init__(
        self,
        app_name: str,
        model_name: str,
        *,
        export_settings: Optional[dict[str, Any]] = None,
        schema_name: Optional[str] = None,
    ):
        """Initialize the exporter with model information.

        Args:
            app_name: Name of the Django app containing the model.
            model_name: Name of the Django model to export.
            export_settings: Optional export configuration override.
            schema_name: Schema name for multi-schema filter support.

        Raises:
            ExportError: If the model cannot be found.
        """
        self.app_name = app_name
        self.model_name = model_name
        self.export_settings = export_settings or get_export_settings()
        self.schema_name = schema_name or app_name or "default"
        self.model = self._load_model()
        self.logger = logging.getLogger(__name__)

        # Settings
        self.allow_callables = bool(self.export_settings.get("allow_callables", False))
        self.allow_dunder_access = bool(
            self.export_settings.get("allow_dunder_access", False)
        )
        self.sanitize_formulas = bool(
            self.export_settings.get("sanitize_formulas", True)
        )
        self.formula_escape_strategy = str(
            self.export_settings.get("formula_escape_strategy", "prefix")
        ).lower()
        self.formula_escape_prefix = str(
            self.export_settings.get("formula_escape_prefix", "'")
        )
        self.sensitive_fields = [
            value.lower()
            for value in (self.export_settings.get("sensitive_fields") or [])
            if str(value).strip()
        ]
        self.export_fields = get_export_fields(self.model, self.export_settings)
        self.export_exclude = get_export_exclude(self.model, self.export_settings)
        self.max_prefetch_depth = self._normalize_max_depth(
            self.export_settings.get("max_prefetch_depth")
        )
        self.filterable_fields = get_filterable_fields(
            self.model, self.export_settings, self.export_fields
        )
        self.orderable_fields = get_orderable_fields(
            self.model, self.export_settings, self.export_fields
        )
        self.filterable_special_fields = [
            value.strip().lower()
            for value in (self.export_settings.get("filterable_special_fields") or [])
            if str(value).strip()
        ]
        self.allowed_filter_lookups = [
            value.strip().lower()
            for value in (self.export_settings.get("allowed_filter_lookups") or [])
            if str(value).strip()
        ]
        self.allowed_filter_transforms = [
            value.strip().lower()
            for value in (self.export_settings.get("allowed_filter_transforms") or [])
            if str(value).strip()
        ]
        self.field_formatters = get_field_formatters(self.model, self.export_settings)

        # Initialize field formatter
        self._formatter = FieldFormatter(
            sanitize_formulas=self.sanitize_formulas,
            formula_escape_strategy=self.formula_escape_strategy,
            formula_escape_prefix=self.formula_escape_prefix,
            field_formatters=self.field_formatters,
        )

        # Initialize GraphQL filter applicator if available
        self.nested_filter_applicator = None
        if NestedFilterApplicator:
            try:
                from ....generators.filter_inputs import get_nested_filter_applicator
                self.nested_filter_applicator = get_nested_filter_applicator(
                    self.schema_name
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize nested filter applicator: {e}"
                )

    def _load_model(self) -> models.Model:
        """Load the Django model dynamically."""
        try:
            return apps.get_model(self.app_name, self.model_name)
        except LookupError as e:
            raise ExportError(
                f"Model '{self.model_name}' not found in app '{self.app_name}': {e}"
            )

    def _normalize_ordering(
        self, ordering: Optional[Union[str, list[str]]]
    ) -> list[str]:
        """Normalize and validate ordering input."""
        if not ordering:
            return []
        if isinstance(ordering, str):
            items = [ordering]
        elif isinstance(ordering, (list, tuple)):
            items = [item for item in ordering if isinstance(item, str) and item]
        else:
            return []

        normalized: list[str] = []
        invalid: list[str] = []
        for item in items:
            desc = item.startswith("-")
            field_name = item[1:] if desc else item
            if not self._is_orderable(field_name):
                invalid.append(item)
                continue
            normalized.append(item)

        if invalid:
            raise ExportError(
                "Ordering not allowed: " + ", ".join(sorted(set(invalid)))
            )
        return normalized

    def _normalize_max_depth(self, value: Any) -> Optional[int]:
        """Normalize a depth limit to a positive int or None."""
        if value is None:
            return None
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _is_orderable(self, field_name: str) -> bool:
        """Check whether a field is allowed for ordering."""
        if not field_name:
            return False
        parts = field_name.replace("__", ".").split(".")
        if any(part.startswith("_") for part in parts):
            return False
        if not self.orderable_fields:
            return True
        normalized = normalize_filter_value(field_name)
        return normalized in self.orderable_fields

    def _resolve_model_field(
        self, model_class: type, field_name: str
    ) -> Optional[models.Field]:
        """Resolve a field or reverse relation on a model."""
        try:
            return model_class._meta.get_field(field_name)
        except FieldDoesNotExist:
            pass
        related_objects = getattr(model_class._meta, "related_objects", [])
        for relation in related_objects:
            if relation.get_accessor_name() == field_name:
                return relation
        return None

    def _collect_related_paths(self, accessors: Iterable[str]) -> dict[str, list[str]]:
        """Collect select_related and prefetch_related paths."""
        select_related: set[str] = set()
        prefetch_related: set[str] = set()

        for accessor in accessors:
            if not accessor:
                continue
            parts = accessor.split(".")
            current_model = self.model
            path_parts: list[str] = []
            prefetch_mode = False
            relation_depth = 0

            for part in parts:
                if part.endswith("()"):
                    break
                field = self._resolve_model_field(current_model, part)
                if not field:
                    break
                path_parts.append(part)

                if isinstance(field, (ForeignKey, OneToOneField)):
                    relation_depth += 1
                    if self.max_prefetch_depth and relation_depth > self.max_prefetch_depth:
                        raise ExportError(
                            f"Max prefetch depth exceeded for accessor '{accessor}'"
                        )
                    if prefetch_mode:
                        prefetch_related.add("__".join(path_parts))
                    else:
                        select_related.add("__".join(path_parts))
                    current_model = field.related_model
                    continue

                if isinstance(
                    field, (ManyToManyField, ManyToOneRel, ManyToManyRel, OneToOneRel)
                ):
                    relation_depth += 1
                    if self.max_prefetch_depth and relation_depth > self.max_prefetch_depth:
                        raise ExportError(
                            f"Max prefetch depth exceeded for accessor '{accessor}'"
                        )
                    prefetch_mode = True
                    prefetch_related.add("__".join(path_parts))
                    related_model = getattr(field, "related_model", None)
                    if related_model:
                        current_model = related_model
                    continue
                break

        return {
            "select_related": sorted(select_related),
            "prefetch_related": sorted(prefetch_related),
        }

    def _apply_related_optimizations(
        self, queryset: models.QuerySet, accessors: Iterable[str]
    ) -> models.QuerySet:
        """Apply select_related/prefetch_related based on accessors."""
        related_paths = self._collect_related_paths(accessors)
        if related_paths["select_related"]:
            queryset = queryset.select_related(*related_paths["select_related"])
        if related_paths["prefetch_related"]:
            queryset = queryset.prefetch_related(*related_paths["prefetch_related"])
        return queryset

    def parse_field_config(
        self, field_config: Union[str, dict[str, str]]
    ) -> dict[str, str]:
        """Parse field configuration to extract accessor and title."""
        if isinstance(field_config, str):
            accessor = field_config
            title = self.get_field_verbose_name(accessor)
            return {"accessor": accessor, "title": title}
        elif isinstance(field_config, dict):
            accessor = field_config.get("accessor", "")
            title = field_config.get("title", accessor)
            return {"accessor": accessor, "title": title}
        else:
            accessor = str(field_config)
            return {"accessor": accessor, "title": accessor}

    def get_field_verbose_name(self, field_path: str) -> str:
        """Get the verbose name for a field path."""
        try:
            parts = field_path.split(".")
            current_model = self.model
            verbose_name = field_path

            for i, part in enumerate(parts):
                try:
                    field = current_model._meta.get_field(part)
                    if i == len(parts) - 1:
                        verbose_name = getattr(field, "verbose_name", part)
                    elif hasattr(field, "related_model"):
                        current_model = field.related_model
                    else:
                        break
                except Exception:
                    verbose_name = part
                    break

            return str(verbose_name).title()
        except Exception as e:
            self.logger.debug(f"Could not get verbose name for {field_path}: {e}")
            return field_path.replace("_", " ").title()

    def get_field_headers(self, fields: list[Union[str, dict[str, str]]]) -> list[str]:
        """Generate column headers for the export."""
        return [self.parse_field_config(f)["title"] for f in fields]

    def get_field_value(self, instance: models.Model, accessor: str) -> Any:
        """Get field value from model instance using accessor path."""
        try:
            parts = accessor.split(".")
            value = instance

            for part in parts:
                if value is None:
                    return None

                if part.endswith("()"):
                    if not self.allow_callables:
                        return None
                    method_name = part[:-2]
                    if not self.allow_dunder_access and method_name.startswith("_"):
                        return None
                    method = getattr(value, method_name, None)
                    if callable(method):
                        value = method()
                    else:
                        return None
                else:
                    if not self.allow_dunder_access and part.startswith("_"):
                        return None
                    if not hasattr(value, part):
                        return None
                    attr = getattr(value, part)
                    if callable(attr):
                        if not self.allow_callables:
                            return None
                        try:
                            value = attr()
                        except Exception:
                            return None
                    else:
                        value = attr

            if hasattr(value, "all"):
                try:
                    items = list(value.all())
                    value = ", ".join(str(item) for item in items) if items else ""
                except Exception:
                    pass

            value = self._formatter.apply_field_formatter(value, accessor)
            return self._formatter.format_value(value)

        except Exception as e:
            self.logger.warning(
                f"Error accessing field '{accessor}' on {instance}: {e}"
            )
            return None

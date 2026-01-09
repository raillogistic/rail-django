"""Django Model Export Functionality

This module provides functionality to export Django model data to Excel or CSV files
through an HTTP endpoint. It supports dynamic model loading, field selection,
filtering, and ordering with GraphQL filter integration.

Features:
- HTTP endpoint for generating downloadable files (JWT protected)
- Support for Excel (.xlsx) and CSV (.csv) formats
- Dynamic model loading by app_name and model_name
- Flexible field selection with nested field access and custom titles
- Advanced filtering using GraphQL filter classes (quick filters, date filters, custom filters)
- Custom ordering support
- Proper error handling and validation

Field Format:
- String format: "field_name" (uses field name as accessor and verbose_name as title)
- Dict format: {"accessor": "field_name", "title": "Custom Title"}

Usage:
    POST /api/export/
    Headers: Authorization: Bearer <jwt_token>
    {
        "app_name": "myapp",
        "model_name": "MyModel",
        "file_extension": "xlsx",
        "filename": "export_data",
        "fields": [
            "title",
            "author.username",
            {"accessor": "slug", "title": "MySlug"}
        ],
        "ordering": ["-created_at"],
        "variables": {
            "status": "active",
            "quick": "search term",
            "published_date_today": true
        }
    }
"""

import csv
import io
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from django.db.models.fields.reverse_related import (
    ManyToManyRel,
    ManyToOneRel,
    OneToOneRel,
)
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from openpyxl.styles import Border, Side

# Import GraphQL filter generator and auth decorators
try:
    from ..generators.filters import AdvancedFilterGenerator
except ImportError:
    AdvancedFilterGenerator = None

try:
    from .auth_decorators import jwt_required
except ImportError:
    jwt_required = None

try:
    from .permissions import OperationType, permission_manager
except ImportError:
    OperationType = None
    permission_manager = None

try:
    from .audit import AuditEventType, log_audit_event
except ImportError:
    AuditEventType = None
    log_audit_event = None

try:
    from ..security.field_permissions import (
        FieldAccessLevel,
        FieldContext,
        field_permission_manager,
    )
except ImportError:
    FieldAccessLevel = None
    FieldContext = None
    field_permission_manager = None

# Optional Excel support
try:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

logger = logging.getLogger(__name__)

EXPORT_DEFAULTS = {
    "max_rows": 5000,
    "stream_csv": True,
    "csv_chunk_size": 1000,
    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30,
    },
    "allowed_models": [],
    "allowed_fields": {},
    "require_model_permissions": True,
    "require_field_permissions": True,
    "required_permissions": [],
}


def _get_export_settings() -> Dict[str, Any]:
    """Return merged export settings with defaults applied."""
    export_settings = getattr(settings, "RAIL_DJANGO_EXPORT", None)
    if export_settings is None:
        export_settings = (
            getattr(settings, "RAIL_DJANGO_GRAPHQL", {}) or {}
        ).get("export_settings", {})

    merged = dict(EXPORT_DEFAULTS)
    if isinstance(export_settings, dict):
        merged.update(export_settings)
        rate_limit_override = export_settings.get("rate_limit")
        rate_limit = dict(EXPORT_DEFAULTS["rate_limit"])
        if isinstance(rate_limit_override, dict):
            rate_limit.update(rate_limit_override)
        merged["rate_limit"] = rate_limit

    return merged


def _model_key_candidates(model: type) -> List[str]:
    """Return possible identifiers for a model."""
    return [
        model._meta.label_lower,
        f"{model._meta.app_label}.{model.__name__}",
        model.__name__,
        model._meta.model_name,
    ]


def _normalize_allowed_list(values: Iterable[Any]) -> List[str]:
    """Normalize allowlist values into lowercase strings."""
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _is_model_allowed(model: type, export_settings: Dict[str, Any]) -> bool:
    """Check if the model is allowed for export."""
    allowed_models = export_settings.get("allowed_models") or []
    if not allowed_models:
        return True

    allowed = set(_normalize_allowed_list(allowed_models))
    return any(key.lower() in allowed for key in _model_key_candidates(model))


def _get_allowed_fields(model: type, export_settings: Dict[str, Any]) -> List[str]:
    """Return the allowed field accessors for a model, if configured."""
    allowed_fields = export_settings.get("allowed_fields") or {}
    if not isinstance(allowed_fields, dict):
        return []

    candidates = {key.lower() for key in _model_key_candidates(model)}
    for key, fields in allowed_fields.items():
        if not key:
            continue
        if str(key).strip().lower() in candidates:
            if isinstance(fields, (list, tuple, set)):
                return [str(field).strip() for field in fields if str(field).strip()]
            return []

    return []


class ExportError(Exception):
    """Custom exception for export-related errors."""

    pass


class ModelExporter:
    """
    Handles the export of Django model data to various formats.

    This class provides methods to dynamically load models, apply GraphQL filters,
    extract field data with flexible field format support, and generate export files.

    Features:
    - Dynamic model loading from app and model names
    - GraphQL filter integration for advanced filtering
    - Flexible field format support (string or dict with accessor/title)
    - Nested field access with proper error handling
    - Method calls and property access on model instances
    - Many-to-many field handling
    """

    def __init__(self, app_name: str, model_name: str):
        """
        Initialize the exporter with model information and GraphQL filter generator.

        Args:
            app_name: Name of the Django app containing the model
            model_name: Name of the Django model to export

        Raises:
            ExportError: If the model cannot be found
        """
        self.app_name = app_name
        self.model_name = model_name
        self.model = self._load_model()
        self.logger = logging.getLogger(__name__)

        # Initialize GraphQL filter generator if available
        self.filter_generator = None
        if AdvancedFilterGenerator:
            try:
                self.filter_generator = AdvancedFilterGenerator()
                self.logger.info("GraphQL filter generator initialized successfully")
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize GraphQL filter generator: {e}"
                )

    def _load_model(self) -> models.Model:
        """
        Load the Django model dynamically.

        Returns:
            The Django model class

        Raises:
            ExportError: If the model cannot be found
        """
        try:
            return apps.get_model(self.app_name, self.model_name)
        except LookupError as e:
            raise ExportError(
                f"Model '{self.model_name}' not found in app '{self.app_name}': {e}"
            )

    def _normalize_ordering(self, ordering: Optional[Union[str, List[str]]]) -> List[str]:
        """Normalize ordering input into a list of field expressions."""
        if not ordering:
            return []
        if isinstance(ordering, str):
            return [ordering]
        if isinstance(ordering, (list, tuple)):
            return [item for item in ordering if isinstance(item, str) and item]
        return []

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

    def _collect_related_paths(self, accessors: Iterable[str]) -> Dict[str, List[str]]:
        """Collect select_related and prefetch_related paths for accessors."""
        select_related: Set[str] = set()
        prefetch_related: Set[str] = set()

        for accessor in accessors:
            if not accessor:
                continue
            parts = accessor.split(".")
            current_model = self.model
            path_parts: List[str] = []
            prefetch_mode = False

            for part in parts:
                if part.endswith("()"):
                    break
                field = self._resolve_model_field(current_model, part)
                if not field:
                    break

                path_parts.append(part)

                if isinstance(field, (ForeignKey, OneToOneField)):
                    if prefetch_mode:
                        prefetch_related.add("__".join(path_parts))
                    else:
                        select_related.add("__".join(path_parts))
                    current_model = field.related_model
                    continue

                if isinstance(field, (ManyToManyField, ManyToOneRel, ManyToManyRel, OneToOneRel)):
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

    def _has_field_access(self, user: Any, accessor: str) -> bool:
        """Check field-level access permissions if configured."""
        if not field_permission_manager or not FieldContext or not FieldAccessLevel:
            return True
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True

        current_model = self.model
        for part in accessor.split("."):
            if part.endswith("()"):
                break
            context = FieldContext(
                user=user,
                field_name=part,
                operation_type="read",
                model_class=current_model,
            )
            access_level = field_permission_manager.get_field_access_level(context)
            if access_level == FieldAccessLevel.NONE:
                return False

            field = self._resolve_model_field(current_model, part)
            related_model = getattr(field, "related_model", None) if field else None
            if related_model:
                current_model = related_model
            else:
                break

        return True

    def validate_fields(
        self,
        fields: List[Union[str, Dict[str, str]]],
        *,
        user: Optional[Any] = None,
        export_settings: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Validate and normalize fields based on allowlist and permissions."""
        export_settings = export_settings or _get_export_settings()
        allowed_fields = _get_allowed_fields(self.model, export_settings)
        require_field_permissions = bool(
            export_settings.get("require_field_permissions", True)
        )

        parsed_fields: List[Dict[str, str]] = []
        denied_fields: List[str] = []

        for field_config in fields:
            parsed_field = self.parse_field_config(field_config)
            accessor = parsed_field.get("accessor", "").strip()
            if not accessor:
                denied_fields.append("<empty>")
                continue

            if allowed_fields:
                base_accessor = accessor.split(".")[0]
                if accessor not in allowed_fields and base_accessor not in allowed_fields:
                    denied_fields.append(accessor)
                    continue

            if (
                user is not None
                and require_field_permissions
                and not self._has_field_access(user, accessor)
            ):
                denied_fields.append(accessor)
                continue

            parsed_fields.append(parsed_field)

        if denied_fields:
            raise ExportError(
                "Export denied for fields: " + ", ".join(sorted(set(denied_fields)))
            )

        if not parsed_fields:
            raise ExportError("No exportable fields were provided")

        return parsed_fields

    def get_queryset(
        self,
        variables: Optional[Dict[str, Any]] = None,
        ordering: Optional[Union[str, List[str]]] = None,
        fields: Optional[Iterable[str]] = None,
        max_rows: Optional[int] = None,
    ) -> models.QuerySet:
        """
        Get the filtered and ordered queryset using GraphQL filters.

        Args:
            variables: Dictionary of filter kwargs (e.g., {'title__icontains': 'test'})
            ordering: Django ORM ordering expression(s)
            fields: Field accessors for select_related/prefetch_related optimization
            max_rows: Optional max rows cap

        Returns:
            Filtered and ordered queryset

        Raises:
            ExportError: If filtering or ordering fails
        """
        try:
            queryset = self.model.objects.all()

            # Apply GraphQL filters
            if variables:
                queryset = self.apply_graphql_filters(queryset, variables)

            # Apply ordering
            ordering_fields = self._normalize_ordering(ordering)
            if ordering_fields:
                queryset = queryset.order_by(*ordering_fields)

            # Apply relation optimizations based on requested fields
            if fields:
                queryset = self._apply_related_optimizations(queryset, fields)

            if max_rows is not None and max_rows > 0:
                queryset = queryset[:max_rows]

            return queryset

        except Exception as e:
            raise ExportError(f"Error building queryset: {e}")

    def apply_graphql_filters(
        self, queryset: models.QuerySet, variables: Dict[str, Any]
    ) -> models.QuerySet:
        """
        Apply GraphQL filters to the queryset using the filter generator.

        Args:
            queryset: Django QuerySet to filter
            variables: Filter parameters from the request

        Returns:
            Filtered QuerySet
        """
        if not variables:
            return queryset

        # Try to use GraphQL filter generator first
        if self.filter_generator:
            try:
                # Use apply_complex_filters to handle complex filter structures (AND/OR/NOT)
                # variables likely contains the 'filters' structure from the frontend
                filter_input = variables.get("filters", variables)
                if filter_input is None:
                    return queryset
                return self.filter_generator.apply_complex_filters(
                    queryset, filter_input
                )

            except Exception as e:
                self.logger.warning(
                    f"GraphQL filtering failed, falling back to basic filtering: {e}"
                )

        # Fall back to basic Django filtering
        try:
            # Clean variables to remove None values and empty strings
            clean_variables = {
                key: value
                for key, value in variables.items()
                if value is not None and value != ""
            }
            if clean_variables:
                return queryset.filter(**clean_variables)
            return queryset
        except Exception as e:
            self.logger.error(f"Basic filtering failed: {e}")
            return queryset

    def get_field_value(self, instance: models.Model, accessor: str) -> Any:
        """
        Get field value from model instance using accessor path.

        Supports:
        - Simple fields: 'title'
        - Nested fields: 'author.username'
        - Method calls: 'get_absolute_url'
        - Many-to-many fields: 'tags' (returns comma-separated list)

        Args:
            instance: Model instance
            accessor: Dot-separated path to the field/attribute

        Returns:
            The field value, properly formatted
        """
        try:
            # Split accessor by dots for nested access
            parts = accessor.split(".")
            value = instance

            for part in parts:
                if value is None:
                    return None

                # Handle method calls (if part ends with parentheses)
                if part.endswith("()"):
                    method_name = part[:-2]
                    if hasattr(value, method_name):
                        method = getattr(value, method_name)
                        if callable(method):
                            value = method()
                        else:
                            value = method
                    else:
                        return None
                else:
                    # Regular attribute access
                    if hasattr(value, part):
                        attr = getattr(value, part)

                        # Handle callable attributes (methods)
                        if callable(attr):
                            try:
                                value = attr()
                            except Exception as e:
                                self.logger.debug(f"Method call failed for {part}: {e}")
                                return None
                        else:
                            value = attr
                    else:
                        return None

            # Handle many-to-many relationships
            if hasattr(value, "all"):
                try:
                    items = list(value.all())
                    if items:
                        return ", ".join(str(item) for item in items)
                    return ""
                except Exception:
                    pass

            return self._format_value(value)

        except Exception as e:
            self.logger.warning(
                f"Error accessing field '{accessor}' on {instance}: {e}"
            )
            return None

    def _format_value(self, value: Any) -> Any:
        """
        Format value for export based on its type.

        Args:
            value: The value to format

        Returns:
            Formatted value suitable for export
        """
        if value is None:
            return ""
        elif isinstance(value, bool):
            return "Yes" if value else "No"
        elif isinstance(value, (datetime, date)):
            if isinstance(value, datetime):
                # Convert timezone-aware datetime to local time
                if timezone.is_aware(value):
                    value = timezone.localtime(value)
                return value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                return value.strftime("%Y-%m-%d")
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, models.Model):
            # For related objects, return string representation
            return str(value)
        elif hasattr(value, "all"):
            # For many-to-many fields, join related objects
            return ", ".join(str(item) for item in value.all())
        else:
            return str(value)

    def parse_field_config(
        self, field_config: Union[str, Dict[str, str]]
    ) -> Dict[str, str]:
        """
        Parse field configuration to extract accessor and title.

        Args:
            field_config: Field configuration (string or dict)

        Returns:
            Dict with 'accessor' and 'title' keys
        """
        if isinstance(field_config, str):
            # String format: use field name as accessor and get verbose name as title
            accessor = field_config
            title = self.get_field_verbose_name(accessor)
            return {"accessor": accessor, "title": title}

        elif isinstance(field_config, dict):
            # Dict format: use provided accessor and title
            accessor = field_config.get("accessor", "")
            title = field_config.get("title", accessor)
            return {"accessor": accessor, "title": title}

        else:
            # Invalid format, use string representation
            accessor = str(field_config)
            title = accessor
            return {"accessor": accessor, "title": title}

    def get_field_verbose_name(self, field_path: str) -> str:
        """
        Get the verbose name for a field path, handling nested fields.

        Args:
            field_path: Field path (e.g., 'title', 'author.username')

        Returns:
            Verbose name of the field
        """
        try:
            parts = field_path.split(".")
            current_model = self.model
            verbose_name = field_path  # Default fallback

            for i, part in enumerate(parts):
                try:
                    field = current_model._meta.get_field(part)

                    if i == len(parts) - 1:  # Last part
                        verbose_name = getattr(field, "verbose_name", part)
                    else:
                        # Navigate to related model
                        if hasattr(field, "related_model"):
                            current_model = field.related_model
                        else:
                            break

                except Exception:
                    # Field not found, use the part name
                    verbose_name = part
                    break

            return str(verbose_name).title()

        except Exception as e:
            self.logger.debug(f"Could not get verbose name for {field_path}: {e}")
            return field_path.replace("_", " ").title()

    def get_field_headers(self, fields: List[Union[str, Dict[str, str]]]) -> List[str]:
        """
        Generate column headers for the export with flexible field format support.

        Args:
            fields: List of field definitions (string or dict format)

        Returns:
            List of column headers
        """
        headers = []

        for field_config in fields:
            parsed_field = self.parse_field_config(field_config)
            headers.append(parsed_field["title"])

        return headers

    def _extract_field_data(self, obj, fields):
        """
        Extract field data from a model instance based on field configurations.

        Args:
            obj: Django model instance
            fields: List of field configurations (string or dict format)

        Returns:
            List of field values for the instance
        """
        row_data = []

        for field_config in fields:
            if isinstance(field_config, str):
                # String format: accessor is the field name
                accessor = field_config
            elif isinstance(field_config, dict):
                # Dict format: get accessor from dict
                accessor = field_config["accessor"]
            else:
                # Invalid format, use empty string
                row_data.append("")
                continue

            try:
                value = self.get_field_value(obj, accessor)
                row_data.append(value)
            except Exception as e:
                # Log error and use empty string as fallback
                logging.getLogger(__name__).warning(
                    f"Error extracting field '{accessor}': {e}"
                )
                row_data.append("")

        return row_data

    def _get_field_headers(self, fields):
        """
        Generate field headers from field configurations.

        Args:
            fields: List of field configurations (string or dict format)

        Returns:
            List of header strings for the export file
        """
        headers = []

        for field_config in fields:
            if isinstance(field_config, str):
                # String format: use verbose_name or field name as title
                accessor = field_config
                title = self._get_verbose_name_for_accessor(accessor)
                headers.append(title)
            elif isinstance(field_config, dict):
                # Dict format: use provided title or fallback to verbose_name
                accessor = field_config["accessor"]
                if "title" in field_config:
                    title = field_config["title"]
                else:
                    title = self._get_verbose_name_for_accessor(accessor)
                headers.append(title)

        return headers

    def _get_verbose_name_for_accessor(self, accessor):
        """
        Get the verbose name for a field accessor, handling nested fields.

        Args:
            accessor: Field accessor string (e.g., 'title', 'author.username')

        Returns:
            String representing the verbose name or field name
        """
        try:
            # Split accessor into parts for nested field access
            parts = accessor.split(".")
            current_model = self.model
            verbose_name = None

            for i, part in enumerate(parts):
                try:
                    field = current_model._meta.get_field(part)

                    if i == len(parts) - 1:
                        # Last part - get verbose name
                        verbose_name = getattr(field, "verbose_name", part)
                        if hasattr(field, "related_model") and field.related_model:
                            # For foreign key fields, might want to include related model info
                            verbose_name = str(verbose_name).title()
                    else:
                        # Intermediate part - move to related model
                        if hasattr(field, "related_model") and field.related_model:
                            current_model = field.related_model
                        else:
                            # Can't traverse further, use remaining parts as fallback
                            remaining_parts = ".".join(parts[i:])
                            verbose_name = remaining_parts.replace("_", " ").title()
                            break

                except FieldDoesNotExist:
                    # Field doesn't exist, might be a method or property
                    # Use the part name as fallback
                    if i == len(parts) - 1:
                        verbose_name = part.replace("_", " ").title()
                    else:
                        # Can't traverse further, use remaining parts as fallback
                        remaining_parts = ".".join(parts[i:])
                        verbose_name = remaining_parts.replace("_", " ").title()
                        break

            return verbose_name or accessor.replace("_", " ").title()

        except Exception:
            # Fallback: use accessor with underscores replaced by spaces
            return accessor.replace("_", " ").title()

    def export_to_csv(
        self,
        fields: List[Union[str, Dict[str, str]]],
        variables: Optional[Dict[str, Any]] = None,
        ordering: Optional[Union[str, List[str]]] = None,
        max_rows: Optional[int] = None,
        parsed_fields: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Export model data to CSV format with flexible field format support.

        Args:
            fields: List of field definitions (string or dict format)
            variables: Filter variables
            ordering: Ordering expression(s)
            max_rows: Optional max rows cap

        Returns:
            CSV content as string
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Parse field configurations
        if parsed_fields is None:
            parsed_fields = []
            for field_config in fields:
                parsed_field = self.parse_field_config(field_config)
                parsed_fields.append(parsed_field)

        # Write headers
        headers = [parsed_field["title"] for parsed_field in parsed_fields]
        writer.writerow(headers)

        # Write data rows
        queryset = self.get_queryset(
            variables,
            ordering,
            fields=[field["accessor"] for field in parsed_fields],
            max_rows=max_rows,
        )

        for instance in queryset.iterator():
            row = []
            for parsed_field in parsed_fields:
                accessor = parsed_field["accessor"]
                value = self.get_field_value(instance, accessor)
                row.append(value)
            writer.writerow(row)

        return output.getvalue()

    def export_to_excel(
        self,
        fields: List[Union[str, Dict[str, str]]],
        variables: Optional[Dict[str, Any]] = None,
        ordering: Optional[Union[str, List[str]]] = None,
        max_rows: Optional[int] = None,
        parsed_fields: Optional[List[Dict[str, str]]] = None,
    ) -> bytes:
        """
        Export model data to Excel format with flexible field format support.

        Args:
            fields: List of field definitions (string or dict format)
            variables: Filter variables
            ordering: Ordering expression(s)
            max_rows: Optional max rows cap

        Returns:
            Excel file content as bytes

        Raises:
            ExportError: If openpyxl is not available
        """
        if not EXCEL_AVAILABLE:
            raise ExportError(
                "Excel export requires openpyxl package. Install with: pip install openpyxl"
            )

        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = f"{self.model_name} Export"

        # Style definitions
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(
            start_color="366092", end_color="366092", fill_type="solid"
        )
        header_alignment = Alignment(horizontal="center", vertical="center")

        # Parse field configurations
        if parsed_fields is None:
            parsed_fields = []
            for field_config in fields:
                parsed_field = self.parse_field_config(field_config)
                parsed_fields.append(parsed_field)

        # Write headers
        headers = [parsed_field["title"] for parsed_field in parsed_fields]
        for col_num, header in enumerate(headers, 1):
            cell = worksheet.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = Border(
                left=Side(border_style="thin"),
                right=Side(border_style="thin"),
                top=Side(border_style="thin"),
                bottom=Side(border_style="thin"),
            )

        # Write data rows
        queryset = self.get_queryset(
            variables,
            ordering,
            fields=[field["accessor"] for field in parsed_fields],
            max_rows=max_rows,
        )

        for row_num, instance in enumerate(queryset.iterator(), 2):
            for col_num, parsed_field in enumerate(parsed_fields, 1):
                accessor = parsed_field["accessor"]
                value = self.get_field_value(instance, accessor)
                worksheet.cell(row=row_num, column=col_num, value=value)

        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)

            for cell in column:
                cell.border = Border(
                    left=Side(border_style="thin"),
                    right=Side(border_style="thin"),
                    top=Side(border_style="thin"),
                    bottom=Side(border_style="thin"),
                )
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass

            adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
            worksheet.column_dimensions[column_letter].width = adjusted_width

        # Save to bytes
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()


@method_decorator(csrf_exempt, name="dispatch")
class ExportView(View):
    """
    Django view for handling model export requests with JWT authentication.

    Accepts POST requests with JSON payload containing export parameters
    and returns downloadable Excel or CSV files. All requests must include
    a valid JWT token in the Authorization header.

    Authentication:
        Requires JWT token: Authorization: Bearer <token>

    Field Format Examples:
    - String: "title" (uses field name as accessor and verbose_name as title)
    - Dict: {"accessor": "author.username", "title": "Author Name"}

    Filter Examples:
    - Basic: {"status": "active", "is_published": true}
    - Quick search: {"quick": "search term"}
    - Date filters: {"created_date_today": true, "updated_date_this_week": true}
    - Custom filters: {"has_tags": true, "content_length": "medium"}
    """

    @method_decorator(jwt_required if jwt_required else lambda f: f)
    def post(self, request):
        """
        Handle POST request for model export (JWT protected).

        Expected JSON payload:
        {
            "app_name": "blog",
            "model_name": "Post",
            "file_extension": "xlsx",  // or "csv"
            "filename": "posts_export",  // optional
            "fields": [
                "title",
                "author.username",
                {"accessor": "slug", "title": "MySlug"}
            ],
            "ordering": ["-created_at"],  // optional list
            "variables": {  // optional GraphQL filter parameters
                "status": "active",
                "quick": "search term",
                "published_date_today": true
            }
        }

        Returns:
            HttpResponse with file download or JsonResponse with error
        """
        # Log authenticated user for audit purposes
        if hasattr(request, "user") and request.user.is_authenticated:
            logger.info(
                f"Export request from user: {request.user.username} (ID: {request.user.id})"
            )

        audit_details = {"action": "export"}

        try:
            export_settings = _get_export_settings()
            rate_limit_response = self._check_rate_limit(request, export_settings)
            if rate_limit_response is not None:
                self._log_export_event(
                    request,
                    success=False,
                    error_message="Rate limit exceeded",
                    details=audit_details,
                )
                return rate_limit_response

            # Parse JSON payload
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                self._log_export_event(
                    request,
                    success=False,
                    error_message="Invalid JSON payload",
                    details=audit_details,
                )
                return JsonResponse({"error": "Invalid JSON payload"}, status=400)

            # Validate required parameters
            required_fields = ["app_name", "model_name", "file_extension", "fields"]
            for field in required_fields:
                if field not in data:
                    self._log_export_event(
                        request,
                        success=False,
                        error_message=f"Missing required field: {field}",
                        details=audit_details,
                    )
                    return JsonResponse(
                        {"error": f"Missing required field: {field}"}, status=400
                    )

            app_name = data["app_name"]
            model_name = data["model_name"]
            file_extension = data["file_extension"].lower()
            fields = data["fields"]
            audit_details.update(
                {
                    "app_name": app_name,
                    "model_name": model_name,
                    "file_extension": file_extension,
                }
            )

            # Validate file extension
            if file_extension in ["excel", "xlsx"]:
                file_extension = "xlsx"
            if file_extension not in ["xlsx", "csv"]:
                self._log_export_event(
                    request,
                    success=False,
                    error_message='file_extension must be "xlsx" or "csv"',
                    details=audit_details,
                )
                return JsonResponse(
                    {"error": 'file_extension must be "xlsx" or "csv"'}, status=400
                )
            audit_details["file_extension"] = file_extension

            # Validate fields format
            if not isinstance(fields, list) or not fields:
                self._log_export_event(
                    request,
                    success=False,
                    error_message="fields must be a non-empty list",
                    details=audit_details,
                )
                return JsonResponse(
                    {"error": "fields must be a non-empty list"}, status=400
                )
            audit_details["fields_count"] = len(fields)

            # Validate field configurations
            for i, field_config in enumerate(fields):
                if isinstance(field_config, str):
                    continue  # String format is valid
                elif isinstance(field_config, dict):
                    if "accessor" not in field_config:
                        self._log_export_event(
                            request,
                            success=False,
                            error_message="Invalid field configuration",
                            details=audit_details,
                        )
                        return JsonResponse(
                            {
                                "error": f"Invalid field configuration at index {i}: dict format must contain 'accessor' key"
                            },
                            status=400,
                        )
                else:
                    self._log_export_event(
                        request,
                        success=False,
                        error_message="Invalid field configuration",
                        details=audit_details,
                    )
                    return JsonResponse(
                        {
                            "error": f"Invalid field configuration at index {i}: field must be string or dict with accessor/title"
                        },
                        status=400,
                    )

            # Optional parameters
            filename = data.get("filename")
            ordering = data.get("ordering")
            variables = data.get("variables") or {}

            if not isinstance(variables, dict):
                self._log_export_event(
                    request,
                    success=False,
                    error_message="variables must be an object of filter parameters",
                    details=audit_details,
                )
                return JsonResponse(
                    {"error": "variables must be an object of filter parameters"},
                    status=400,
                )

            max_rows, max_rows_error = self._resolve_max_rows(data, export_settings)
            if max_rows_error is not None:
                self._log_export_event(
                    request,
                    success=False,
                    error_message="Invalid max_rows",
                    details=audit_details,
                )
                return max_rows_error
            audit_details["max_rows"] = max_rows

            # Generate default filename if not provided
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{model_name}_{timestamp}"

            # Create exporter and generate file
            exporter = ModelExporter(app_name, model_name)
            permission_response = self._enforce_model_permissions(
                request, exporter.model, export_settings
            )
            if permission_response is not None:
                audit_details["model_label"] = exporter.model._meta.label
                self._log_export_event(
                    request,
                    success=False,
                    error_message="Export not permitted",
                    details=audit_details,
                )
                return permission_response

            parsed_fields = exporter.validate_fields(
                fields, user=getattr(request, "user", None), export_settings=export_settings
            )
            ordering_fields = exporter._normalize_ordering(ordering)
            ordering_value = ordering_fields or None

            if file_extension == "xlsx":
                content = exporter.export_to_excel(
                    fields,
                    variables,
                    ordering_value,
                    max_rows=max_rows,
                    parsed_fields=parsed_fields,
                )
                content_type = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                file_ext = "xlsx"
            else:  # csv
                if export_settings.get("stream_csv", True):
                    audit_details["stream_csv"] = True
                    self._log_export_event(
                        request,
                        success=True,
                        details=audit_details,
                    )
                    return self._stream_csv_response(
                        exporter=exporter,
                        parsed_fields=parsed_fields,
                        variables=variables,
                        ordering=ordering_value,
                        max_rows=max_rows,
                        filename=filename,
                        chunk_size=int(export_settings.get("csv_chunk_size", 1000)),
                    )
                content = exporter.export_to_csv(
                    fields,
                    variables,
                    ordering_value,
                    max_rows=max_rows,
                    parsed_fields=parsed_fields,
                )
                content_type = "text/csv; charset=utf-8"
                file_ext = "csv"
                audit_details["stream_csv"] = False

            # Create HTTP response with file download
            response = HttpResponse(content, content_type=content_type)
            response["Content-Disposition"] = (
                f'attachment; filename="{filename}.{file_ext}"'
            )
            response["Content-Length"] = len(content)

            logger.info(
                f"Successfully exported {model_name} data to {file_extension} format"
            )
            self._log_export_event(
                request,
                success=True,
                details=audit_details,
            )
            return response

        except ExportError as e:
            logger.error(f"Export error: {e}")
            message = str(e)
            status = 403 if "denied" in message.lower() else 400
            self._log_export_event(
                request,
                success=False,
                error_message=message,
                details=audit_details,
            )
            return JsonResponse({"error": message}, status=status)
        except Exception as e:
            logger.error(f"Unexpected error during export: {e}")
            self._log_export_event(
                request,
                success=False,
                error_message="Internal server error",
                details=audit_details,
            )
            return JsonResponse({"error": "Internal server error"}, status=500)

    def _log_export_event(
        self,
        request: Any,
        *,
        success: bool,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an audit event for export activity."""
        if not log_audit_event or not AuditEventType:
            return

        audit_details = {"action": "export"}
        if details:
            audit_details.update(details)

        log_audit_event(
            request,
            AuditEventType.DATA_ACCESS,
            success=success,
            error_message=error_message,
            additional_data=audit_details,
        )

    def _get_rate_limit_identifier(self, request) -> str:
        """Resolve the rate limit identifier for the request."""
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return f"user:{user.id}"

        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR", "unknown")

        return f"ip:{ip_address}"

    def _check_rate_limit(
        self, request: Any, export_settings: Dict[str, Any]
    ) -> Optional[JsonResponse]:
        """Apply a basic rate limit using Django cache."""
        config = export_settings.get("rate_limit") or {}
        if not config.get("enable", True):
            return None

        window_seconds = int(config.get("window_seconds", 60))
        max_requests = int(config.get("max_requests", 30))
        identifier = self._get_rate_limit_identifier(request)
        cache_key = f"rail:export_rl:{identifier}"

        count = cache.get(cache_key)
        if count is None:
            cache.add(cache_key, 1, timeout=window_seconds)
            return None

        if int(count) >= max_requests:
            return JsonResponse(
                {"error": "Rate limit exceeded", "retry_after": window_seconds},
                status=429,
            )

        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, int(count) + 1, timeout=window_seconds)
        return None

    def _resolve_max_rows(
        self, data: Dict[str, Any], export_settings: Dict[str, Any]
    ) -> Tuple[Optional[int], Optional[JsonResponse]]:
        """Resolve max rows with request override and config cap."""
        config_max_rows = export_settings.get("max_rows", None)
        requested_max = data.get("max_rows", data.get("limit"))

        if config_max_rows is not None:
            try:
                config_max_rows = int(config_max_rows)
            except (TypeError, ValueError):
                config_max_rows = None
        if config_max_rows is not None and config_max_rows <= 0:
            config_max_rows = None

        if requested_max is None:
            return config_max_rows, None

        try:
            requested_max = int(requested_max)
        except (TypeError, ValueError):
            return None, JsonResponse(
                {"error": "max_rows must be an integer"}, status=400
            )

        if requested_max <= 0:
            return config_max_rows, None

        if config_max_rows is None:
            return requested_max, None

        return min(requested_max, config_max_rows), None

    def _enforce_model_permissions(
        self, request: Any, model: type, export_settings: Dict[str, Any]
    ) -> Optional[JsonResponse]:
        """Check model allowlist and permissions."""
        if not _is_model_allowed(model, export_settings):
            return JsonResponse(
                {"error": "Model export not allowed", "model": model._meta.label},
                status=403,
            )

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return JsonResponse(
                {"error": "Authentication required for export"}, status=401
            )

        if not export_settings.get("require_model_permissions", True):
            return None

        if getattr(user, "is_superuser", False):
            return None

        required_permissions = export_settings.get("required_permissions") or []
        if required_permissions:
            if not any(user.has_perm(perm) for perm in required_permissions):
                return JsonResponse(
                    {"error": "Insufficient permissions for export"}, status=403
                )
            return None

        if permission_manager and OperationType:
            result = permission_manager.check_operation_permission(
                user, model._meta.label_lower, OperationType.READ
            )
            if not result.allowed:
                return JsonResponse(
                    {
                        "error": "Insufficient permissions for export",
                        "detail": result.reason,
                    },
                    status=403,
                )

        view_perm = f"{model._meta.app_label}.view_{model._meta.model_name}"
        if not user.has_perm(view_perm):
            return JsonResponse(
                {"error": "Insufficient permissions for export"}, status=403
            )

        return None

    def _stream_csv_response(
        self,
        *,
        exporter: ModelExporter,
        parsed_fields: List[Dict[str, str]],
        variables: Dict[str, Any],
        ordering: Optional[Union[str, List[str]]],
        max_rows: Optional[int],
        filename: str,
        chunk_size: int,
    ) -> StreamingHttpResponse:
        """Stream a CSV export response."""
        headers = [field["title"] for field in parsed_fields]
        accessors = [field["accessor"] for field in parsed_fields]

        if chunk_size <= 0:
            chunk_size = 1000

        queryset = exporter.get_queryset(
            variables,
            ordering,
            fields=accessors,
            max_rows=max_rows,
        ).iterator(chunk_size=chunk_size)

        def row_generator():
            output = io.StringIO()
            writer = csv.writer(output)

            writer.writerow(headers)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            for instance in queryset:
                row = [exporter.get_field_value(instance, accessor) for accessor in accessors]
                writer.writerow(row)
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

        response = StreamingHttpResponse(
            row_generator(), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        return response

    @method_decorator(jwt_required if jwt_required else lambda f: f)
    def get(self, request):
        """
        Handle GET request - return API documentation (JWT protected).
        """
        # Log authenticated user for audit purposes
        if hasattr(request, "user") and request.user.is_authenticated:
            logger.info(
                f"Export API documentation request from user: {request.user.username}"
            )

        documentation = {
            "endpoint": "/export",
            "method": "POST",
            "authentication": "JWT token required in Authorization header",
            "description": "Export Django model data to Excel or CSV format with GraphQL filter integration",
            "required_headers": {
                "Authorization": "Bearer <jwt_token>",
                "Content-Type": "application/json",
            },
            "required_parameters": {
                "app_name": "string - Name of the Django app containing the model",
                "model_name": "string - Name of the Django model to export",
                "file_extension": 'string - Either "xlsx" or "csv"',
                "fields": "array - List of field configurations (string or dict format)",
            },
            "optional_parameters": {
                "filename": "string - Custom filename (default: ModelName_timestamp)",
                "ordering": "array - List of Django ORM ordering expressions",
                "variables": "object - GraphQL filter parameters",
                "max_rows": "integer - Optional cap for rows exported (bounded by server settings)",
            },
            "field_formats": {
                "string": "Uses field name as accessor and verbose_name as title",
                "dict": "Must contain 'accessor' key, optionally 'title' key",
            },
            "filter_examples": {
                "basic": {"status": "active", "is_published": True},
                "quick_search": {"quick": "search term"},
                "date_filters": {
                    "created_date_today": True,
                    "updated_date_this_week": True,
                },
                "custom_filters": {"has_tags": True, "content_length": "medium"},
            },
            "example_request": {
                "url": "/api/export/",
                "method": "POST",
                "headers": {
                    "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                    "Content-Type": "application/json",
                },
                "payload": {
                    "app_name": "blog",
                    "model_name": "Post",
                    "file_extension": "xlsx",
                    "filename": "blog_posts_export",
                    "fields": [
                        "title",
                        "author.username",
                        {"accessor": "slug", "title": "MySlug"},
                    ],
                    "ordering": ["-created_at"],
                    "variables": {
                        "status": "active",
                        "quick": "search term",
                        "published_date_today": True,
                    },
                },
            },
            "authentication_errors": {
                "401": "Missing or invalid JWT token",
                "403": "Token valid but insufficient permissions",
            },
        }

        return JsonResponse(documentation, json_dumps_params={"indent": 2})


# URL configuration helper
def get_export_urls():
    """
    Helper function to get URL patterns for the export functionality.

    Usage in urls.py:
        from rail_django.extensions.exporting import get_export_urls

        urlpatterns = [
            # ... other patterns
        ] + get_export_urls()

    Returns:
        List of URL patterns
    """
    from django.urls import path

    return [
        path("export/", ExportView.as_view(), name="model_export"),
    ]


# Utility functions for programmatic use
def export_model_to_csv(
    app_name: str,
    model_name: str,
    fields: List[Union[str, Dict[str, str]]],
    variables: Optional[Dict[str, Any]] = None,
    ordering: Optional[Union[str, List[str]]] = None,
) -> str:
    """
    Programmatically export model data to CSV format with flexible field format support.

    Args:
        app_name: Name of the Django app
        model_name: Name of the model
        fields: List of field definitions (string or dict format)
        variables: Filter variables
        ordering: Ordering expression

    Returns:
        CSV content as string
    """
    exporter = ModelExporter(app_name, model_name)
    return exporter.export_to_csv(fields, variables, ordering)


def export_model_to_excel(
    app_name: str,
    model_name: str,
    fields: List[Union[str, Dict[str, str]]],
    variables: Optional[Dict[str, Any]] = None,
    ordering: Optional[Union[str, List[str]]] = None,
) -> bytes:
    """
    Programmatically export model data to Excel format with flexible field format support.

    Args:
        app_name: Name of the Django app
        model_name: Name of the model
        fields: List of field definitions (string or dict format)
        variables: Filter variables
        ordering: Ordering expression

    Returns:
        Excel file content as bytes
    """
    exporter = ModelExporter(app_name, model_name)
    return exporter.export_to_excel(fields, variables, ordering)

"""Field Validation Utilities

This module provides field validation functionality for the model exporter.
"""

from typing import Any, Iterable, List, Optional, Union

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
    normalize_accessor_value,
)
from ..exceptions import ExportError

# Import field permissions
try:
    from ....security.field_permissions import (
        FieldAccessLevel,
        FieldContext,
        field_permission_manager,
    )
except ImportError:
    FieldAccessLevel = None
    FieldContext = None
    field_permission_manager = None


class ValidationMixin:
    """Mixin providing field validation functionality."""

    def _has_field_access(self, user: Any, accessor: str) -> bool:
        """Check field-level access permissions if configured.

        Args:
            user: User object to check permissions for.
            accessor: Field accessor path.

        Returns:
            True if access is allowed, False otherwise.
        """
        if not field_permission_manager or not FieldContext or not FieldAccessLevel:
            return True
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True

        current_model = self.model
        for part in accessor.split("."):
            if part.endswith("()"):
                return False
            if not self.allow_dunder_access and part.startswith("_"):
                return False
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

    def _validate_accessor(
        self,
        accessor: str,
        export_fields: list[str],
        export_exclude: list[str],
        sensitive_fields: list[str],
        require_export_fields: bool,
    ) -> Optional[str]:
        """Validate accessor syntax and model traversal.

        Args:
            accessor: Field accessor to validate.
            export_fields: List of allowed export fields.
            export_exclude: List of excluded fields.
            sensitive_fields: List of sensitive field names.
            require_export_fields: Whether export_fields are required.

        Returns:
            Error message string if validation fails, None if valid.
        """
        if "__" in accessor:
            return "Accessors must use dot notation"
        normalized = normalize_accessor_value(accessor)
        if not normalized:
            return "Empty accessor"
        if normalized in export_exclude:
            return "Accessor is explicitly excluded"
        if export_fields and normalized not in export_fields:
            return "Accessor is not allowlisted"

        parts = accessor.split(".")
        for part in parts:
            if not part:
                return "Accessor contains empty path segments"
            if not self.allow_dunder_access and part.startswith("_"):
                return "Accessor uses a private field"
            if part.endswith("()") and not self.allow_callables:
                return "Callable accessors are disabled"
            if part.endswith("()") and part[:-2].startswith("_"):
                return "Accessor uses a private field"

        if sensitive_fields:
            for part in parts:
                if part.lower() in sensitive_fields:
                    return "Accessor matches a sensitive field"

        current_model = self.model
        relation_depth = 0

        for index, part in enumerate(parts):
            is_last = index == len(parts) - 1
            part_name = part[:-2] if part.endswith("()") else part
            if part.endswith("()") and not is_last:
                return "Callable accessors cannot be chained"
            field = self._resolve_model_field(current_model, part_name)

            if field is None:
                if not is_last:
                    return "Accessor cannot traverse non-relational field"
                attr = getattr(current_model, part_name, None)
                if callable(attr) and not self.allow_callables:
                    return "Callable accessors are disabled"
                return None

            is_relation = isinstance(
                field,
                (
                    ForeignKey,
                    OneToOneField,
                    ManyToManyField,
                    ManyToOneRel,
                    ManyToManyRel,
                    OneToOneRel,
                ),
            )
            if is_relation:
                relation_depth += 1
                if self.max_prefetch_depth and relation_depth > self.max_prefetch_depth:
                    return "Accessor exceeds max relationship depth"
                related_model = getattr(field, "related_model", None)
                if related_model and not is_last:
                    current_model = related_model
                    continue
                if not is_last:
                    return "Accessor cannot traverse non-relational field"
                return None

            if not is_last:
                return "Accessor cannot traverse non-relational field"

        return None

    def validate_fields(
        self,
        fields: list[Union[str, dict[str, str]]],
        *,
        user: Optional[Any] = None,
        export_settings: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, str]]:
        """Validate and normalize fields based on allowlist and permissions.

        Args:
            fields: List of field configurations.
            user: Optional user for permission checking.
            export_settings: Optional export settings override.

        Returns:
            List of validated and normalized field dictionaries.

        Raises:
            ExportError: If any fields are denied or no valid fields provided.
        """
        export_settings = export_settings or self.export_settings
        export_fields = get_export_fields(self.model, export_settings)
        export_exclude = get_export_exclude(self.model, export_settings)
        sensitive_fields = [
            value.lower()
            for value in (export_settings.get("sensitive_fields") or [])
            if str(value).strip()
        ]
        require_export_fields = bool(export_settings.get("require_export_fields", True))
        require_field_permissions = bool(
            export_settings.get("require_field_permissions", True)
        )

        if require_export_fields and not export_fields:
            raise ExportError(
                f"Export denied: schema is not configured for model {self.model._meta.label}"
            )

        parsed_fields: list[dict[str, str]] = []
        denied_fields: list[str] = []

        for field_config in fields:
            parsed_field = self.parse_field_config(field_config)
            accessor = parsed_field.get("accessor", "").strip()
            if not accessor:
                denied_fields.append("<empty>")
                continue

            error = self._validate_accessor(
                accessor,
                export_fields,
                export_exclude,
                sensitive_fields,
                require_export_fields,
            )
            if error:
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

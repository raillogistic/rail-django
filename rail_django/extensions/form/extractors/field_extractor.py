"""
Field extraction for Form API.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from django.db import models

from ....security.field_permissions import FieldVisibility, field_permission_manager
from ..utils.type_mapping import map_field_input_type, map_graphql_type, map_python_type


class FieldExtractorMixin:
    """Mixin for extracting field configurations."""

    def _to_json_value(self, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "__json__"):
            try:
                return self._to_json_value(value.__json__())
            except Exception:
                return str(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return value.hex()
        if isinstance(value, set):
            return [self._to_json_value(v) for v in sorted(value, key=str)]
        if isinstance(value, (list, tuple)):
            return [self._to_json_value(v) for v in value]
        if isinstance(value, dict):
            return {str(k): self._to_json_value(v) for k, v in value.items()}
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    def _extract_fields(
        self,
        model: type[models.Model],
        user: Any,
        *,
        instance: Optional[models.Model] = None,
        graphql_meta: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        field_metadata = getattr(graphql_meta, "field_metadata", None) or {}
        fields: list[dict[str, Any]] = []
        for field in model._meta.get_fields():
            if field.is_relation:
                continue
            if not hasattr(field, "name"):
                continue
            field_schema = self._extract_field(
                model,
                field,
                user,
                instance=instance,
                field_metadata=field_metadata.get(field.name),
            )
            if field_schema:
                fields.append(field_schema)
        return fields

    def _extract_field(
        self,
        model: type[models.Model],
        field: models.Field,
        user: Any,
        *,
        instance: Optional[models.Model] = None,
        field_metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        try:
            from graphene.utils.str_converters import to_camel_case

            readable, writable, visibility = True, True, "VISIBLE"
            if user:
                try:
                    perm = field_permission_manager.check_field_permission(
                        user, model, field.name, instance=None
                    )
                    readable = perm.visibility != FieldVisibility.HIDDEN
                    writable = perm.can_write
                    visibility = (
                        perm.visibility.name
                        if hasattr(perm.visibility, "name")
                        else "VISIBLE"
                    )
                except Exception:
                    pass

            choices = None
            if getattr(field, "choices", None):
                choices = [
                    {"value": str(choice[0]), "label": str(choice[1])}
                    for choice in field.choices
                ]

            default_value = None
            has_default = field.has_default()
            if has_default and not callable(field.default):
                try:
                    default_value = self._to_json_value(field.default)
                except Exception:
                    default_value = str(field.default)

            validators = []
            for validator in getattr(field, "validators", []):
                params: dict[str, Any] = {}
                if hasattr(validator, "limit_value"):
                    params["limit_value"] = self._to_json_value(validator.limit_value)
                if hasattr(validator, "regex"):
                    if hasattr(validator.regex, "pattern"):
                        params["pattern"] = validator.regex.pattern
                    elif isinstance(validator.regex, str):
                        params["pattern"] = validator.regex
                    if hasattr(validator.regex, "flags"):
                        params["flags"] = validator.regex.flags

                message = getattr(validator, "message", None)
                validators.append(
                    {
                        "type": type(validator).__name__,
                        "params": params or None,
                        "message": str(message) if message else None,
                        "async_field": False,
                    }
                )

            custom_metadata = (
                self._to_json_value(field_metadata)
                if field_metadata is not None
                else None
            )

            upload_config = None
            if type(field).__name__ in ("FileField", "ImageField"):
                upload_config = {
                    "strategy": "GRAPHQL_UPLOAD",
                    "allowed_extensions": None,
                    "max_file_size": None,
                    "max_files": 1,
                    "direct_upload_url": None,
                }

            return {
                "name": to_camel_case(field.name),
                "field_name": field.name,
                "label": str(getattr(field, "verbose_name", field.name)),
                "description": str(getattr(field, "help_text", "") or "") or None,
                "input_type": map_field_input_type(field),
                "graphql_type": map_graphql_type(field),
                "python_type": map_python_type(field),
                "required": not field.blank and not field.null,
                "nullable": bool(field.null),
                "read_only": not bool(field.editable),
                "disabled": False,
                "hidden": visibility == "HIDDEN",
                "constraints": {
                    "max_length": getattr(field, "max_length", None),
                    "min_length": getattr(field, "min_length", None),
                    "max_value": getattr(field, "max_value", None),
                    "min_value": getattr(field, "min_value", None),
                    "pattern": None,
                    "pattern_message": None,
                    "decimal_places": getattr(field, "decimal_places", None),
                    "max_digits": getattr(field, "max_digits", None),
                    "allowed_extensions": None,
                    "max_file_size": None,
                },
                "choices": choices,
                "default_value": default_value,
                "has_default": bool(has_default),
                "validators": validators,
                "placeholder": None,
                "help_text": str(getattr(field, "help_text", "") or "") or None,
                "order": None,
                "col_span": None,
                "input_props": None,
                "metadata": custom_metadata,
                "upload_config": upload_config,
                "readable": readable,
                "writable": writable,
            }
        except Exception:
            return None

"""
Field extraction for Form API.

@module rail_django.extensions.form.extractors.field_extractor
@description Extrait les configurations et les métadonnées des champs de modèle Django pour l'API Form.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from django.db import models

from ....security.field_permissions import FieldVisibility, field_permission_manager
from ....utils.history_detection import is_historical_records_attribute
from ..utils.type_mapping import map_field_input_type, map_graphql_type, map_python_type

logger = logging.getLogger(__name__)


def _resolve_permission_operation_type(mode: str) -> str:
    normalized = str(mode or "").strip().upper()
    if normalized == "CREATE":
        return "create"
    if normalized == "VIEW":
        return "view"
    return "update"


def _check_field_permission_compat(
    user: Any,
    model: type[models.Model],
    field_name: str,
    *,
    instance: Optional[models.Model] = None,
    operation_type: str,
) -> Any:
    try:
        return field_permission_manager.check_field_permission(
            user,
            model,
            field_name,
            instance=instance,
            operation_type=operation_type,
        )
    except TypeError as exc:
        if "operation_type" not in str(exc):
            raise
        return field_permission_manager.check_field_permission(
            user,
            model,
            field_name,
            instance=instance,
        )


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
        mode: str = "CREATE",
    ) -> list[dict[str, Any]]:
        field_metadata = getattr(graphql_meta, "field_metadata", None) or {}
        fields: list[dict[str, Any]] = []
        for field in model._meta.get_fields():
            if field.is_relation:
                continue
            if not hasattr(field, "name"):
                continue
            if is_historical_records_attribute(model, field.name):
                continue
            if graphql_meta is not None:
                try:
                    if not graphql_meta.should_expose_field(
                        field.name, for_input=True
                    ):
                        continue
                except Exception:
                    logger.debug(
                        "Failed to apply GraphQLMeta field exposure rule for %s.%s.",
                        model._meta.label,
                        field.name,
                    )
            field_schema = self._extract_field(
                model,
                field,
                user,
                instance=instance,
                field_metadata=field_metadata.get(field.name),
                mode=mode,
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
        mode: str = "CREATE",
    ) -> Optional[dict[str, Any]]:
        """
        Extrait les métadonnées et contraintes d'un champ spécifique d'un modèle Django.

        @param model Le modèle Django parent.
        @param field Le champ Django à extraire.
        @param user L'utilisateur actuel pour le calcul des permissions.
        @param instance L'instance spécifique du modèle.
        @param field_metadata Métadonnées spécifiques au champ.
        @param mode Mode du formulaire (CREATE, UPDATE, VIEW).
        @returns Un dictionnaire représentant le schéma du champ, ou None.
        """
        try:
            from graphene.utils.str_converters import to_camel_case

            readable, writable, visibility = True, True, "VISIBLE"
            if user:
                try:
                    perm = _check_field_permission_compat(
                        user,
                        model,
                        field.name,
                        instance=instance,
                        operation_type=_resolve_permission_operation_type(mode),
                    )
                    readable = perm.visibility != FieldVisibility.HIDDEN
                    writable = perm.can_write
                    visibility = (
                        perm.visibility.name
                        if hasattr(perm.visibility, "name")
                        else "VISIBLE"
                    )
                except Exception:
                    readable, writable, visibility = False, False, "HIDDEN"

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

            # Extraction des contraintes à partir des validateurs et attributs du champ
            max_length = getattr(field, "max_length", None)
            min_length = getattr(field, "min_length", None)
            max_value = getattr(field, "max_value", None)
            min_value = getattr(field, "min_value", None)
            pattern = None
            pattern_message = None
            allowed_extensions = None

            validators = []
            for validator in getattr(field, "validators", []):
                params: dict[str, Any] = {}
                val_name = type(validator).__name__

                # Extraction intelligente des limites depuis les validateurs
                if val_name == "MinValueValidator" and hasattr(validator, "limit_value"):
                    min_value = validator.limit_value
                elif val_name == "MaxValueValidator" and hasattr(validator, "limit_value"):
                    max_value = validator.limit_value
                elif val_name == "MinLengthValidator" and hasattr(validator, "limit_value"):
                    min_length = validator.limit_value
                elif val_name == "MaxLengthValidator" and hasattr(validator, "limit_value"):
                    max_length = validator.limit_value
                elif val_name == "RegexValidator" and hasattr(validator, "regex"):
                    if hasattr(validator.regex, "pattern"):
                        pattern = validator.regex.pattern
                    elif isinstance(validator.regex, str):
                        pattern = validator.regex
                    pattern_message = getattr(validator, "message", None)
                elif val_name == "FileExtensionValidator" and hasattr(validator, "allowed_extensions"):
                    allowed_extensions = validator.allowed_extensions

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
                        "type": val_name,
                        "params": params or None,
                        "message": str(message) if message else None,
                        "async_field": False,
                    }
                )

            def _to_float(val: Any) -> Optional[float]:
                if val is None:
                    return None
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None

            custom_metadata = (
                self._to_json_value(field_metadata)
                if field_metadata is not None
                else None
            )

            upload_config = None
            if type(field).__name__ in ("FileField", "ImageField"):
                upload_config = {
                    "strategy": "GRAPHQL_UPLOAD",
                    "allowed_extensions": self._to_json_value(allowed_extensions),
                    "max_file_size": getattr(field, "max_file_size", None),
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
                    "max_length": self._to_json_value(max_length),
                    "min_length": self._to_json_value(min_length),
                    "max_value": _to_float(max_value),
                    "min_value": _to_float(min_value),
                    "pattern": pattern,
                    "pattern_message": str(pattern_message) if pattern_message else None,
                    "decimal_places": getattr(field, "decimal_places", None),
                    "max_digits": getattr(field, "max_digits", None),
                    "allowed_extensions": self._to_json_value(allowed_extensions),
                    "max_file_size": getattr(field, "max_file_size", None),
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
        except Exception as exc:
            logger.debug(
                "Failed to extract field metadata for %s.%s. Details: %s",
                model._meta.label,
                getattr(field, "name", "<unknown>"),
                str(exc),
                exc_info=True,
            )
            return None

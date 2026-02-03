"""
Field and relationship extraction logic for ModelSchemaExtractor.
"""

import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from django.db import models
from ...security.field_permissions import field_permission_manager, FieldVisibility
from .utils import _classify_field, _get_fsm_transitions
from .mapping import registry

logger = logging.getLogger(__name__)


class FieldExtractorMixin:
    """Mixin for extracting fields and relationships."""

    def _to_json_value(self, value: Any) -> Any:
        """Coerce values into JSON-serializable structures."""
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
        instance: Optional[models.Model] = None,
    ) -> list[dict]:
        """Extract all field schemas."""
        fields = []
        for field in model._meta.get_fields():
            if field.is_relation:
                continue
            if not hasattr(field, "name"):
                continue

            field_schema = self._extract_field(model, field, user, instance)
            if field_schema:
                fields.append(field_schema)
        return fields

    def _extract_field(
        self,
        model: type[models.Model],
        field: models.Field,
        user: Any,
        instance: Optional[models.Model] = None,
    ) -> Optional[dict]:
        """Extract schema for a single field."""
        try:
            field_type = type(field).__name__
            classification = _classify_field(field)

            # Permission check
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

            # Choices
            choices = None
            if hasattr(field, "choices") and field.choices:
                choices = [
                    {"value": str(c[0]), "label": str(c[1])} for c in field.choices
                ]

            # Default value
            default_value = None
            has_default = field.has_default()
            if has_default and not callable(field.default):
                try:
                    default_value = self._to_json_value(field.default)
                except Exception:
                    default_value = str(field.default)

            # Validators
            validators = []
            for v in getattr(field, "validators", []):
                v_type = type(v).__name__
                params = {}

                # Extract limits
                if hasattr(v, "limit_value"):
                    params["limit_value"] = self._to_json_value(v.limit_value)

                # Extract regex patterns
                if hasattr(v, "regex"):
                    if hasattr(v.regex, "pattern"):
                        params["pattern"] = v.regex.pattern
                    elif isinstance(v.regex, str):
                        params["pattern"] = v.regex

                    if hasattr(v, "inverse_match"):
                        params["inverse_match"] = v.inverse_match
                    if hasattr(v, "flags"):
                        params["flags"] = v.flags

                # Extract error messages if available
                message = getattr(v, "message", None)
                if hasattr(v, "code"):
                    params["code"] = v.code

                validators.append({
                    "type": v_type,
                    "params": params if params else None,
                    "message": str(message) if message else None
                })

            # FSM transitions
            fsm_transitions = []
            if classification["is_fsm_field"]:
                fsm_transitions = _get_fsm_transitions(
                    model, field.name, instance=instance
                )

            # GraphQL type mapping
            graphql_type = self._map_to_graphql_type(field_type, field)

            from graphene.utils.str_converters import to_camel_case
            camel_name = to_camel_case(field.name)

            return {
                "name": camel_name,
                "field_name": field.name,
                "verbose_name": str(getattr(field, "verbose_name", field.name)),
                "help_text": str(getattr(field, "help_text", "") or ""),
                "field_type": field_type,
                "graphql_type": graphql_type,
                "python_type": self._get_python_type(field),
                "required": not field.blank and not field.null,
                "nullable": field.null,
                "blank": field.blank,
                "editable": field.editable,
                "unique": field.unique,
                "max_length": getattr(field, "max_length", None),
                "min_length": getattr(field, "min_length", None),
                "max_value": getattr(field, "max_value", None),
                "min_value": getattr(field, "min_value", None),
                "decimal_places": getattr(field, "decimal_places", None),
                "max_digits": getattr(field, "max_digits", None),
                "choices": choices,
                "default_value": default_value,
                "has_default": has_default,
                "auto_now": getattr(field, "auto_now", False),
                "auto_now_add": getattr(field, "auto_now_add", False),
                "validators": validators,
                "regex_pattern": None,
                "readable": readable,
                "writable": writable,
                "visibility": visibility,
                **classification,
                "fsm_transitions": [
                    {
                        "name": t["name"],
                        "source": t["source"],
                        "target": t["target"],
                        "label": t.get("label"),
                        "description": None,
                        "permission": None,
                        "allowed": t.get("allowed", True),
                    }
                    for t in fsm_transitions
                ],
                "custom_metadata": None,
            }
        except Exception as e:
            logger.warning(f"Error extracting field {field.name}: {e}")
            return None

    def _map_to_graphql_type(self, field_type: str, field: models.Field) -> str:
        """Map Django field type to GraphQL type."""
        return registry.get_graphql_type(field)

    def _get_python_type(self, field: models.Field) -> str:
        """Get Python type for a field."""
        return registry.get_python_type(field)

    def _extract_relationships(
        self, model: type[models.Model], user: Any
    ) -> list[dict]:
        """Extract relationship schemas."""
        relationships = []
        for field in model._meta.get_fields():
            if not field.is_relation:
                continue

            rel_schema = self._extract_relationship(model, field, user)
            if rel_schema:
                relationships.append(rel_schema)
        return relationships

    def _extract_relationship(
        self, model: type[models.Model], field: Any, user: Any
    ) -> Optional[dict]:
        """Extract schema for a relationship."""
        try:
            from graphene.utils.str_converters import to_camel_case
            is_reverse = not hasattr(field, "remote_field") or field.auto_created

            if is_reverse:
                related_model = field.related_model
                relation_type = "REVERSE_M2M" if field.many_to_many else "REVERSE_FK"
            else:
                related_model = field.related_model
                if field.many_to_many:
                    relation_type = "MANY_TO_MANY"
                elif field.one_to_one:
                    relation_type = "ONE_TO_ONE"
                else:
                    relation_type = "FOREIGN_KEY"

            is_to_one = relation_type in ("FOREIGN_KEY", "ONE_TO_ONE")
            is_to_many = not is_to_one

            # Permission check
            readable, writable = True, True
            if user and hasattr(field, "name"):
                try:
                    perm = field_permission_manager.check_field_permission(
                        user, model, field.name, instance=None
                    )
                    readable = perm.visibility != FieldVisibility.HIDDEN
                    writable = perm.can_write
                except Exception:
                    pass

            return {
                "name": to_camel_case(field.name) if hasattr(field, "name") else to_camel_case(field.get_accessor_name()),
                "field_name": field.name
                if hasattr(field, "name")
                else field.get_accessor_name(),
                "verbose_name": str(
                    getattr(
                        field,
                        "verbose_name",
                        field.name if hasattr(field, "name") else "",
                    )
                ),
                "help_text": str(getattr(field, "help_text", "") or ""),
                "related_app": related_model._meta.app_label,
                "related_model": related_model.__name__,
                "related_model_verbose": str(related_model._meta.verbose_name),
                "relation_type": relation_type,
                "is_reverse": is_reverse,
                "is_to_one": is_to_one,
                "is_to_many": is_to_many,
                "on_delete": str(
                    getattr(field, "remote_field", None)
                    and getattr(field.remote_field, "on_delete", None).__name__
                )
                if hasattr(field, "remote_field")
                else None,
                "related_name": getattr(field, "related_query_name", lambda: None)()
                if hasattr(field, "related_query_name")
                else None,
                "through_model": field.remote_field.through._meta.label
                if hasattr(field, "remote_field")
                and hasattr(field.remote_field, "through")
                else None,
                "required": not is_reverse and not getattr(field, "null", True),
                "nullable": getattr(field, "null", True),
                "editable": getattr(field, "editable", True),
                "lookup_field": "__str__",
                "search_fields": [],
                "readable": readable,
                "writable": writable,
                "can_create_inline": not is_reverse,
                "custom_metadata": None,
            }
        except Exception as e:
            logger.warning(f"Error extracting relationship: {e}")
            return None

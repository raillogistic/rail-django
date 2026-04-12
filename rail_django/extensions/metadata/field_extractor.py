"""
Field and relationship extraction logic for ModelSchemaExtractor.
"""

import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional, get_args, get_origin
from uuid import UUID

from django.db import models
import graphene
from ...security.field_permissions import field_permission_manager, FieldVisibility
from ...core.settings import MutationGeneratorSettings
from ...generators.introspector import ModelIntrospector
from ...utils.history_detection import (
    is_historical_records_attribute,
    is_historical_relation_field,
)
from .utils import _classify_field, _get_fsm_transitions
from .mapping import registry

logger = logging.getLogger(__name__)


class FieldExtractorMixin:
    """Mixin for extracting fields and relationships."""

    _IGNORED_PROPERTY_NAMES: set[str] = {"pk"}

    _PROPERTY_PYTHON_TO_GRAPHQL: dict[type, str] = {
        str: "String",
        int: "Int",
        float: "Float",
        bool: "Boolean",
        dict: "JSONString",
        date: "Date",
        datetime: "DateTime",
        time: "Time",
        Decimal: "Float",
        UUID: "String",
    }

    @staticmethod
    def _wants(include_keys: Optional[set[str]], key: str) -> bool:
        """Return True when a response key should be included."""
        return not include_keys or key in include_keys

    @staticmethod
    def _split_relation_verbose_name(raw_value: Any) -> tuple[Optional[str], Optional[str]]:
        text = str(raw_value or "").strip()
        if "/" not in text:
            return None, None

        left, right = text.split("/", 1)
        left_value = left.strip() or None
        right_value = right.strip() or None
        return left_value, right_value

    @staticmethod
    def _normalize_relation_name(raw_name: Optional[str]) -> Optional[str]:
        if not raw_name:
            return None
        cleaned = str(raw_name).replace("_", "").strip()
        return cleaned or None

    def _get_relationship_label(
        self,
        *,
        field: Any,
        related_model: type[models.Model],
        is_reverse: bool,
    ) -> str:
        field_name = field.name if hasattr(field, "name") else field.get_accessor_name()
        field_verbose_name = str(
            getattr(
                field,
                "verbose_name",
                field_name,
            )
        )

        if not is_reverse:
            forward_label, _ = self._split_relation_verbose_name(field_verbose_name)
            return forward_label or field_verbose_name

        # Reverse relations should use the source field verbose_name when available.
        source_field = getattr(field, "field", None)
        source_verbose_name = getattr(source_field, "verbose_name", None)
        _, reverse_label = self._split_relation_verbose_name(source_verbose_name)
        if reverse_label:
            return reverse_label

        if bool(getattr(field, "many_to_many", False) or getattr(field, "one_to_many", False)):
            return str(related_model._meta.verbose_name_plural)
        if bool(getattr(field, "one_to_one", False)):
            return str(related_model._meta.verbose_name)

        fallback_name = None
        if hasattr(field, "get_accessor_name"):
            fallback_name = field.get_accessor_name()
        normalized_name = self._normalize_relation_name(fallback_name)
        return normalized_name or field_verbose_name

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
        graphql_meta: Optional[Any] = None,
        include_keys: Optional[set[str]] = None,
    ) -> list[dict]:
        """Extract all field schemas."""
        field_metadata = getattr(graphql_meta, "field_metadata", None) or {}
        fields = []
        for field in model._meta.get_fields():
            if field.is_relation:
                continue
            if not hasattr(field, "name"):
                continue
            if is_historical_records_attribute(model, field.name):
                continue
            if not self._is_field_exposed(graphql_meta, field.name):
                continue

            field_schema = self._extract_field(
                model,
                field,
                user,
                instance,
                field_metadata=field_metadata.get(field.name),
                include_keys=include_keys,
            )
            if field_schema and field_schema.get("readable", True):
                fields.append(field_schema)

        fields.extend(
            self._extract_property_fields(
                model,
                user,
                graphql_meta=graphql_meta,
                existing_field_names={
                    str(f.get("field_name"))
                    for f in fields
                    if isinstance(f, dict) and f.get("field_name")
                },
                field_metadata=field_metadata,
                include_keys=include_keys,
            )
        )
        fields.extend(
            self._extract_custom_field_fields(
                model,
                user,
                graphql_meta=graphql_meta,
                existing_field_names={
                    str(f.get("field_name"))
                    for f in fields
                    if isinstance(f, dict) and f.get("field_name")
                },
                field_metadata=field_metadata,
                include_keys=include_keys,
            )
        )
        return fields

    def _is_field_exposed(
        self,
        graphql_meta: Optional[Any],
        field_name: str,
    ) -> bool:
        if graphql_meta is None:
            return True
        try:
            return bool(graphql_meta.should_expose_field(field_name))
        except Exception:
            return True

    def _extract_property_fields(
        self,
        model: type[models.Model],
        user: Any,
        *,
        graphql_meta: Optional[Any],
        existing_field_names: set[str],
        field_metadata: dict[str, Any],
        include_keys: Optional[set[str]] = None,
    ) -> list[dict]:
        introspector = ModelIntrospector.for_model(model)
        property_fields: list[dict] = []

        for prop_name, prop_info in introspector.get_model_properties().items():
            if str(prop_name).lower() in self._IGNORED_PROPERTY_NAMES:
                continue
            if is_historical_records_attribute(model, str(prop_name)):
                continue
            if prop_name in existing_field_names:
                continue
            if not self._is_field_exposed(graphql_meta, prop_name):
                continue

            property_schema = self._extract_property_field(
                model,
                prop_name,
                prop_info,
                user,
                field_metadata=field_metadata.get(prop_name),
                include_keys=include_keys,
            )
            if property_schema and property_schema.get("readable", True):
                property_fields.append(property_schema)

        property_fields.sort(key=lambda item: str(item.get("name") or ""))
        return property_fields

    def _extract_custom_field_fields(
        self,
        model: type[models.Model],
        user: Any,
        *,
        graphql_meta: Optional[Any],
        existing_field_names: set[str],
        field_metadata: dict[str, Any],
        include_keys: Optional[set[str]] = None,
    ) -> list[dict]:
        introspector = ModelIntrospector.for_model(model)
        custom_fields: list[dict] = []

        for field_name, field_info in introspector.get_model_custom_fields().items():
            if str(field_name).lower() in self._IGNORED_PROPERTY_NAMES:
                continue
            if field_name in existing_field_names:
                continue
            if not self._is_field_exposed(graphql_meta, field_name):
                continue

            field_schema = self._extract_custom_field(
                model,
                field_name,
                field_info,
                user,
                field_metadata=field_metadata.get(field_name),
                include_keys=include_keys,
            )
            if field_schema and field_schema.get("readable", True):
                custom_fields.append(field_schema)

        custom_fields.sort(key=lambda item: str(item.get("name") or ""))
        return custom_fields

    def _extract_property_field(
        self,
        model: type[models.Model],
        property_name: str,
        property_info: Any,
        user: Any,
        *,
        field_metadata: Optional[dict[str, Any]] = None,
        include_keys: Optional[set[str]] = None,
    ) -> Optional[dict]:
        try:
            from graphene.utils.str_converters import to_camel_case

            wants = lambda key: self._wants(include_keys, key)

            readable, writable, visibility = True, False, "VISIBLE"
            if wants("readable") or wants("writable") or wants("visibility"):
                if user:
                    try:
                        perm = field_permission_manager.check_field_permission(
                            user, model, property_name, instance=None
                        )
                        readable = perm.visibility != FieldVisibility.HIDDEN
                        writable = False
                        visibility = (
                            perm.visibility.name
                            if hasattr(perm.visibility, "name")
                            else "VISIBLE"
                        )
                    except Exception:
                        readable, writable, visibility = False, False, "HIDDEN"

            return_type = getattr(property_info, "return_type", Any)
            graphql_type: Optional[str] = None
            if any(
                wants(key)
                for key in (
                    "graphql_type",
                    "is_json",
                    "is_date",
                    "is_datetime",
                    "is_numeric",
                    "is_boolean",
                    "is_text",
                )
            ):
                graphql_type = self._map_property_graphql_type(return_type)

            python_type: Optional[str] = None
            if wants("python_type"):
                python_type = self._map_property_python_type(return_type)

            custom_metadata = None
            if wants("custom_metadata"):
                custom_metadata = (
                    self._to_json_value(field_metadata)
                    if field_metadata is not None
                    else None
                )

            verbose_name = str(
                getattr(property_info, "verbose_name", None)
                or property_name.replace("_", " ").strip()
                or property_name
            )

            result: dict[str, Any] = {}
            if wants("name"):
                result["name"] = to_camel_case(property_name)
            if wants("field_name"):
                result["field_name"] = property_name
            if wants("verbose_name"):
                result["verbose_name"] = verbose_name
            if wants("help_text"):
                result["help_text"] = ""
            if wants("field_type"):
                result["field_type"] = "Property"
            if wants("graphql_type"):
                result["graphql_type"] = graphql_type
            if wants("python_type"):
                result["python_type"] = python_type

            if wants("required"):
                result["required"] = False
            if wants("nullable"):
                result["nullable"] = True
            if wants("blank"):
                result["blank"] = True
            if wants("editable"):
                result["editable"] = False
            if wants("unique"):
                result["unique"] = False
            if wants("max_length"):
                result["max_length"] = None
            if wants("min_length"):
                result["min_length"] = None
            if wants("max_value"):
                result["max_value"] = None
            if wants("min_value"):
                result["min_value"] = None
            if wants("decimal_places"):
                result["decimal_places"] = None
            if wants("max_digits"):
                result["max_digits"] = None
            if wants("choices"):
                result["choices"] = None
            if wants("default_value"):
                result["default_value"] = None
            if wants("has_default"):
                result["has_default"] = False
            if wants("auto_now"):
                result["auto_now"] = False
            if wants("auto_now_add"):
                result["auto_now_add"] = False
            if wants("validators"):
                result["validators"] = []
            if wants("regex_pattern"):
                result["regex_pattern"] = None
            if wants("readable"):
                result["readable"] = readable
            if wants("writable"):
                result["writable"] = writable
            if wants("visibility"):
                result["visibility"] = visibility
            if wants("is_primary_key"):
                result["is_primary_key"] = False
            if wants("is_indexed"):
                result["is_indexed"] = False
            if wants("is_relation"):
                result["is_relation"] = False
            if wants("is_computed"):
                result["is_computed"] = True
            if wants("is_file"):
                result["is_file"] = False
            if wants("is_image"):
                result["is_image"] = False
            if wants("is_json"):
                result["is_json"] = graphql_type == "JSONString"
            if wants("is_date"):
                result["is_date"] = graphql_type == "Date"
            if wants("is_datetime"):
                result["is_datetime"] = graphql_type == "DateTime"
            if wants("is_numeric"):
                result["is_numeric"] = graphql_type in {"Int", "Float", "Decimal"}
            if wants("is_boolean"):
                result["is_boolean"] = graphql_type == "Boolean"
            if wants("is_text"):
                result["is_text"] = graphql_type in {"String", "ID"}
            if wants("is_rich_text"):
                result["is_rich_text"] = False
            if wants("is_fsm_field"):
                result["is_fsm_field"] = False
            if wants("fsm_transitions"):
                result["fsm_transitions"] = []
            if wants("custom_metadata"):
                result["custom_metadata"] = custom_metadata
            return result
        except Exception as e:
            logger.warning("Error extracting property field %s: %s", property_name, e)
            return None

    def _extract_custom_field(
        self,
        model: type[models.Model],
        field_name: str,
        field_info: Any,
        user: Any,
        *,
        field_metadata: Optional[dict[str, Any]] = None,
        include_keys: Optional[set[str]] = None,
    ) -> Optional[dict]:
        try:
            from graphene.utils.str_converters import to_camel_case

            wants = lambda key: self._wants(include_keys, key)

            readable, writable, visibility = True, False, "VISIBLE"
            if wants("readable") or wants("writable") or wants("visibility"):
                if user:
                    try:
                        perm = field_permission_manager.check_field_permission(
                            user, model, field_name, instance=None
                        )
                        readable = perm.visibility != FieldVisibility.HIDDEN
                        visibility = (
                            perm.visibility.name
                            if hasattr(perm.visibility, "name")
                            else "VISIBLE"
                        )
                    except Exception:
                        readable, visibility = False, "HIDDEN"

            return_type = getattr(field_info, "return_type", Any)
            declared_type = getattr(field_info, "field_type", None)
            graphql_type = None
            if any(
                wants(key)
                for key in (
                    "graphql_type",
                    "is_json",
                    "is_date",
                    "is_datetime",
                    "is_numeric",
                    "is_boolean",
                    "is_text",
                )
            ):
                graphql_type = self._map_declared_graphql_type(
                    declared_type
                ) or self._map_property_graphql_type(return_type)

            python_type = None
            if wants("python_type"):
                python_type = self._map_property_python_type(return_type)

            custom_metadata = None
            if wants("custom_metadata"):
                custom_metadata = (
                    self._to_json_value(field_metadata)
                    if field_metadata is not None
                    else None
                )

            verbose_name = str(
                getattr(field_info, "verbose_name", None)
                or field_name.replace("_", " ").strip()
                or field_name
            )

            result: dict[str, Any] = {}
            if wants("name"):
                result["name"] = to_camel_case(field_name)
            if wants("field_name"):
                result["field_name"] = field_name
            if wants("verbose_name"):
                result["verbose_name"] = verbose_name
            if wants("help_text"):
                result["help_text"] = str(getattr(field_info, "description", None) or "")
            if wants("field_type"):
                result["field_type"] = "CustomField"
            if wants("graphql_type"):
                result["graphql_type"] = graphql_type
            if wants("python_type"):
                result["python_type"] = python_type
            if wants("required"):
                result["required"] = False
            if wants("nullable"):
                result["nullable"] = True
            if wants("blank"):
                result["blank"] = True
            if wants("editable"):
                result["editable"] = False
            if wants("unique"):
                result["unique"] = False
            if wants("max_length"):
                result["max_length"] = None
            if wants("min_length"):
                result["min_length"] = None
            if wants("max_value"):
                result["max_value"] = None
            if wants("min_value"):
                result["min_value"] = None
            if wants("decimal_places"):
                result["decimal_places"] = None
            if wants("max_digits"):
                result["max_digits"] = None
            if wants("choices"):
                result["choices"] = None
            if wants("default_value"):
                result["default_value"] = None
            if wants("has_default"):
                result["has_default"] = False
            if wants("auto_now"):
                result["auto_now"] = False
            if wants("auto_now_add"):
                result["auto_now_add"] = False
            if wants("validators"):
                result["validators"] = []
            if wants("regex_pattern"):
                result["regex_pattern"] = None
            if wants("readable"):
                result["readable"] = readable
            if wants("writable"):
                result["writable"] = writable
            if wants("visibility"):
                result["visibility"] = visibility
            if wants("is_primary_key"):
                result["is_primary_key"] = False
            if wants("is_indexed"):
                result["is_indexed"] = False
            if wants("is_relation"):
                result["is_relation"] = False
            if wants("relation_type"):
                result["relation_type"] = None
            if wants("related_model"):
                result["related_model"] = None
            if wants("related_name"):
                result["related_name"] = None
            if wants("on_delete"):
                result["on_delete"] = None
            if wants("through_model"):
                result["through_model"] = None
            if wants("through_fields"):
                result["through_fields"] = None
            if wants("is_reverse"):
                result["is_reverse"] = False
            if wants("is_many_to_many"):
                result["is_many_to_many"] = False
            if wants("is_one_to_many"):
                result["is_one_to_many"] = False
            if wants("is_one_to_one"):
                result["is_one_to_one"] = False
            if wants("is_foreign_key"):
                result["is_foreign_key"] = False
            if wants("is_json"):
                result["is_json"] = graphql_type == "JSONString"
            if wants("is_date"):
                result["is_date"] = graphql_type == "Date"
            if wants("is_datetime"):
                result["is_datetime"] = graphql_type == "DateTime"
            if wants("is_numeric"):
                result["is_numeric"] = graphql_type in {"Int", "Float", "Decimal"}
            if wants("is_boolean"):
                result["is_boolean"] = graphql_type == "Boolean"
            if wants("is_text"):
                result["is_text"] = graphql_type in {"String", "ID"}
            if wants("is_computed"):
                result["is_computed"] = True
            if wants("is_file"):
                result["is_file"] = False
            if wants("is_image"):
                result["is_image"] = False
            if wants("is_required_on_create"):
                result["is_required_on_create"] = False
            if wants("is_required_on_update"):
                result["is_required_on_update"] = False
            if wants("custom_metadata"):
                result["custom_metadata"] = custom_metadata

            return result
        except Exception as e:
            logger.warning("Error extracting custom field %s: %s", field_name, e)
            return None

    def _map_declared_graphql_type(self, declared_type: Any) -> Optional[str]:
        if declared_type is None:
            return None

        if isinstance(declared_type, graphene.Field):
            field_type = getattr(declared_type, "_type", None)
            if callable(field_type):
                try:
                    field_type = field_type()
                except Exception:
                    pass
            return self._map_declared_graphql_type(field_type)

        if isinstance(declared_type, graphene.types.unmountedtype.UnmountedType):
            declared_type = declared_type.__class__

        if isinstance(declared_type, type):
            name = getattr(declared_type, "__name__", "")
            if name:
                return name

        return None

    def _map_property_graphql_type(self, annotation: Any) -> str:
        if annotation in (None, Any):
            return "String"

        if isinstance(annotation, str):
            normalized = annotation.strip()
            if not normalized:
                return "String"
            return {
                "str": "String",
                "string": "String",
                "int": "Int",
                "float": "Float",
                "bool": "Boolean",
                "dict": "JSONString",
                "date": "Date",
                "datetime": "DateTime",
                "time": "Time",
            }.get(normalized.lower(), "String")

        mapped = self._PROPERTY_PYTHON_TO_GRAPHQL.get(annotation)
        if mapped:
            return mapped

        origin = get_origin(annotation)
        if origin in (list, tuple, set):
            inner_args = get_args(annotation)
            inner_type = (
                self._map_property_graphql_type(inner_args[0])
                if inner_args
                else "String"
            )
            return f"[{inner_type}]"

        if origin is dict:
            return "JSONString"

        if origin is None and hasattr(annotation, "__args__"):
            args = [a for a in getattr(annotation, "__args__", ()) if a is not type(None)]
            if len(args) == 1:
                return self._map_property_graphql_type(args[0])

        if origin is not None:
            args = [a for a in get_args(annotation) if a is not type(None)]
            if len(args) == 1:
                return self._map_property_graphql_type(args[0])

        return "String"

    def _map_property_python_type(self, annotation: Any) -> str:
        if annotation in (None, Any):
            return "Any"
        if isinstance(annotation, str):
            return annotation or "Any"
        if hasattr(annotation, "__name__"):
            return str(annotation.__name__)

        rendered = str(annotation).replace("typing.", "")
        return rendered or "Any"

    def _extract_field(
        self,
        model: type[models.Model],
        field: models.Field,
        user: Any,
        instance: Optional[models.Model] = None,
        field_metadata: Optional[dict[str, Any]] = None,
        include_keys: Optional[set[str]] = None,
    ) -> Optional[dict]:
        """Extract schema for a single field."""
        try:
            wants = lambda key: self._wants(include_keys, key)
            field_type = type(field).__name__
            readable, writable, visibility = True, True, "VISIBLE"
            choices = None
            default_value = None
            has_default = False
            validators: list[dict[str, Any]] = []
            fsm_transitions = []

            if wants("readable") or wants("writable") or wants("visibility"):
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
                        readable, writable, visibility = False, False, "HIDDEN"

            if wants("choices") and hasattr(field, "choices") and field.choices:
                choices = [
                    {"value": str(c[0]), "label": str(c[1])} for c in field.choices
                ]

            if wants("default_value") or wants("has_default"):
                has_default = field.has_default()
                if has_default and not callable(field.default) and wants("default_value"):
                    try:
                        default_value = self._to_json_value(field.default)
                    except Exception:
                        default_value = str(field.default)

            if wants("validators"):
                for v in getattr(field, "validators", []):
                    v_type = type(v).__name__
                    params = {}

                    if hasattr(v, "limit_value"):
                        params["limit_value"] = self._to_json_value(v.limit_value)

                    if hasattr(v, "regex"):
                        if hasattr(v.regex, "pattern"):
                            params["pattern"] = v.regex.pattern
                        elif isinstance(v.regex, str):
                            params["pattern"] = v.regex

                        if hasattr(v, "inverse_match"):
                            params["inverse_match"] = v.inverse_match
                        if hasattr(v, "flags"):
                            params["flags"] = v.flags

                    message = getattr(v, "message", None)
                    if hasattr(v, "code"):
                        params["code"] = v.code

                    validators.append(
                        {
                            "type": v_type,
                            "params": params if params else None,
                            "message": str(message) if message else None,
                        }
                    )

            classification_keys = (
                "is_primary_key",
                "is_indexed",
                "is_relation",
                "is_computed",
                "is_file",
                "is_image",
                "is_json",
                "is_date",
                "is_datetime",
                "is_numeric",
                "is_boolean",
                "is_text",
                "is_rich_text",
                "is_fsm_field",
            )
            classification = (
                _classify_field(field)
                if any(wants(key) for key in classification_keys) or wants("fsm_transitions")
                else {}
            )

            if wants("fsm_transitions") and classification.get("is_fsm_field"):
                fsm_transitions = _get_fsm_transitions(
                    model, field.name, instance=instance
                )

            graphql_type = (
                self._map_to_graphql_type(field_type, field)
                if wants("graphql_type")
                else None
            )

            from graphene.utils.str_converters import to_camel_case
            camel_name = to_camel_case(field.name)
            custom_metadata = None
            if wants("custom_metadata"):
                custom_metadata = (
                    self._to_json_value(field_metadata)
                    if field_metadata is not None
                    else None
                )

            result: dict[str, Any] = {}
            if wants("name"):
                result["name"] = camel_name
            if wants("field_name"):
                result["field_name"] = field.name
            if wants("verbose_name"):
                result["verbose_name"] = str(getattr(field, "verbose_name", field.name))
            if wants("help_text"):
                result["help_text"] = str(getattr(field, "help_text", "") or "")
            if wants("field_type"):
                result["field_type"] = field_type
            if wants("graphql_type"):
                result["graphql_type"] = graphql_type
            if wants("python_type"):
                result["python_type"] = self._get_python_type(field)
            if wants("required"):
                result["required"] = not field.blank and not field.null
            if wants("nullable"):
                result["nullable"] = field.null
            if wants("blank"):
                result["blank"] = field.blank
            if wants("editable"):
                result["editable"] = field.editable
            if wants("unique"):
                result["unique"] = field.unique
            if wants("max_length"):
                result["max_length"] = getattr(field, "max_length", None)
            if wants("min_length"):
                result["min_length"] = getattr(field, "min_length", None)
            if wants("max_value"):
                result["max_value"] = getattr(field, "max_value", None)
            if wants("min_value"):
                result["min_value"] = getattr(field, "min_value", None)
            if wants("decimal_places"):
                result["decimal_places"] = getattr(field, "decimal_places", None)
            if wants("max_digits"):
                result["max_digits"] = getattr(field, "max_digits", None)
            if wants("choices"):
                result["choices"] = choices
            if wants("default_value"):
                result["default_value"] = default_value
            if wants("has_default"):
                result["has_default"] = has_default
            if wants("auto_now"):
                result["auto_now"] = getattr(field, "auto_now", False)
            if wants("auto_now_add"):
                result["auto_now_add"] = getattr(field, "auto_now_add", False)
            if wants("validators"):
                result["validators"] = validators
            if wants("regex_pattern"):
                result["regex_pattern"] = None
            if wants("readable"):
                result["readable"] = readable
            if wants("writable"):
                result["writable"] = writable
            if wants("visibility"):
                result["visibility"] = visibility

            for key in classification_keys:
                if wants(key):
                    result[key] = classification.get(key)

            if wants("fsm_transitions"):
                result["fsm_transitions"] = [
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
                ]
            if wants("custom_metadata"):
                result["custom_metadata"] = custom_metadata
            return result
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
        self,
        model: type[models.Model],
        user: Any,
        graphql_meta: Optional[Any] = None,
        include_keys: Optional[set[str]] = None,
    ) -> list[dict]:
        """Extract relationship schemas."""
        field_metadata = getattr(graphql_meta, "field_metadata", None) or {}
        relationships = []
        for field in model._meta.get_fields():
            if not field.is_relation:
                continue
            if is_historical_relation_field(field):
                continue

            field_key = (
                field.name
                if hasattr(field, "name")
                else field.get_accessor_name()
            )
            rel_schema = self._extract_relationship(
                model,
                field,
                user,
                field_metadata=field_metadata.get(field_key),
                graphql_meta=graphql_meta,
                include_keys=include_keys,
            )
            if rel_schema and rel_schema.get("readable", True):
                relationships.append(rel_schema)
        return relationships

    def _extract_relationship(
        self,
        model: type[models.Model],
        field: Any,
        user: Any,
        field_metadata: Optional[dict[str, Any]] = None,
        graphql_meta: Optional[Any] = None,
        include_keys: Optional[set[str]] = None,
    ) -> Optional[dict]:
        """Extract schema for a relationship."""
        try:
            from graphene.utils.str_converters import to_camel_case
            wants = lambda key: self._wants(include_keys, key)
            is_reverse = not hasattr(field, "remote_field") or field.auto_created
            field_key = field.name if hasattr(field, "name") else field.get_accessor_name()

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
            if wants("readable") or wants("writable"):
                if user and hasattr(field, "name"):
                    try:
                        perm = field_permission_manager.check_field_permission(
                            user, model, field.name, instance=None
                        )
                        readable = perm.visibility != FieldVisibility.HIDDEN
                        writable = perm.can_write
                    except Exception:
                        readable, writable = False, False

            if related_model is None:
                # Skip relationships without a concrete related model (e.g. generic relations).
                return None

            on_delete_name = None
            if wants("on_delete"):
                if getattr(field, "remote_field", None) and getattr(
                    field.remote_field, "on_delete", None
                ):
                    on_delete_name = field.remote_field.on_delete.__name__

            custom_metadata = None
            if wants("custom_metadata"):
                custom_metadata = (
                    self._to_json_value(field_metadata)
                    if field_metadata is not None
                    else None
                )

            related_query_name = None
            if wants("related_name") and hasattr(field, "related_query_name"):
                candidate = field.related_query_name
                if callable(candidate):
                    try:
                        related_query_name = candidate()
                    except Exception:
                        related_query_name = None
                elif isinstance(candidate, str):
                    related_query_name = candidate

            relation_operations = None
            if wants("relation_operations"):
                relation_operations = self._extract_relation_operations(
                    model, field_key, graphql_meta=graphql_meta
                )

            relationship_label = None
            if wants("verbose_name"):
                relationship_label = self._get_relationship_label(
                    field=field,
                    related_model=related_model,
                    is_reverse=is_reverse,
                )

            result: dict[str, Any] = {}
            if wants("name"):
                result["name"] = (
                    to_camel_case(field.name)
                    if hasattr(field, "name")
                    else to_camel_case(field.get_accessor_name())
                )
            if wants("field_name"):
                result["field_name"] = (
                    field.name if hasattr(field, "name") else field.get_accessor_name()
                )
            if wants("verbose_name"):
                result["verbose_name"] = relationship_label
            if wants("help_text"):
                result["help_text"] = str(getattr(field, "help_text", "") or "")
            if wants("related_app"):
                result["related_app"] = related_model._meta.app_label
            if wants("related_model"):
                result["related_model"] = related_model.__name__
            if wants("related_model_verbose"):
                result["related_model_verbose"] = str(related_model._meta.verbose_name)
            if wants("relation_type"):
                result["relation_type"] = relation_type
            if wants("is_reverse"):
                result["is_reverse"] = is_reverse
            if wants("is_to_one"):
                result["is_to_one"] = is_to_one
            if wants("is_to_many"):
                result["is_to_many"] = is_to_many
            if wants("on_delete"):
                result["on_delete"] = on_delete_name
            if wants("related_name"):
                result["related_name"] = related_query_name
            if wants("through_model"):
                result["through_model"] = (
                    field.remote_field.through._meta.label
                    if hasattr(field, "remote_field")
                    and hasattr(field.remote_field, "through")
                    else None
                )
            if wants("required"):
                result["required"] = not is_reverse and not getattr(field, "null", True)
            if wants("nullable"):
                result["nullable"] = getattr(field, "null", True)
            if wants("editable"):
                result["editable"] = getattr(field, "editable", True)
            if wants("lookup_field"):
                result["lookup_field"] = "__str__"
            if wants("search_fields"):
                result["search_fields"] = []
            if wants("readable"):
                result["readable"] = readable
            if wants("writable"):
                result["writable"] = writable
            if wants("can_create_inline"):
                result["can_create_inline"] = not is_reverse
            if wants("relation_operations"):
                result["relation_operations"] = relation_operations
            if wants("custom_metadata"):
                result["custom_metadata"] = custom_metadata
            return result
        except Exception as e:
            logger.warning(f"Error extracting relationship: {e}")
            return None

    def _extract_relation_operations(
        self,
        model: type[models.Model],
        field_name: str,
        graphql_meta: Optional[Any] = None,
    ) -> Optional[dict]:
        """Build relation operation metadata from GraphQLMeta and settings."""
        try:
            schema_name = getattr(self, "schema_name", "default")
            settings = MutationGeneratorSettings.from_schema(schema_name)
        except Exception:
            settings = None

        cfg = None
        if graphql_meta is not None:
            try:
                cfg = graphql_meta.get_relation_config(field_name)
            except Exception:
                cfg = None

        def op_dict(op_cfg: Any, default_enabled: bool = True) -> dict:
            enabled = default_enabled
            require_permission = None
            if op_cfg is not None:
                enabled = bool(getattr(op_cfg, "enabled", default_enabled))
                require_permission = getattr(op_cfg, "require_permission", None)
            return {"enabled": enabled, "require_permission": require_permission}

        # Defaults
        connect_enabled = True
        create_enabled = True
        update_enabled = True
        disconnect_enabled = True
        set_enabled = True

        if cfg is not None:
            connect_enabled = bool(getattr(getattr(cfg, "connect", None), "enabled", True))
            create_enabled = bool(getattr(getattr(cfg, "create", None), "enabled", True))
            update_enabled = bool(getattr(getattr(cfg, "update", None), "enabled", True))
            disconnect_enabled = bool(getattr(getattr(cfg, "disconnect", None), "enabled", True))
            set_enabled = bool(getattr(getattr(cfg, "set", None), "enabled", True))

        # Apply global nested relation settings (disable nested create/update)
        if settings is not None:
            model_name = model.__name__
            nested_enabled = bool(getattr(settings, "enable_nested_relations", True))
            if model_name in getattr(settings, "nested_relations_config", {}):
                nested_enabled = bool(settings.nested_relations_config[model_name])
            if not nested_enabled:
                create_enabled = False
                update_enabled = False

        style = getattr(cfg, "style", "unified") if cfg is not None else "unified"
        if str(style).lower() == "id_only":
            create_enabled = False
            update_enabled = False

        return {
            "style": style,
            "connect": op_dict(getattr(cfg, "connect", None), connect_enabled),
            "create": op_dict(getattr(cfg, "create", None), create_enabled),
            "update": op_dict(getattr(cfg, "update", None), update_enabled),
            "disconnect": op_dict(getattr(cfg, "disconnect", None), disconnect_enabled),
            "set": op_dict(getattr(cfg, "set", None), set_enabled),
        }

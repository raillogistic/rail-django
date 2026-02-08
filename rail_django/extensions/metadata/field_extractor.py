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
from ...core.settings import MutationGeneratorSettings
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
        graphql_meta: Optional[Any] = None,
    ) -> list[dict]:
        """Extract all field schemas."""
        field_metadata = getattr(graphql_meta, "field_metadata", None) or {}
        fields = []
        for field in model._meta.get_fields():
            if field.is_relation:
                continue
            if not hasattr(field, "name"):
                continue

            field_schema = self._extract_field(
                model,
                field,
                user,
                instance,
                field_metadata=field_metadata.get(field.name),
            )
            if field_schema and field_schema.get("readable", True):
                fields.append(field_schema)
        return fields

    def _extract_field(
        self,
        model: type[models.Model],
        field: models.Field,
        user: Any,
        instance: Optional[models.Model] = None,
        field_metadata: Optional[dict[str, Any]] = None,
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
            custom_metadata = (
                self._to_json_value(field_metadata)
                if field_metadata is not None
                else None
            )

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
                "custom_metadata": custom_metadata,
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
        self, model: type[models.Model], user: Any, graphql_meta: Optional[Any] = None
    ) -> list[dict]:
        """Extract relationship schemas."""
        field_metadata = getattr(graphql_meta, "field_metadata", None) or {}
        relationships = []
        for field in model._meta.get_fields():
            if not field.is_relation:
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
    ) -> Optional[dict]:
        """Extract schema for a relationship."""
        try:
            from graphene.utils.str_converters import to_camel_case
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
            if user and hasattr(field, "name"):
                try:
                    perm = field_permission_manager.check_field_permission(
                        user, model, field.name, instance=None
                    )
                    readable = perm.visibility != FieldVisibility.HIDDEN
                    writable = perm.can_write
                except Exception:
                    pass

            if related_model is None:
                # Skip relationships without a concrete related model (e.g. generic relations).
                return None

            on_delete_name = None
            if getattr(field, "remote_field", None) and getattr(
                field.remote_field, "on_delete", None
            ):
                on_delete_name = field.remote_field.on_delete.__name__

            custom_metadata = (
                self._to_json_value(field_metadata)
                if field_metadata is not None
                else None
            )

            related_query_name = None
            if hasattr(field, "related_query_name"):
                candidate = field.related_query_name
                if callable(candidate):
                    try:
                        related_query_name = candidate()
                    except Exception:
                        related_query_name = None
                elif isinstance(candidate, str):
                    related_query_name = candidate

            relation_operations = self._extract_relation_operations(
                model, field_key, graphql_meta=graphql_meta
            )

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
                "on_delete": on_delete_name,
                "related_name": related_query_name,
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
                "relation_operations": relation_operations,
                "custom_metadata": custom_metadata,
            }
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

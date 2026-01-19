"""
Metadata V2: Rich Model Introspection for Frontend UI Generation.

This module provides comprehensive metadata exposure for Django models,
enabling frontends to build forms, tables, and detail views automatically.

Philosophy: Expose rich data, let the frontend decide how to render it.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Optional, Union

import graphene
from django.apps import apps
from django.db import models
from django.utils.encoding import force_str
from graphql import GraphQLError

from ..config_proxy import get_core_schema_settings
from ..core.settings import SchemaSettings
from ..security.field_permissions import field_permission_manager, FieldVisibility
from ..utils.graphql_meta import get_model_graphql_meta

logger = logging.getLogger(__name__)

# Cache management
_schema_cache: dict[str, dict[str, Any]] = {}
_cache_version = str(int(time.time() * 1000))


def _generate_version() -> str:
    """Generate a metadata version token."""
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _get_cache_key(app: str, model: str, user_id: Optional[str] = None) -> str:
    """Build cache key for model schema."""
    key = f"v2:{app}:{model}"
    if user_id:
        key = f"{key}:{hashlib.sha1(str(user_id).encode()).hexdigest()[:8]}"
    return key


def invalidate_metadata_v2_cache(app: str = None, model: str = None) -> None:
    """Invalidate metadata v2 cache."""
    global _cache_version
    _cache_version = _generate_version()
    _schema_cache.clear()


# =============================================================================
# Field Classification Helpers
# =============================================================================


def _is_fsm_field(field: Any) -> bool:
    """Check if field is django-fsm FSMField."""
    try:
        from django_fsm import FSMField

        return isinstance(field, FSMField)
    except ImportError:
        return False


def _get_fsm_transitions(model: type[models.Model], field_name: str) -> list[dict]:
    """Get FSM transitions for a field."""
    try:
        from django_fsm import get_available_FIELD_transitions

        func = getattr(model, f"get_available_{field_name}_transitions", None)
        if not func:
            return []
        # Return static transition info (without instance)
        transitions = []
        for attr_name in dir(model):
            attr = getattr(model, attr_name, None)
            if hasattr(attr, "_django_fsm"):
                fsm_meta = attr._django_fsm
                if hasattr(fsm_meta, "field") and fsm_meta.field.name == field_name:
                    for source, target in getattr(fsm_meta, "transitions", {}).items():
                        transitions.append(
                            {
                                "name": attr_name,
                                "source": [source] if source != "*" else ["*"],
                                "target": target.target
                                if hasattr(target, "target")
                                else str(target),
                                "label": getattr(
                                    attr, "label", attr_name.replace("_", " ").title()
                                ),
                            }
                        )
        return transitions
    except Exception:
        return []


def _classify_field(field: models.Field) -> dict[str, bool]:
    """Return classification flags for a field."""
    field_type = type(field).__name__
    return {
        "is_primary_key": field.primary_key,
        "is_indexed": field.db_index or field.unique or field.primary_key,
        "is_relation": field.is_relation,
        "is_computed": False,
        "is_file": field_type in ("FileField", "FilePathField"),
        "is_image": field_type == "ImageField",
        "is_json": field_type == "JSONField",
        "is_date": field_type == "DateField",
        "is_datetime": field_type in ("DateTimeField", "DateField"),
        "is_time": field_type == "TimeField",
        "is_numeric": field_type
        in (
            "IntegerField",
            "SmallIntegerField",
            "BigIntegerField",
            "PositiveIntegerField",
            "PositiveSmallIntegerField",
            "PositiveBigIntegerField",
            "FloatField",
            "DecimalField",
        ),
        "is_boolean": field_type in ("BooleanField", "NullBooleanField"),
        "is_text": field_type
        in ("CharField", "TextField", "SlugField", "URLField", "EmailField"),
        "is_rich_text": field_type == "TextField",
        "is_fsm_field": _is_fsm_field(field),
        "is_uuid": field_type == "UUIDField",
        "is_ip": field_type in ("IPAddressField", "GenericIPAddressField"),
        "is_duration": field_type == "DurationField",
    }


# =============================================================================
# GraphQL Types
# =============================================================================


class ChoiceTypeV2(graphene.ObjectType):
    """Choice option for select fields."""

    value = graphene.String(required=True)
    label = graphene.String(required=True)
    group = graphene.String()
    disabled = graphene.Boolean()


class ValidatorInfoType(graphene.ObjectType):
    """Validator information."""

    type = graphene.String(required=True)
    params = graphene.JSONString()
    message = graphene.String()


class FSMTransitionType(graphene.ObjectType):
    """FSM state transition."""

    name = graphene.String(required=True)
    source = graphene.List(graphene.String, required=True)
    target = graphene.String(required=True)
    label = graphene.String()
    description = graphene.String()
    permission = graphene.String()
    allowed = graphene.Boolean(required=True)


class FieldSchemaType(graphene.ObjectType):
    """Complete field schema for UI rendering."""

    # Identity
    name = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    help_text = graphene.String()

    # Type info
    field_type = graphene.String(required=True)
    graphql_type = graphene.String(required=True)
    python_type = graphene.String()

    # Constraints
    required = graphene.Boolean(required=True)
    nullable = graphene.Boolean(required=True)
    blank = graphene.Boolean(required=True)
    editable = graphene.Boolean(required=True)
    unique = graphene.Boolean(required=True)

    # Value constraints
    max_length = graphene.Int()
    min_length = graphene.Int()
    max_value = graphene.Float()
    min_value = graphene.Float()
    decimal_places = graphene.Int()
    max_digits = graphene.Int()

    # Choices
    choices = graphene.List(ChoiceTypeV2)

    # Default
    default_value = graphene.JSONString()
    has_default = graphene.Boolean(required=True)
    auto_now = graphene.Boolean(required=True)
    auto_now_add = graphene.Boolean(required=True)

    # Validators
    validators = graphene.List(ValidatorInfoType)
    regex_pattern = graphene.String()

    # Permissions
    readable = graphene.Boolean(required=True)
    writable = graphene.Boolean(required=True)
    visibility = graphene.String(required=True)

    # Classification flags
    is_primary_key = graphene.Boolean(required=True)
    is_indexed = graphene.Boolean(required=True)
    is_relation = graphene.Boolean(required=True)
    is_computed = graphene.Boolean(required=True)
    is_file = graphene.Boolean(required=True)
    is_image = graphene.Boolean(required=True)
    is_json = graphene.Boolean(required=True)
    is_date = graphene.Boolean(required=True)
    is_datetime = graphene.Boolean(required=True)
    is_numeric = graphene.Boolean(required=True)
    is_boolean = graphene.Boolean(required=True)
    is_text = graphene.Boolean(required=True)
    is_rich_text = graphene.Boolean(required=True)
    is_fsm_field = graphene.Boolean(required=True)

    # FSM
    fsm_transitions = graphene.List(FSMTransitionType)

    # Custom metadata
    custom_metadata = graphene.JSONString()


class RelationshipSchemaType(graphene.ObjectType):
    """Relationship field schema."""

    name = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    help_text = graphene.String()

    # Related model
    related_app = graphene.String(required=True)
    related_model = graphene.String(required=True)
    related_model_verbose = graphene.String(required=True)

    # Relationship type
    relation_type = graphene.String(required=True)
    is_reverse = graphene.Boolean(required=True)
    is_to_one = graphene.Boolean(required=True)
    is_to_many = graphene.Boolean(required=True)

    # Config
    on_delete = graphene.String()
    related_name = graphene.String()
    through_model = graphene.String()

    # Constraints
    required = graphene.Boolean(required=True)
    nullable = graphene.Boolean(required=True)
    editable = graphene.Boolean(required=True)

    # Lookup
    lookup_field = graphene.String(required=True)
    search_fields = graphene.List(graphene.String)

    # Permissions
    readable = graphene.Boolean(required=True)
    writable = graphene.Boolean(required=True)
    can_create_inline = graphene.Boolean(required=True)

    # Custom
    custom_metadata = graphene.JSONString()


class InputFieldSchemaType(graphene.ObjectType):
    """Mutation input field schema."""

    name = graphene.String(required=True)
    field_type = graphene.String(required=True)
    graphql_type = graphene.String(required=True)
    required = graphene.Boolean(required=True)
    default_value = graphene.JSONString()
    description = graphene.String()
    choices = graphene.List(ChoiceTypeV2)
    related_model = graphene.String()


class MutationSchemaType(graphene.ObjectType):
    """Available mutation schema."""

    name = graphene.String(required=True)
    operation = graphene.String(required=True)
    description = graphene.String()
    method_name = graphene.String()
    input_fields = graphene.List(InputFieldSchemaType, required=True)
    allowed = graphene.Boolean(required=True)
    required_permissions = graphene.List(graphene.String)
    reason = graphene.String()


class FilterOptionSchemaType(graphene.ObjectType):
    """Filter option/operator schema."""

    name = graphene.String(required=True)
    lookup = graphene.String(required=True)
    help_text = graphene.String()
    choices = graphene.List(ChoiceTypeV2)
    graphql_type = graphene.String(description="GraphQL type for this operator")
    is_list = graphene.Boolean(description="Whether this operator accepts a list")


class FilterStyleEnum(graphene.Enum):
    """Filter input style."""

    FLAT = "flat"
    NESTED = "nested"


class RelationFilterSchemaType(graphene.ObjectType):
    """Relation filter schema for M2M and reverse relations."""

    relation_name = graphene.String(required=True)
    relation_type = graphene.String(required=True)
    supports_some = graphene.Boolean(required=True)
    supports_every = graphene.Boolean(required=True)
    supports_none = graphene.Boolean(required=True)
    supports_count = graphene.Boolean(required=True)
    nested_filter_type = graphene.String()


class FilterSchemaType(graphene.ObjectType):
    """Filter field schema with support for both flat and nested styles."""

    field_name = graphene.String(required=True)
    field_label = graphene.String(required=True)
    is_nested = graphene.Boolean(required=True)
    related_model = graphene.String()
    options = graphene.List(FilterOptionSchemaType, required=True)

    # New fields for nested filter style
    filter_input_type = graphene.String(
        description="Filter input type (e.g., StringFilterInput)"
    )
    available_operators = graphene.List(
        graphene.String, description="Available operators for nested style"
    )


class FilterConfigType(graphene.ObjectType):
    """Overall filter configuration for a model."""

    style = graphene.Field(FilterStyleEnum, required=True)
    argument_name = graphene.String(
        required=True, description="'where' for nested filtering"
    )
    input_type_name = graphene.String(
        required=True, description="e.g., UserWhereInput"
    )
    supports_and = graphene.Boolean(required=True)
    supports_or = graphene.Boolean(required=True)
    supports_not = graphene.Boolean(required=True)
    dual_mode_enabled = graphene.Boolean(
        required=True, description="Both filter styles available"
    )


class ModelPermissionsType(graphene.ObjectType):
    """Model-level permissions for current user."""

    can_list = graphene.Boolean(required=True)
    can_retrieve = graphene.Boolean(required=True)
    can_create = graphene.Boolean(required=True)
    can_update = graphene.Boolean(required=True)
    can_delete = graphene.Boolean(required=True)
    can_bulk_create = graphene.Boolean(required=True)
    can_bulk_update = graphene.Boolean(required=True)
    can_bulk_delete = graphene.Boolean(required=True)
    can_export = graphene.Boolean(required=True)
    denial_reasons = graphene.JSONString()


class FieldGroupType(graphene.ObjectType):
    """Field grouping hint for frontend organization."""

    key = graphene.String(required=True)
    label = graphene.String(required=True)
    description = graphene.String()
    fields = graphene.List(graphene.String, required=True)


class TemplateInfoType(graphene.ObjectType):
    """Available template info."""

    key = graphene.String(required=True)
    title = graphene.String(required=True)
    description = graphene.String()
    endpoint = graphene.String(required=True)


class ModelInfoType(graphene.ObjectType):
    """Basic model info."""

    app = graphene.String(required=True)
    model = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    verbose_name_plural = graphene.String(required=True)


class ModelSchemaType(graphene.ObjectType):
    """Complete model schema for UI generation."""

    # Identity
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    verbose_name_plural = graphene.String(required=True)

    # Structure
    primary_key = graphene.String(required=True)
    ordering = graphene.List(graphene.String)
    unique_together = graphene.List(graphene.List(graphene.String))

    # Fields
    fields = graphene.List(FieldSchemaType, required=True)
    relationships = graphene.List(RelationshipSchemaType, required=True)

    # Filters
    filters = graphene.List(FilterSchemaType, required=True)
    filter_config = graphene.Field(
        FilterConfigType, description="Filter style configuration"
    )
    relation_filters = graphene.List(
        RelationFilterSchemaType,
        description="Relation filters for M2M and reverse relations (nested style)",
    )

    # Mutations
    mutations = graphene.List(MutationSchemaType, required=True)

    # Permissions
    permissions = graphene.Field(ModelPermissionsType, required=True)

    # Hints
    field_groups = graphene.List(FieldGroupType)

    # Templates
    templates = graphene.List(TemplateInfoType)

    # Cache
    metadata_version = graphene.String(required=True)

    # Custom
    custom_metadata = graphene.JSONString()


# =============================================================================
# Extractors
# =============================================================================


class ModelSchemaExtractor:
    """
    Extracts comprehensive schema information from Django models.

    Attributes:
        schema_name: Name of the schema configuration.
    """

    def __init__(self, schema_name: str = "default"):
        """
        Initialize the schema extractor.

        Args:
            schema_name: Schema configuration name.
        """
        self.schema_name = schema_name

    def extract(
        self,
        app_name: str,
        model_name: str,
        user: Any = None,
        object_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Extract complete schema for a model.

        Args:
            app_name: Django app label.
            model_name: Model class name.
            user: Current user for permission checks.
            object_id: Instance ID for instance-specific permissions.

        Returns:
            Complete model schema dictionary.
        """
        try:
            model = apps.get_model(app_name, model_name)
        except LookupError:
            raise GraphQLError(f"Model '{app_name}.{model_name}' not found.")

        meta = model._meta
        graphql_meta = get_model_graphql_meta(model)

        return {
            "app": app_name,
            "model": model_name,
            "verbose_name": str(meta.verbose_name),
            "verbose_name_plural": str(meta.verbose_name_plural),
            "primary_key": meta.pk.name if meta.pk else "id",
            "ordering": list(meta.ordering) if meta.ordering else [],
            "unique_together": [list(ut) for ut in meta.unique_together]
            if meta.unique_together
            else [],
            "fields": self._extract_fields(model, user),
            "relationships": self._extract_relationships(model, user),
            "filters": self._extract_filters(model),
            "filter_config": self._extract_filter_config(model),
            "relation_filters": self._extract_relation_filters(model),
            "mutations": self._extract_mutations(model, user),
            "permissions": self._extract_permissions(model, user),
            "field_groups": self._extract_field_groups(model, graphql_meta),
            "templates": self._extract_templates(model, user),
            "metadata_version": _cache_version,
            "custom_metadata": getattr(graphql_meta, "custom_metadata", None),
        }

    def _extract_fields(self, model: type[models.Model], user: Any) -> list[dict]:
        """Extract all field schemas."""
        fields = []
        for field in model._meta.get_fields():
            if field.is_relation:
                continue
            if not hasattr(field, "name"):
                continue

            field_schema = self._extract_field(model, field, user)
            if field_schema:
                fields.append(field_schema)
        return fields

    def _extract_field(
        self, model: type[models.Model], field: models.Field, user: Any
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
                    default_value = field.default
                    if hasattr(default_value, "__json__"):
                        default_value = default_value.__json__()
                except Exception:
                    default_value = str(field.default)

            # Validators
            validators = []
            for v in getattr(field, "validators", []):
                v_type = type(v).__name__
                validators.append({"type": v_type, "params": None, "message": None})

            # FSM transitions
            fsm_transitions = []
            if classification["is_fsm_field"]:
                fsm_transitions = _get_fsm_transitions(model, field.name)

            # GraphQL type mapping
            graphql_type = self._map_to_graphql_type(field_type, field)

            return {
                "name": field.name,
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
                        "allowed": True,
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
        mapping = {
            "CharField": "String",
            "TextField": "String",
            "SlugField": "String",
            "URLField": "String",
            "EmailField": "String",
            "UUIDField": "String",
            "IntegerField": "Int",
            "SmallIntegerField": "Int",
            "BigIntegerField": "Int",
            "PositiveIntegerField": "Int",
            "PositiveSmallIntegerField": "Int",
            "FloatField": "Float",
            "DecimalField": "Float",
            "BooleanField": "Boolean",
            "NullBooleanField": "Boolean",
            "DateField": "Date",
            "DateTimeField": "DateTime",
            "TimeField": "Time",
            "JSONField": "JSONString",
            "FileField": "String",
            "ImageField": "String",
            "ForeignKey": "ID",
            "OneToOneField": "ID",
        }
        return mapping.get(field_type, "String")

    def _get_python_type(self, field: models.Field) -> str:
        """Get Python type for a field."""
        field_type = type(field).__name__
        mapping = {
            "CharField": "str",
            "TextField": "str",
            "IntegerField": "int",
            "FloatField": "float",
            "DecimalField": "Decimal",
            "BooleanField": "bool",
            "DateField": "date",
            "DateTimeField": "datetime",
            "JSONField": "dict",
        }
        return mapping.get(field_type, "str")

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
                "name": field.name
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

    def _extract_filters(self, model: type[models.Model]) -> list[dict]:
        """Extract available filters with nested style."""
        filters = []

        # Mapping from Django field types to nested filter input types
        field_to_filter_input = {
            "CharField": "StringFilterInput",
            "TextField": "StringFilterInput",
            "EmailField": "StringFilterInput",
            "URLField": "StringFilterInput",
            "SlugField": "StringFilterInput",
            "IntegerField": "IntFilterInput",
            "SmallIntegerField": "IntFilterInput",
            "BigIntegerField": "IntFilterInput",
            "PositiveIntegerField": "IntFilterInput",
            "AutoField": "IntFilterInput",
            "BigAutoField": "IntFilterInput",
            "FloatField": "FloatFilterInput",
            "DecimalField": "FloatFilterInput",
            "BooleanField": "BooleanFilterInput",
            "NullBooleanField": "BooleanFilterInput",
            "DateField": "DateFilterInput",
            "DateTimeField": "DateTimeFilterInput",
            "UUIDField": "UUIDFilterInput",
            "JSONField": "JSONFilterInput",
            "ForeignKey": "IDFilterInput",
            "OneToOneField": "IDFilterInput",
        }

        # Operators by filter input type
        operators_by_type = {
            "StringFilterInput": [
                "eq", "neq", "contains", "icontains", "starts_with",
                "istarts_with", "ends_with", "iends_with", "in", "not_in",
                "is_null", "regex", "iregex"
            ],
            "IntFilterInput": [
                "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in",
                "between", "is_null"
            ],
            "FloatFilterInput": [
                "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in",
                "between", "is_null"
            ],
            "BooleanFilterInput": ["eq", "is_null"],
            "DateFilterInput": [
                "eq", "neq", "gt", "gte", "lt", "lte", "between", "is_null",
                "year", "month", "day", "week_day", "today", "yesterday",
                "this_week", "past_week", "this_month", "past_month",
                "this_year", "past_year"
            ],
            "DateTimeFilterInput": [
                "eq", "neq", "gt", "gte", "lt", "lte", "between", "is_null",
                "year", "month", "day", "week_day", "hour", "minute", "date",
                "today", "yesterday", "this_week", "past_week", "this_month",
                "past_month", "this_year", "past_year"
            ],
            "IDFilterInput": ["eq", "neq", "in", "not_in", "is_null"],
            "UUIDFilterInput": ["eq", "neq", "in", "not_in", "is_null"],
            "JSONFilterInput": ["eq", "is_null", "has_key", "has_keys", "has_any_keys"],
        }

        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue
            if field.is_relation and not hasattr(field, "related_model"):
                continue

            field_type = type(field).__name__
            options = self._get_filter_options(field_type, field)

            if options:
                filter_input_type = field_to_filter_input.get(field_type)
                available_operators = operators_by_type.get(filter_input_type, [])

                filters.append(
                    {
                        "field_name": field.name,
                        "field_label": str(getattr(field, "verbose_name", field.name)),
                        "is_nested": field.is_relation,
                        "related_model": f"{field.related_model._meta.app_label}.{field.related_model.__name__}"
                        if field.is_relation and hasattr(field, "related_model")
                        else None,
                        "options": options,
                        "filter_input_type": filter_input_type,
                        "available_operators": available_operators,
                    }
                )
        return filters

    def _extract_filter_config(self, model: type[models.Model]) -> dict:
        """Extract filter configuration for the model."""
        model_name = model.__name__

        return {
            "style": "NESTED",
            "argument_name": "where",
            "input_type_name": f"{model_name}WhereInput",
            "supports_and": True,
            "supports_or": True,
            "supports_not": True,
            "dual_mode_enabled": False,
        }

    def _extract_relation_filters(self, model: type[models.Model]) -> list[dict]:
        """Extract relation filter metadata for M2M and reverse relations."""
        relation_filters = []
        for field in model._meta.get_fields():
            if not hasattr(field, "name"):
                continue

            is_m2m = isinstance(field, models.ManyToManyField)
            is_reverse = hasattr(field, "related_model") and not hasattr(field, "remote_field")
            is_reverse_m2m = hasattr(field, "many_to_many") and field.many_to_many
            is_reverse_fk = hasattr(field, "one_to_many") and field.one_to_many

            if is_m2m or is_reverse_m2m or is_reverse_fk:
                related_model = getattr(field, "related_model", None)
                if not related_model:
                    continue

                relation_type = "MANY_TO_MANY" if (is_m2m or is_reverse_m2m) else "REVERSE_FK"

                relation_filters.append({
                    "relation_name": field.name,
                    "relation_type": relation_type,
                    "supports_some": True,
                    "supports_every": True,
                    "supports_none": True,
                    "supports_count": True,
                    "nested_filter_type": f"{related_model.__name__}WhereInput",
                })

        return relation_filters

    def _get_filter_options(self, field_type: str, field: models.Field) -> list[dict]:
        """Get filter options for a field type."""
        base = [
            {
                "name": f"{field.name}",
                "lookup": "exact",
                "help_text": "Égal à",
                "choices": None,
            }
        ]

        if field_type in ("CharField", "TextField", "SlugField"):
            base.extend(
                [
                    {
                        "name": f"{field.name}__icontains",
                        "lookup": "icontains",
                        "help_text": "Contient",
                        "choices": None,
                    },
                    {
                        "name": f"{field.name}__istartswith",
                        "lookup": "istartswith",
                        "help_text": "Commence par",
                        "choices": None,
                    },
                ]
            )
        elif field_type in (
            "IntegerField",
            "FloatField",
            "DecimalField",
            "DateField",
            "DateTimeField",
        ):
            base.extend(
                [
                    {
                        "name": f"{field.name}__gte",
                        "lookup": "gte",
                        "help_text": "Supérieur ou égal",
                        "choices": None,
                    },
                    {
                        "name": f"{field.name}__lte",
                        "lookup": "lte",
                        "help_text": "Inférieur ou égal",
                        "choices": None,
                    },
                ]
            )
        elif field_type == "BooleanField":
            base = [
                {
                    "name": field.name,
                    "lookup": "exact",
                    "help_text": "Est",
                    "choices": [
                        {"value": "true", "label": "Oui"},
                        {"value": "false", "label": "Non"},
                    ],
                }
            ]

        if hasattr(field, "choices") and field.choices:
            choices = [{"value": str(c[0]), "label": str(c[1])} for c in field.choices]
            base[0]["choices"] = choices

        return base

    def _extract_mutations(self, model: type[models.Model], user: Any) -> list[dict]:
        """Extract available mutations."""
        mutations = []
        model_name = model.__name__

        # CRUD mutations
        for op, name in [
            ("CREATE", f"create_{model_name}"),
            ("UPDATE", f"update_{model_name}"),
            ("DELETE", f"delete_{model_name}"),
        ]:
            mutations.append(
                {
                    "name": name,
                    "operation": op,
                    "description": f"{op.title()} a {model._meta.verbose_name}",
                    "method_name": None,
                    "input_fields": [],
                    "allowed": True,
                    "required_permissions": [
                        f"{model._meta.app_label}.{op.lower()}_{model_name.lower()}"
                    ],
                    "reason": None,
                }
            )

        return mutations

    def _extract_permissions(self, model: type[models.Model], user: Any) -> dict:
        """Extract model permissions for user."""
        perms = {
            "can_list": True,
            "can_retrieve": True,
            "can_create": True,
            "can_update": True,
            "can_delete": True,
            "can_bulk_create": True,
            "can_bulk_update": True,
            "can_bulk_delete": True,
            "can_export": True,
            "denial_reasons": {},
        }

        if user and hasattr(user, "has_perm"):
            app = model._meta.app_label
            name = model.__name__.lower()
            perms["can_create"] = user.has_perm(f"{app}.add_{name}")
            perms["can_update"] = user.has_perm(f"{app}.change_{name}")
            perms["can_delete"] = user.has_perm(f"{app}.delete_{name}")
            perms["can_list"] = user.has_perm(f"{app}.view_{name}")
            perms["can_retrieve"] = perms["can_list"]

        return perms

    def _extract_field_groups(
        self, model: type[models.Model], graphql_meta: Any
    ) -> Optional[list[dict]]:
        """Extract field groups from GraphQLMeta."""
        groups = getattr(graphql_meta, "field_groups", None)
        if groups:
            return [
                {
                    "key": g.get("key", ""),
                    "label": g.get("label", ""),
                    "description": g.get("description"),
                    "fields": g.get("fields", []),
                }
                for g in groups
            ]
        return None

    def _extract_templates(self, model: type[models.Model], user: Any) -> list[dict]:
        """Extract available templates."""
        templates = []
        try:
            from .templating import template_registry

            if template_registry:
                model_templates = template_registry.get_templates_for_model(model)
                for key, tmpl in model_templates.items():
                    templates.append(
                        {
                            "key": key,
                            "title": getattr(tmpl, "title", key),
                            "description": getattr(tmpl, "description", None),
                            "endpoint": f"/api/templates/{model._meta.app_label}/{model.__name__}/{key}/",
                        }
                    )
        except Exception:
            pass
        return templates


# =============================================================================
# GraphQL Query
# =============================================================================


class ModelSchemaQueryV2(graphene.ObjectType):
    """
    GraphQL queries for model schema (Metadata V2).

    Provides comprehensive model introspection for frontend UI generation.
    """

    model_schema = graphene.Field(
        ModelSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        model=graphene.String(required=True, description="Model name"),
        object_id=graphene.ID(
            description="Instance ID for instance-specific permissions"
        ),
        description="Get complete schema information for a model.",
    )

    available_models_v2 = graphene.List(
        ModelInfoType,
        app=graphene.String(description="Filter by app"),
        description="List all available models.",
    )

    app_schemas = graphene.List(
        ModelSchemaType,
        app=graphene.String(required=True, description="Django app label"),
        description="Get schemas for all models in an app.",
    )

    def resolve_model_schema(
        self,
        info,
        app: str,
        model: str,
        object_id: Optional[str] = None,
    ) -> dict:
        """
        Resolve complete model schema.

        Args:
            info: GraphQL resolve info.
            app: Django app label.
            model: Model name.
            object_id: Optional instance ID.

        Returns:
            Complete model schema.
        """
        user = getattr(info.context, "user", None)
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        return extractor.extract(app, model, user=user, object_id=object_id)

    def resolve_available_models_v2(
        self, info, app: Optional[str] = None
    ) -> list[dict]:
        """
        Resolve list of available models.

        Args:
            info: GraphQL resolve info.
            app: Optional app filter.

        Returns:
            List of model info dicts.
        """
        results = []
        for model in apps.get_models():
            if app and model._meta.app_label != app:
                continue
            if model._meta.app_label in ("admin", "auth", "contenttypes", "sessions"):
                continue
            results.append(
                {
                    "app": model._meta.app_label,
                    "model": model.__name__,
                    "verbose_name": str(model._meta.verbose_name),
                    "verbose_name_plural": str(model._meta.verbose_name_plural),
                }
            )
        return results

    def resolve_app_schemas(self, info, app: str) -> list[dict]:
        """
        Resolve schemas for all models in an app.

        Args:
            info: GraphQL resolve info.
            app: Django app label.

        Returns:
            List of model schemas.
        """
        user = getattr(info.context, "user", None)
        extractor = ModelSchemaExtractor(
            schema_name=getattr(info.context, "schema_name", "default")
        )
        schemas = []
        for model in apps.get_app_config(app).get_models():
            try:
                schemas.append(extractor.extract(app, model.__name__, user=user))
            except Exception as e:
                logger.warning(
                    f"Error extracting schema for {app}.{model.__name__}: {e}"
                )
        return schemas


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    "ModelSchemaQueryV2",
    "ModelSchemaType",
    "FieldSchemaType",
    "RelationshipSchemaType",
    "MutationSchemaType",
    "FilterSchemaType",
    "FilterConfigType",
    "FilterStyleEnum",
    "FilterOptionSchemaType",
    "RelationFilterSchemaType",
    "ModelPermissionsType",
    "ModelSchemaExtractor",
    "invalidate_metadata_v2_cache",
]

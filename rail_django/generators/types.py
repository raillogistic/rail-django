"""
Type Generation System for Django GraphQL Auto-Generation

This module provides the TypeGenerator class, which is responsible for converting
Django model fields and relationships into GraphQL types.
"""

from datetime import date
from typing import Any, Dict, List, Optional, Type, Union

import graphene
from django.db import models
from django.db.models.fields import Field
from graphene_django import DjangoObjectType
from graphene_django.converter import (
    convert_django_field,
    get_django_field_description,
)
from graphene_django.utils import DJANGO_FILTER_INSTALLED

if DJANGO_FILTER_INSTALLED:
    from django_filters import CharFilter

from ..core.meta import get_model_graphql_meta
from ..core.services import get_query_optimizer
from ..core.scalars import Binary as BinaryScalar
from ..core.scalars import get_custom_scalar, get_enabled_scalars
from ..core.settings import MutationGeneratorSettings, TypeGeneratorSettings
from .introspector import FieldInfo, ModelIntrospector
from .types_dataloaders import RelatedObjectsLoader
from .types_enums import (
    build_enum_name as _build_enum_name,
    get_or_create_enum_for_field as _get_or_create_enum_for_field,
)
from .types_inputs import (
    generate_input_type as _generate_input_type,
    get_or_create_nested_input_type as _get_or_create_nested_input_type,
)
from .types_objects import generate_object_type as _generate_object_type


class TypeGenerator:
    """
    Generates GraphQL types from Django models, including object types,
    input types, and filter types.

    This class supports:
    - Multi-schema type generation
    - Configurable field inclusion/exclusion
    - Custom naming conventions
    - Relationship handling with depth limits
    - Input type generation for mutations
    - Filter type generation for queries
    - Custom scalar types integration
    - Performance optimization
    """

    # Mapping of Django field types to GraphQL scalar types
    FIELD_TYPE_MAP = {
        models.AutoField: graphene.ID,
        models.BigAutoField: graphene.ID,
        models.BigIntegerField: graphene.Int,
        models.BooleanField: graphene.Boolean,
        models.CharField: graphene.String,
        models.DateField: graphene.Date,
        models.DateTimeField: graphene.DateTime,
        models.DecimalField: graphene.Decimal,
        models.EmailField: graphene.String,
        models.FileField: graphene.String,
        models.FloatField: graphene.Float,
        models.ImageField: graphene.String,
        models.IntegerField: graphene.Int,
        models.JSONField: graphene.JSONString,
        models.PositiveIntegerField: graphene.Int,
        models.PositiveSmallIntegerField: graphene.Int,
        models.SlugField: graphene.String,
        models.SmallIntegerField: graphene.Int,
        models.TextField: graphene.String,
        models.BinaryField: graphene.String,
        models.TimeField: graphene.Time,
        models.URLField: graphene.String,
        models.UUIDField: graphene.UUID,
    }

    # Mapping of Python types to GraphQL scalar types for @property methods
    PYTHON_TYPE_MAP = {
        str: graphene.String,
        int: graphene.Int,
        float: graphene.Float,
        bool: graphene.Boolean,
        list: graphene.List,
        dict: graphene.JSONString,
        date: graphene.Date,
        # Add more mappings as needed
    }

    def __init__(
        self,
        settings: Optional[TypeGeneratorSettings] = None,
        mutation_settings: Optional[MutationGeneratorSettings] = None,
        schema_name: str = "default",
    ):
        """
        Initialize the TypeGenerator.

        Args:
            settings: Type generator settings or None for defaults
            mutation_settings: Mutation generator settings or None for defaults
            schema_name: Name of the schema for multi-schema support
        """
        self.schema_name = schema_name

        # Use hierarchical settings if no explicit settings provided
        if settings is None:
            self.settings = TypeGeneratorSettings.from_schema(schema_name)
        else:
            self.settings = settings

        if mutation_settings is None:
            self.mutation_settings = MutationGeneratorSettings.from_schema(schema_name)
        else:
            self.mutation_settings = mutation_settings

        # Initialize performance optimizer
        self.query_optimizer = get_query_optimizer(schema_name)

        # Get enabled custom scalars for this schema
        self.custom_scalars = get_enabled_scalars(schema_name)

        # Update field type map with custom scalars
        self._update_field_type_map()

        # Type registries for caching generated types
        self._type_registry: dict[type[models.Model], type[DjangoObjectType]] = {}
        self._input_type_registry: dict[
            type[models.Model], type[graphene.InputObjectType]
        ] = {}
        self._filter_type_registry: dict[type[models.Model], type] = {}
        self._union_registry: dict[str, type[graphene.Union]] = {}
        self._interface_registry: dict[
            type[models.Model], type[graphene.Interface]
        ] = {}
        # Registry for generated GraphQL Enums for choice fields
        self._enum_registry: dict[str, type[graphene.Enum]] = {}
        self._meta_cache: dict[type[models.Model], Any] = {}

    def _update_field_type_map(self) -> None:
        """Update field type map with custom scalars based on settings."""
        # Apply custom field mappings from settings
        if (
            hasattr(self.settings, "custom_field_mappings")
            and self.settings.custom_field_mappings
        ):
            for (
                django_field,
                graphql_type,
            ) in self.settings.custom_field_mappings.items():
                if isinstance(graphql_type, str):
                    # Try to get custom scalar
                    custom_scalar = get_custom_scalar(graphql_type)
                    if custom_scalar:
                        self.FIELD_TYPE_MAP[django_field] = custom_scalar
                else:
                    self.FIELD_TYPE_MAP[django_field] = graphql_type

        # Apply custom scalars based on field types
        if "Email" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.EmailField] = self.custom_scalars["Email"]

        if "URL" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.URLField] = self.custom_scalars["URL"]

        if "UUID" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.UUIDField] = self.custom_scalars["UUID"]

        if "DateTime" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.DateTimeField] = self.custom_scalars["DateTime"]

        if "Date" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.DateField] = self.custom_scalars["Date"]

        if "Time" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.TimeField] = self.custom_scalars["Time"]

        if "JSON" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.JSONField] = self.custom_scalars["JSON"]

        if "Decimal" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.DecimalField] = self.custom_scalars["Decimal"]

        if "Binary" in self.custom_scalars:
            self.FIELD_TYPE_MAP[models.BinaryField] = self.custom_scalars["Binary"]

    def _get_excluded_fields(self, model: type[models.Model]) -> list[str]:
        """Get excluded fields for a specific model.

        Filters out names that are not real Django model fields to avoid Graphene warnings
        (e.g., excluding reverse relations like 'user_set' or non-existent fields).
        """
        model_name = model.__name__
        excluded: set[str] = set()

        # Introspect actual model fields once
        from rail_django.generators.introspector import ModelIntrospector

        introspector = ModelIntrospector.for_model(model)
        all_fields = introspector.get_model_fields()
        valid_field_names = set(all_fields.keys())

        # Exclude polymorphic internal field only if present on this model
        if "polymorphic_ctype" in valid_field_names:
            excluded.add("polymorphic_ctype")

        # Also exclude any field ending with '_ptr' which are typically OneToOneField pointers in inheritance
        for field_name in valid_field_names:
            if field_name.endswith("_ptr"):
                excluded.add(field_name)

        # Check both exclude_fields and excluded_fields (alias)
        # Handle case where settings might be a list instead of dict
        configured_excludes: set[str] = set()
        if isinstance(self.settings.exclude_fields, dict):
            configured_excludes.update(self.settings.exclude_fields.get(model_name, []))
        elif isinstance(self.settings.exclude_fields, list):
            configured_excludes.update(self.settings.exclude_fields)

        if isinstance(self.settings.excluded_fields, dict):
            configured_excludes.update(
                self.settings.excluded_fields.get(model_name, [])
            )
        elif isinstance(self.settings.excluded_fields, list):
            configured_excludes.update(self.settings.excluded_fields)

        # Only keep excludes that match actual model fields to prevent noisy warnings
        excluded.update(
            name for name in configured_excludes if name in valid_field_names
        )
        meta = self._get_model_meta(model)
        if meta:
            excluded.update(
                name
                for name in getattr(meta, "exclude_fields", []) or []
                if name in valid_field_names
            )
        return list(sorted(excluded))

    def _get_included_fields(self, model: type[models.Model]) -> Optional[list[str]]:
        """Get included fields for a specific model."""
        meta = self._get_model_meta(model)
        if meta and meta.include_fields is not None:
            valid_field_names = {
                f.name for f in model._meta.get_fields() if hasattr(f, "name")
            }
            return [name for name in meta.include_fields if name in valid_field_names]
        if self.settings.include_fields is None:
            return None
        include_list = self.settings.include_fields.get(model.__name__, None)
        if include_list is None:
            return None
        return list(include_list)

    def _get_model_meta(self, model: type[models.Model]) -> Any:
        """
        Retrieve (and cache) the GraphQL meta helper for a model.
        """
        if model not in self._meta_cache:
            try:
                self._meta_cache[model] = get_model_graphql_meta(model)
            except Exception:
                self._meta_cache[model] = None
        return self._meta_cache[model]

    def _get_maskable_fields(self, model: type[models.Model]) -> set:
        meta = self._get_model_meta(model)
        if not meta or not getattr(meta, "access_config", None):
            return set()
        maskable: set = set()
        for rule in getattr(meta.access_config, "fields", []):
            visibility = getattr(rule, "visibility", "visible")
            access = getattr(rule, "access", "read")
            if str(visibility).lower() in {"hidden", "masked", "redacted"} or str(
                access
            ).lower() not in {"read", "all"}:
                maskable.add(rule.field)
        return maskable

    def _should_field_be_required_for_create(
        self,
        field_info: "FieldInfo",
        field_name: str = None,
        model: type[models.Model] = None,
    ) -> bool:
        """
        Determine if a field should be required for create mutations based on:
        - auto_now and auto_now_add fields are not required (automatically set)
        - fields with defaults are not required (Django will use the default)
        - fields with blank=True are not required (can be empty)
        - fields with blank=False AND no default ARE required
        - id/primary key fields are not required for create (auto-generated)
        - mandatory fields defined by _get_mandatory_fields are always required
        """
        # Check if this field is mandatory for this model
        if model and field_name:
            mandatory_fields = self._get_mandatory_fields(model)
            if field_name in mandatory_fields:
                return True

        # Primary key fields (id, pk) are not required for create
        if field_name and field_name in ("id", "pk"):
            return False

        # auto_now and auto_now_add fields are automatically set
        if field_info.has_auto_now or field_info.has_auto_now_add:
            return False

        # Fields with defaults don't need to be provided
        if field_info.has_default:
            return False

        # Fields with blank=True can be left empty, so not required
        if field_info.blank:
            return False

        # Fields with blank=False (default) and no default value are required
        return True

    def _should_field_be_required_for_update(
        self, field_name: str, field_info: Any, model: type[models.Model] = None
    ) -> bool:
        """
        Determine if a field should be required for update mutations.
        - mandatory fields defined by _get_mandatory_fields are always required
        - id is required at the mutation argument level, not in the input payload
        """
        # Check if this field is mandatory for this model
        if model and field_name:
            mandatory_fields = self._get_mandatory_fields(model)
            if field_name in mandatory_fields:
                return True

        return field_name == "id"

    def _get_mandatory_fields(self, model: type[models.Model]) -> list[str]:
        """
        Get list of mandatory fields for a specific model.
        These fields are always required in input types regardless of Django field settings.

        Args:
            model: The Django model to get mandatory fields for

        Returns:
            List of field names that are mandatory for this model
        """
        # Define mandatory fields per model

        return []

    def _should_include_field(
        self, model: type[models.Model], field_name: str, *, for_input: bool = False
    ) -> bool:
        # Exclude polymorphic model internal fields
        # These fields are automatically managed by django-polymorphic and should not be exposed in mutations
        polymorphic_fields = {"polymorphic_ctype"}
        # Also exclude any field ending with '_ptr' which are typically OneToOneField pointers in inheritance
        if field_name in polymorphic_fields or field_name.endswith("_ptr"):
            return False

        excluded_fields = self._get_excluded_fields(model)
        if field_name in excluded_fields:
            return False

        included_fields = self._get_included_fields(model)
        if included_fields is not None:
            return field_name in included_fields

        meta = self._get_model_meta(model)
        if meta and not meta.should_expose_field(field_name, for_input=for_input):
            return False

        return True

    def _get_graphql_type_for_property(self, return_type: Any) -> graphene.Field:
        """
        Convert a Python return type annotation to a GraphQL field type.

        Args:
            return_type: The return type annotation from a @property method

        Returns:
            GraphQL field with appropriate type
        """
        # Handle typing.Any or no annotation
        if return_type is Any or return_type is None:
            return graphene.String()

        # Handle basic Python types
        if return_type in self.PYTHON_TYPE_MAP:
            graphql_type = self.PYTHON_TYPE_MAP[return_type]
            # Special handling for List type which requires of_type parameter
            if graphql_type == graphene.List:
                return graphene.List(graphene.String)
            return graphql_type()

        # Handle typing generics like List[str], Optional[int], etc.
        origin = getattr(return_type, "__origin__", None)
        if origin is not None:
            if origin is list or origin is list:
                # Handle List[SomeType]
                args = getattr(return_type, "__args__", ())
                if args:
                    inner_type = self._get_graphql_type_for_property(args[0])
                    # If inner_type is a Field, extract its type
                    if hasattr(inner_type, "_type"):
                        return graphene.List(inner_type._type)
                    return graphene.List(inner_type)
                return graphene.List(graphene.String)
            elif origin is Union:
                # Handle Optional[SomeType] which is Union[SomeType, None]
                args = getattr(return_type, "__args__", ())
                if len(args) == 2 and type(None) in args:
                    # This is Optional[SomeType]
                    non_none_type = args[0] if args[1] is type(None) else args[1]
                    return self._get_graphql_type_for_property(non_none_type)

        # Default to String for unknown types
        return graphene.String()

    def generate_object_type(self, model: type[models.Model]) -> type[DjangoObjectType]:
        return _generate_object_type(self, model)

    def generate_input_type(
        self,
        model: type[models.Model],
        mutation_type: str = "create",
        partial: bool = False,
        include_reverse_relations: bool = True,
    ) -> type[graphene.InputObjectType]:
        return _generate_input_type(
            self,
            model,
            mutation_type=mutation_type,
            partial=partial,
            include_reverse_relations=include_reverse_relations,
        )

    def _build_enum_name(self, model: type[models.Model], field_name: str) -> str:
        return _build_enum_name(self, model, field_name)

    def _get_or_create_enum_for_field(
        self, model: type[models.Model], django_field: Field
    ) -> Optional[type[graphene.Enum]]:
        return _get_or_create_enum_for_field(self, model, django_field)

    def generate_filter_type(self, model: type[models.Model]) -> type:
        """
        Generates a filter type for the model if Django-filter is installed.
        Configures available filter operations based on field types.
        """
        if not DJANGO_FILTER_INSTALLED or not self.settings.generate_filters:
            return None

        if model in self._filter_type_registry:
            return self._filter_type_registry[model]

        from django_filters import FilterSet

        introspector = ModelIntrospector.for_model(model)
        fields = introspector.get_model_fields()

        # Define filter fields
        filter_fields = {}
        for field_name, field_info in fields.items():
            if not self._should_include_field(model, field_name):
                continue

            filter_type = self._get_filter_field_type(field_info.field_type)
            if filter_type:
                filter_fields[field_name] = filter_type

        # Apply GraphQLMeta.filtering.fields overrides:
        # - If a field is explicitly mentioned with non-empty lookups, restrict to those
        # - If a field is not mentioned or lookups list is empty, keep all available filters
        try:
            graphql_meta = get_model_graphql_meta(model)
            configured_fields = (
                getattr(graphql_meta, "filtering").fields if graphql_meta else {}
            )
            if configured_fields:
                for fname in list(filter_fields.keys()):
                    cfg = configured_fields.get(fname)
                    if cfg and cfg.lookups:
                        # Only keep the explicitly allowed lookups for this field
                        allowed = list(cfg.lookups)
                        # Ensure we only include lookups that actually exist for the field type
                        existing = set(filter_fields.get(fname, []))
                        filter_fields[fname] = [lk for lk in allowed if lk in existing]
                    # If cfg exists but lookups is empty or None, leave defaults (include all available)
        except Exception:
            # Be defensive: any issues retrieving meta should not break filter generation
            pass

        # Create the filter set class
        class_name = f"{model.__name__}Filter"

        # Add filter overrides for file fields
        filter_overrides = {
            models.FileField: {
                "filter_class": CharFilter,
                "extra": lambda f: {"lookup_expr": "exact"},
            },
            models.ImageField: {
                "filter_class": CharFilter,
                "extra": lambda f: {"lookup_expr": "exact"},
            },
        }

        meta_class = type(
            "Meta",
            (),
            {
                "model": model,
                "fields": filter_fields,
                "filter_overrides": filter_overrides,
            },
        )

        filter_class = type(
            class_name,
            (FilterSet,),
            {
                "Meta": meta_class,
                "__doc__": f"Filter set for {model.__name__} queries.",
            },
        )

        self._filter_type_registry[model] = filter_class
        return filter_class

    def _get_input_field_type(
        self, django_field_type: type[Field]
    ) -> Optional[type[graphene.Scalar]]:
        """Maps Django field types to GraphQL input field types."""
        return self.FIELD_TYPE_MAP.get(django_field_type)

    def _get_filter_field_type(self, django_field_type: type[Field]) -> list[str]:
        """Determines available filter operations for a field type."""
        base_filters = ["exact", "in", "isnull"]
        text_filters = [
            "contains",
            "icontains",
            "startswith",
            "istartswith",
            "endswith",
            "iendswith",
        ]
        number_filters = ["gt", "gte", "lt", "lte", "range"]

        if issubclass(django_field_type, (models.CharField, models.TextField)):
            return base_filters + text_filters
        elif issubclass(
            django_field_type,
            (models.IntegerField, models.FloatField, models.DecimalField),
        ):
            return base_filters + number_filters
        elif issubclass(django_field_type, (models.DateField, models.DateTimeField)):
            return base_filters + number_filters + ["year", "month", "day"]
        else:
            return base_filters

    def _get_filterable_fields(self, model: type[models.Model]) -> dict[str, list[str]]:
        """
        Determines which fields should be filterable and what operations are available.
        """
        introspector = ModelIntrospector.for_model(model)
        fields = introspector.get_model_fields()

        filterable_fields = {}
        for field_name, field_info in fields.items():
            if self._should_include_field(model, field_name):
                filter_ops = self._get_filter_field_type(field_info.field_type)
                if filter_ops:
                    filterable_fields[field_name] = filter_ops

        return filterable_fields

    def handle_custom_fields(self, field: Field) -> type[graphene.Scalar]:
        """
        Handles custom field types by attempting to map them to appropriate GraphQL types.
        Falls back to String if no specific mapping is found.
        """
        # Check if there's a custom mapping defined in settings
        if self.settings.custom_field_mappings:
            field_type = type(field)
            if field_type in self.settings.custom_field_mappings:
                return self.settings.custom_field_mappings[field_type]

        # Default to String for unknown field types
        return graphene.String

    def _is_historical_model(self, model: type[models.Model]) -> bool:
        """Return True if the model is generated by django-simple-history."""
        try:
            name = getattr(model, "__name__", "")
            module = getattr(model, "__module__", "")
        except Exception:
            return False
        if name.startswith("Historical"):
            return True
        if "simple_history" in module:
            return True
        return False

    def _get_reverse_relations(
        self, model: type[models.Model]
    ) -> dict[str, dict[str, Any]]:
        """
        Get reverse relationships for a model (e.g., comments for Post).

        Returns:
            Dict mapping field names to related models
        """
        reverse_relations: dict[str, dict[str, Any]] = {}

        # For modern Django versions, use related_objects
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                # Get the accessor name (e.g., 'comments' for Comment.post -> Post)
                accessor_name = rel.get_accessor_name()

                # Skip if accessor name is in excluded fields
                if not self._should_include_field(model, accessor_name):
                    continue

                # Skip reverse relations that point to historical models or history accessors
                if self._is_historical_model(rel.related_model):
                    continue
                if accessor_name.startswith("history") or accessor_name.startswith(
                    "historical"
                ):
                    continue
                reverse_relations[accessor_name] = {
                    "model": rel.related_model,
                    "relation": rel,
                }
        # Fallback for Django versions that use get_fields() with related fields
        elif hasattr(model._meta, "get_fields"):
            try:
                for field in model._meta.get_fields():
                    # Check if it's a reverse relation (ForeignKey, OneToOneField, ManyToManyField)
                    if hasattr(field, "related_model") and hasattr(
                        field, "get_accessor_name"
                    ):
                        accessor_name = field.get_accessor_name()

                        if self._should_include_field(model, accessor_name):
                            if self._is_historical_model(field.related_model):
                                continue
                            if accessor_name.startswith(
                                "history"
                            ) or accessor_name.startswith("historical"):
                                continue
                            reverse_relations[accessor_name] = {
                                "model": field.related_model,
                                "relation": field,
                            }
            except AttributeError:
                # If get_fields doesn't work as expected, continue without reverse relations
                pass
        else:
            # Final fallback for very old Django versions
            try:
                for rel in model._meta.get_all_related_objects():
                    if hasattr(rel, "get_accessor_name"):
                        accessor_name = rel.get_accessor_name()
                    else:
                        accessor_name = rel.name

                    if self._should_include_field(model, accessor_name):
                        if self._is_historical_model(rel.related_model):
                            continue
                        if accessor_name.startswith(
                            "history"
                        ) or accessor_name.startswith("historical"):
                            continue
                        reverse_relations[accessor_name] = {
                            "model": rel.related_model,
                            "relation": rel,
                        }
            except AttributeError:
                # If get_all_related_objects doesn't exist, skip reverse relations
                pass

        return reverse_relations

    def _get_relation_dataloader(
        self,
        context: Any,
        related_model: type[models.Model],
        relation: Any,
        state: Any,
    ):
        """Return a cached DataLoader for a reverse foreign key relation."""
        if not RelatedObjectsLoader or not context or relation is None:
            return None

        try:
            from django.db.models.fields.reverse_related import ManyToOneRel

            if not isinstance(relation, ManyToOneRel):
                return None
        except Exception:
            return None

        relation_field = getattr(relation.field, "name", None)
        if not relation_field:
            return None

        db_alias = getattr(state, "db", None)
        loader_key = f"reverse:{related_model._meta.label_lower}:{relation_field}:{db_alias or 'default'}"

        if not hasattr(context, "_rail_dataloaders"):
            context._rail_dataloaders = {}

        if loader_key not in context._rail_dataloaders:
            context._rail_dataloaders[loader_key] = RelatedObjectsLoader(
                related_model, relation_field, db_alias
            )

        return context._rail_dataloaders[loader_key]

    def _get_or_create_nested_input_type(
        self,
        model: type[models.Model],
        mutation_type: str = "create",
        exclude_parent_field: Optional[type[models.Model]] = None,
    ) -> type[graphene.InputObjectType]:
        return _get_or_create_nested_input_type(
            self,
            model,
            mutation_type=mutation_type,
            exclude_parent_field=exclude_parent_field,
        )

    def _should_include_nested_relations(self, model: type[models.Model]) -> bool:
        """
        Check if nested relations should be included for this model.

        Args:
            model: The Django model to check

        Returns:
            bool: True if nested relations should be included
        """
        model_name = model.__name__

        # Check global setting first
        if not self.mutation_settings.enable_nested_relations:
            return False

        # Check per-model configuration
        if model_name in self.mutation_settings.nested_relations_config:
            return self.mutation_settings.nested_relations_config[model_name]

        # Default to enabled if no specific configuration
        return True

    def _should_include_nested_field(
        self, model: type[models.Model], field_name: str
    ) -> bool:
        """
        Check if a specific nested field should be included for this model.

        Args:
            model: The Django model
            field_name: The field name to check

        Returns:
            bool: True if the nested field should be included
        """
        model_name = model.__name__

        # Check per-field configuration
        if model_name in self.mutation_settings.nested_field_config:
            field_config = self.mutation_settings.nested_field_config[model_name]
            if field_name in field_config:
                return field_config[field_name]

        # Check per-model configuration
        if model_name in self.mutation_settings.nested_relations_config:
            return self.mutation_settings.nested_relations_config[model_name]

        # Check global configuration
        if hasattr(self.mutation_settings, "enable_nested_relations"):
            return self.mutation_settings.enable_nested_relations

        # Default to ID-based operations when no configuration is specified
        return False

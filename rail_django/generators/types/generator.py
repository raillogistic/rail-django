"""
TypeGenerator implementation.
"""

import logging
from typing import Any, Dict, List, Optional, Type, Union

import graphene
from django.db import models
from django.db.models.fields import Field
from graphene_django import DjangoObjectType
from graphene_django.utils import DJANGO_FILTER_INSTALLED
from graphene_django.converter import convert_django_field
from graphql import GraphQLError

# Django 5.0+ GeneratedField support
try:
    from django.db.models import GeneratedField

    @convert_django_field.register(GeneratedField)
    def convert_generated_field(field, registry=None):
        return convert_django_field(field.output_field, registry)
except ImportError:
    pass

if DJANGO_FILTER_INSTALLED:
    from django_filters import CharFilter, FilterSet

from ...core.meta import get_model_graphql_meta
from ...core.services import get_query_optimizer
from ...core.scalars import get_custom_scalar, get_enabled_scalars
from ...core.settings import MutationGeneratorSettings, TypeGeneratorSettings
from ..introspector import ModelIntrospector
from .dataloaders import RelatedObjectsLoader
from .enums import (
    build_enum_name as _build_enum_name,
    get_or_create_enum_for_field as _get_or_create_enum_for_field,
)
from .inputs import (
    generate_input_type as _generate_input_type,
)
from .relations import RelationInputTypeGenerator
from .relation_config import FieldRelationConfig as GeneratorFieldRelationConfig
from .relation_config import RelationOperationConfig as GeneratorRelationOperationConfig
from .objects import (
    generate_object_type as _generate_object_type,
)

from .constants import FIELD_TYPE_MAP, PYTHON_TYPE_MAP

logger = logging.getLogger(__name__)


class TypeGenerator:
    """
    Generates GraphQL types from Django models.
    """

    FIELD_TYPE_MAP = FIELD_TYPE_MAP.copy()
    PYTHON_TYPE_MAP = PYTHON_TYPE_MAP.copy()

    def __init__(
        self,
        settings: Optional[TypeGeneratorSettings] = None,
        mutation_settings: Optional[MutationGeneratorSettings] = None,
        schema_name: str = "default",
    ):
        self.schema_name = schema_name

        if settings is None:
            self.settings = TypeGeneratorSettings.from_schema(schema_name)
        else:
            self.settings = settings

        if mutation_settings is None:
            self.mutation_settings = MutationGeneratorSettings.from_schema(schema_name)
        else:
            self.mutation_settings = mutation_settings

        self.query_optimizer = get_query_optimizer(schema_name)
        self.custom_scalars = get_enabled_scalars(schema_name)
        self._update_field_type_map()

        self._type_registry: dict[type[models.Model], type[DjangoObjectType]] = {}
        self._input_type_registry: dict[
            type[models.Model], type[graphene.InputObjectType]
        ] = {}
        self._filter_type_registry: dict[type[models.Model], type] = {}
        self._union_registry: dict[str, type[graphene.Union]] = {}
        self._interface_registry: dict[
            type[models.Model], type[graphene.Interface]
        ] = {}
        self._enum_registry: dict[str, type[graphene.Enum]] = {}
        self._meta_cache: dict[type[models.Model], Any] = {}
        
        self.relation_input_generator = RelationInputTypeGenerator(self)

    def _update_field_type_map(self) -> None:
        """Update field type map with custom scalars based on settings."""
        if (
            hasattr(self.settings, "custom_field_mappings")
            and self.settings.custom_field_mappings
        ):
            for (
                django_field,
                graphql_type,
            ) in self.settings.custom_field_mappings.items():
                if isinstance(graphql_type, str):
                    custom_scalar = get_custom_scalar(graphql_type)
                    if custom_scalar:
                        self.FIELD_TYPE_MAP[django_field] = custom_scalar
                else:
                    self.FIELD_TYPE_MAP[django_field] = graphql_type

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
        """Get excluded fields for a specific model."""
        model_name = model.__name__
        excluded: set[str] = set()

        introspector = ModelIntrospector.for_model(model)
        all_fields = introspector.get_model_fields()
        valid_field_names = set(all_fields.keys())

        if "polymorphic_ctype" in valid_field_names:
            excluded.add("polymorphic_ctype")

        for field_name in valid_field_names:
            if field_name.endswith("_ptr"):
                excluded.add(field_name)

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
        """Retrieve (and cache) the GraphQL meta helper for a model."""
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
        field_info: Any,
        field_name: str = None,
        model: type[models.Model] = None,
    ) -> bool:
        if model and field_name:
            mandatory_fields = self._get_mandatory_fields(model)
            if field_name in mandatory_fields:
                return True
        if field_name and field_name in ("id", "pk"):
            return False
        if field_info.has_auto_now or field_info.has_auto_now_add:
            return False
        if field_info.has_default:
            return False
        if field_info.blank:
            return False
        return True

    def _should_field_be_required_for_update(
        self, field_name: str, field_info: Any, model: type[models.Model] = None
    ) -> bool:
        if model and field_name:
            mandatory_fields = self._get_mandatory_fields(model)
            if field_name in mandatory_fields:
                return True
        return field_name == "id"

    def _get_mandatory_fields(self, model: type[models.Model]) -> list[str]:
        return []

    def _should_include_field(
        self, model: type[models.Model], field_name: str, *, for_input: bool = False
    ) -> bool:
        polymorphic_fields = {"polymorphic_ctype"}
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
        """Convert a Python return type annotation to a GraphQL field type."""
        if return_type is Any or return_type is None:
            return graphene.String()
        if return_type in self.PYTHON_TYPE_MAP:
            graphql_type = self.PYTHON_TYPE_MAP[return_type]
            if graphql_type == graphene.List:
                return graphene.List(graphene.String)
            return graphql_type()
        origin = getattr(return_type, "__origin__", None)
        if origin is not None:
            if origin is list or origin is list:
                args = getattr(return_type, "__args__", ())
                if args:
                    inner_type = self._get_graphql_type_for_property(args[0])
                    if hasattr(inner_type, "_type"):
                        return graphene.List(inner_type._type)
                    return graphene.List(inner_type)
                return graphene.List(graphene.String)
            elif origin is Union:
                args = getattr(return_type, "__args__", ())
                if len(args) == 2 and type(None) in args:
                    non_none_type = args[0] if args[1] is type(None) else args[1]
                    return self._get_graphql_type_for_property(non_none_type)
        return graphene.String()

    def generate_object_type(self, model: type[models.Model]) -> type[DjangoObjectType]:
        return _generate_object_type(self, model)

    def generate_input_type(
        self,
        model: type[models.Model],
        mutation_type: str = "create",
        partial: bool = False,
        include_reverse_relations: bool = True,
        exclude_fields: Optional[List[str]] = None,
        depth: int = 0,
    ) -> type[graphene.InputObjectType]:
        return _generate_input_type(
            self,
            model,
            mutation_type=mutation_type,
            partial=partial,
            include_reverse_relations=include_reverse_relations,
            exclude_fields=exclude_fields,
            depth=depth,
        )

    def _build_enum_name(self, model: type[models.Model], field_name: str) -> str:
        return _build_enum_name(self, model, field_name)

    def _get_or_create_enum_for_field(
        self, model: type[models.Model], django_field: Field
    ) -> Optional[type[graphene.Enum]]:
        return _get_or_create_enum_for_field(self, model, django_field)

    def generate_filter_type(self, model: type[models.Model]) -> type:
        """Generates a filter type for the model if Django-filter is installed."""
        if not DJANGO_FILTER_INSTALLED or not self.settings.generate_filters:
            return None
        if model in self._filter_type_registry:
            return self._filter_type_registry[model]

        introspector = ModelIntrospector.for_model(model)
        fields = introspector.get_model_fields()
        filter_fields = {}
        for field_name, field_info in fields.items():
            if not self._should_include_field(model, field_name):
                continue
            filter_type = self._get_filter_field_type(field_info.field_type)
            if filter_type:
                filter_fields[field_name] = filter_type

        try:
            graphql_meta = get_model_graphql_meta(model)
            configured_fields = (
                getattr(graphql_meta, "filtering").fields if graphql_meta else {}
            )
            if configured_fields:
                operator_map = {
                    "eq": "exact", "is_null": "isnull", "between": "range",
                    "starts_with": "startswith", "istarts_with": "istartswith",
                    "ends_with": "endswith", "iends_with": "iendswith",
                }
                def normalize_lookups(lookups: list[str]) -> list[str]:
                    normalized = []
                    for lookup in lookups:
                        if lookup is None: continue
                        key = str(lookup)
                        normalized.append(operator_map.get(key, key))
                    return normalized
                for fname in list(filter_fields.keys()):
                    cfg = configured_fields.get(fname)
                    if cfg and cfg.lookups:
                        allowed = normalize_lookups(list(cfg.lookups))
                        existing = set(filter_fields.get(fname, []))
                        filter_fields[fname] = [lk for lk in allowed if lk in existing]
        except Exception:
            pass

        class_name = f"{model.__name__}Filter"
        filter_overrides = {
            models.FileField: {"filter_class": CharFilter, "extra": lambda f: {"lookup_expr": "exact"}},
            models.ImageField: {"filter_class": CharFilter, "extra": lambda f: {"lookup_expr": "exact"}},
        }
        meta_class = type("Meta", (), {"model": model, "fields": filter_fields, "filter_overrides": filter_overrides})
        filter_class = type(class_name, (FilterSet,), {"Meta": meta_class, "__doc__": f"Filter set for {model.__name__} queries."})
        self._filter_type_registry[model] = filter_class
        return filter_class

    def _get_input_field_type(self, django_field_type: type[Field]) -> Optional[type[graphene.Scalar]]:
        return self.FIELD_TYPE_MAP.get(django_field_type)

    def _get_filter_field_type(self, django_field_type: type[Field]) -> list[str]:
        base_filters = ["exact", "in", "isnull"]
        text_filters = ["contains", "icontains", "startswith", "istartswith", "endswith", "iendswith"]
        number_filters = ["gt", "gte", "lt", "lte", "range"]
        if issubclass(django_field_type, (models.CharField, models.TextField)):
            return base_filters + text_filters
        elif issubclass(django_field_type, (models.IntegerField, models.FloatField, models.DecimalField)):
            return base_filters + number_filters
        elif issubclass(django_field_type, (models.DateField, models.DateTimeField)):
            return base_filters + number_filters + ["year", "month", "day"]
        else:
            return base_filters

    def _get_filterable_fields(self, model: type[models.Model]) -> dict[str, list[str]]:
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
        if self.settings.custom_field_mappings:
            field_type = type(field)
            if field_type in self.settings.custom_field_mappings:
                return self.settings.custom_field_mappings[field_type]
        return graphene.String

    def _is_historical_model(self, model: type[models.Model]) -> bool:
        try:
            name = getattr(model, "__name__", "")
            module = getattr(model, "__module__", "")
        except Exception:
            return False
        if name.startswith("Historical") or "simple_history" in module:
            return True
        return False

    def _get_reverse_relations(self, model: type[models.Model]) -> dict[str, dict[str, Any]]:
        reverse_relations: dict[str, dict[str, Any]] = {}
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                accessor_name = rel.get_accessor_name()
                if not self._should_include_field(model, accessor_name):
                    continue
                if self._is_historical_model(rel.related_model):
                    continue
                if accessor_name.startswith("history") or accessor_name.startswith("historical"):
                    continue
                reverse_relations[accessor_name] = {"model": rel.related_model, "relation": rel}
        return reverse_relations

    def _get_relation_dataloader(self, context: Any, related_model: type[models.Model], relation: Any, state: Any):
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
        tenant_field, tenant_id, tenant_settings = self._get_tenant_filter_for_model(context, related_model)
        if tenant_settings and tenant_settings.require_tenant and tenant_field and tenant_id is None:
            return None
        tenant_key = "none" if tenant_id is None else str(tenant_id)
        loader_key = f"reverse:{related_model._meta.label_lower}:{relation_field}:{db_alias or 'default'}:{tenant_key}"
        if not hasattr(context, "_rail_dataloaders"):
            context._rail_dataloaders = {}
        if loader_key not in context._rail_dataloaders:
            context._rail_dataloaders[loader_key] = RelatedObjectsLoader(related_model, relation_field, db_alias, tenant_field=tenant_field, tenant_id=tenant_id)
        return context._rail_dataloaders[loader_key]

    def _apply_tenant_scope(self, queryset: models.QuerySet, info: Any, model: type[models.Model], *, operation: str = "read") -> models.QuerySet:
        try:
            from ...extensions.multitenancy import apply_tenant_queryset
            return apply_tenant_queryset(queryset, info, model, schema_name=self.schema_name, operation=operation)
        except GraphQLError:
            raise
        except Exception as e:
            logger.warning(f"Failed to apply tenant scope: {e}")
            return queryset

    def _get_tenant_filter_for_model(self, context: Any, model: type[models.Model]) -> tuple[Optional[str], Optional[Any], Optional[Any]]:
        try:
            from ...extensions.multitenancy import get_multitenancy_settings, get_tenant_field_config, resolve_tenant_id
            settings_mt = get_multitenancy_settings(self.schema_name)
            if not settings_mt.enabled or settings_mt.isolation_mode != "row":
                return None, None, settings_mt
            tenant_field = get_tenant_field_config(model, schema_name=self.schema_name)
            if tenant_field is None:
                return None, None, settings_mt
            user = getattr(context, "user", None)
            if settings_mt.allow_cross_tenant_superuser and user and user.is_superuser:
                return None, None, settings_mt
            tenant_id = resolve_tenant_id(context, schema_name=self.schema_name)
            return tenant_field.path, tenant_id, settings_mt
        except Exception:
            return None, None, None

    def _should_include_nested_relations(self, model: type[models.Model]) -> bool:
        model_name = model.__name__
        if not self.mutation_settings.enable_nested_relations:
            return False
        if model_name in self.mutation_settings.nested_relations_config:
            return self.mutation_settings.nested_relations_config[model_name]
        return True

    def _should_include_nested_field(self, model: type[models.Model], field_name: str) -> bool:
        model_name = model.__name__
        if model_name in self.mutation_settings.nested_relations_config:
            return self.mutation_settings.nested_relations_config[model_name]
        return getattr(self.mutation_settings, "enable_nested_relations", False)

    def _resolve_relation_config(
        self, model: type[models.Model], field_name: str
    ) -> Optional[GeneratorFieldRelationConfig]:
        """Resolve per-field relation config, applying nested relation settings."""
        meta = self._get_model_meta(model)
        base_cfg = None
        if meta:
            try:
                base_cfg = meta.get_relation_config(field_name)
            except Exception:
                base_cfg = None

        def clone_op(op_cfg: Any) -> GeneratorRelationOperationConfig:
            enabled = True
            require_permission = None
            if op_cfg is not None:
                enabled = bool(getattr(op_cfg, "enabled", True))
                require_permission = getattr(op_cfg, "require_permission", None)
            return GeneratorRelationOperationConfig(
                enabled=enabled, require_permission=require_permission
            )

        cfg = None
        if base_cfg is not None:
            cfg = GeneratorFieldRelationConfig(
                style=getattr(base_cfg, "style", "unified"),
                connect=clone_op(getattr(base_cfg, "connect", None)),
                create=clone_op(getattr(base_cfg, "create", None)),
                update=clone_op(getattr(base_cfg, "update", None)),
                disconnect=clone_op(getattr(base_cfg, "disconnect", None)),
                set=clone_op(getattr(base_cfg, "set", None)),
            )

        if not self._should_include_nested_field(model, field_name):
            if cfg is None:
                cfg = GeneratorFieldRelationConfig()
            cfg.create.enabled = False
            cfg.update.enabled = False

        return cfg

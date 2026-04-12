"""
ModelIntrospector implementation.
"""

import inspect
import threading
import weakref
from typing import Any, Dict, Optional, Union

from django.db import models
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from django.utils.functional import cached_property

from .types import (
    CustomFieldInfo,
    FieldInfo,
    InheritanceInfo,
    ManagerInfo,
    MethodInfo,
    PropertyInfo,
    RelationshipInfo,
)
from .methods import MethodAnalyzerMixin
from .relationships import RelationshipDiscoveryMixin


class ModelIntrospector(MethodAnalyzerMixin, RelationshipDiscoveryMixin):
    """
    Analyzes Django models to extract metadata for GraphQL schema generation.
    """

    def __init__(self, model: type[models.Model], schema_name: Optional[str] = None):
        self.model = model
        self.schema_name = schema_name or "default"
        self._meta = getattr(model, "_meta", None)

    _cache: "weakref.WeakKeyDictionary[type[models.Model], dict[str, ModelIntrospector]]" = (
        weakref.WeakKeyDictionary()
    )
    _cache_lock = threading.Lock()

    @classmethod
    def for_model(
        cls, model: type[models.Model], schema_name: Optional[str] = None
    ) -> "ModelIntrospector":
        schema_key = schema_name or "default"
        with cls._cache_lock:
            per_model = cls._cache.get(model)
            if per_model is None:
                per_model = {}
                cls._cache[model] = per_model
            cached = per_model.get(schema_key)
            if cached is not None: return cached
            instance = cls(model, schema_name=schema_key)
            per_model[schema_key] = instance
            return instance

    @classmethod
    def clear_cache(cls) -> None:
        with cls._cache_lock:
            cls._cache.clear()

    @cached_property
    def managers(self) -> dict[str, ManagerInfo]:
        """Discovers model managers."""
        manager_info = {}
        manager_map = getattr(self._meta, "managers_map", None) or {}
        default_manager_name = getattr(self._meta, "default_manager_name", "objects")
        if manager_map:
            manager_items = manager_map.items()
        else:
            manager_items = (
                (name, getattr(self.model, name))
                for name in dir(self.model)
                if not name.startswith("_")
            )

        ignored_methods = {
            "model",
            "get_queryset",
            "all",
            "filter",
            "exclude",
            "get",
            "create",
            "update",
            "delete",
        }

        for name, attr in manager_items:
            if not hasattr(attr, "model") or not hasattr(attr, "get_queryset"):
                continue
            get_queryset = getattr(attr, "get_queryset", None)
            if not callable(get_queryset):
                continue
            custom_methods = {}
            for method_name in dir(attr):
                if method_name.startswith("_") or method_name in ignored_methods:
                    continue
                method = getattr(attr, method_name, None)
                if callable(method):
                    custom_methods[method_name] = method
            manager_info[name] = ManagerInfo(
                name=name,
                manager_class=type(attr),
                is_default=(name == default_manager_name),
                custom_methods=custom_methods,
            )
        return manager_info

    @cached_property
    def fields(self) -> dict[str, FieldInfo]:
        """Extracts model fields."""
        if not self._meta: return {}
        field_info = {}
        for field in self._meta.get_fields():
            if isinstance(field, (ForeignKey, OneToOneField, ManyToManyField)): continue
            if not hasattr(field, "null") or not hasattr(field, "default"): continue
            field_info[field.name] = FieldInfo(field_type=type(field), is_required=not field.null, default_value=field.default if field.default is not models.NOT_PROVIDED else None, help_text=str(field.help_text), has_auto_now=getattr(field, "auto_now", False), has_auto_now_add=getattr(field, "auto_now_add", False), blank=getattr(field, "blank", False), has_default=(field.default is not models.NOT_PROVIDED))
        return field_info

    @cached_property
    def relationships(self) -> dict[str, RelationshipInfo]:
        """Identifies model relationships."""
        if not self._meta: return {}
        rel_info = {}
        for field in self._meta.get_fields():
            if isinstance(field, (ForeignKey, OneToOneField, ManyToManyField)):
                rel_info[field.name] = RelationshipInfo(related_model=field.related_model, relationship_type=type(field).__name__, to_field=field.remote_field.name if field.remote_field else None, from_field=field.name)
        return rel_info

    @cached_property
    def methods(self) -> dict[str, MethodInfo]:
        """Discovers model methods."""
        method_info = {}
        for name, member in inspect.getmembers(self.model, predicate=inspect.isfunction):
            if self._is_django_builtin_method(name, member) or name.startswith("_"): continue
            try:
                sig = inspect.signature(member)
                arguments = {pn: {"type": p.annotation if p.annotation != inspect.Parameter.empty else Any, "default": p.default if p.default != inspect.Parameter.empty else None, "required": p.default == inspect.Parameter.empty} for pn, p in sig.parameters.items() if pn != "self"}
                return_type = sig.return_annotation if sig.return_annotation != inspect.Signature.empty else Any
            except Exception: continue
            method_info[name] = MethodInfo(name=name, arguments=arguments, return_type=return_type, is_async=inspect.iscoroutinefunction(member), is_mutation=self._is_mutation_method(name, member), is_private=hasattr(member, "_private"), method=member)
        return method_info

    @cached_property
    def properties(self) -> dict[str, PropertyInfo]:
        """Discovers model properties."""
        prop_info = {}
        for name, member in inspect.getmembers(self.model, predicate=lambda x: isinstance(x, property)):
            if name.startswith("_"): continue
            rt, vn = Any, None
            if member.fget:
                sig = inspect.signature(member.fget)
                rt, vn = sig.return_annotation, getattr(member.fget, "short_description", None)
            prop_info[name] = PropertyInfo(return_type=rt, verbose_name=vn)
        return prop_info

    @cached_property
    def custom_fields(self) -> dict[str, CustomFieldInfo]:
        """Discovers model methods decorated as GraphQL output fields."""
        field_info = {}

        for base_class in reversed(self.model.__mro__):
            if base_class in (models.Model, object):
                continue

            for attr_name, attr_value in vars(base_class).items():
                member = getattr(attr_value, "__func__", attr_value)
                if not getattr(member, "_is_graphql_field", False):
                    continue

                try:
                    sig = inspect.signature(member)
                    return_type = (
                        sig.return_annotation
                        if sig.return_annotation != inspect.Signature.empty
                        else Any
                    )
                    accepts_info = len(
                        [
                            param
                            for param in sig.parameters.values()
                            if param.kind
                            in (
                                inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            )
                        ]
                    ) >= 2
                except Exception:
                    return_type = Any
                    accepts_info = False

                field_name = getattr(member, "_graphql_field_name", None) or attr_name
                field_info[field_name] = CustomFieldInfo(
                    name=field_name,
                    field_type=getattr(member, "_graphql_field_type", None),
                    return_type=return_type,
                    accepts_info=accepts_info,
                    verbose_name=getattr(member, "_graphql_field_title", None),
                    description=getattr(member, "_graphql_field_description", None),
                    method=member,
                )

        return field_info

    @cached_property
    def inheritance(self) -> InheritanceInfo:
        """Analyzes model inheritance."""
        if not self._meta: return InheritanceInfo(base_classes=[], is_abstract=False)
        return InheritanceInfo(base_classes=[b for b in self.model.__bases__ if isinstance(b, type(models.Model))], is_abstract=self._meta.abstract)

    def get_model_fields(self) -> dict[str, FieldInfo]: return self.fields
    def get_model_relationships(self) -> dict[str, RelationshipInfo]: return self.relationships
    def get_model_methods(self) -> dict[str, MethodInfo]: return self.methods
    def get_model_properties(self) -> dict[str, PropertyInfo]: return self.properties
    def get_model_custom_fields(self) -> dict[str, CustomFieldInfo]: return self.custom_fields
    def get_model_managers(self) -> dict[str, ManagerInfo]: return self.managers
    def analyze_inheritance(self) -> InheritanceInfo: return self.inheritance

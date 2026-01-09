"""
Model Introspection System for Django GraphQL Auto-Generation

This module provides the ModelIntrospector class, which is responsible for analyzing
Django models and extracting metadata required for generating GraphQL schemas.
"""

import inspect
from typing import Any, Dict, List, Optional, Type, Union, get_args, get_origin

from django.db import models
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from django.utils.functional import cached_property

# Data structures for introspection results


class FieldInfo:
    """
    Stores metadata about a Django model field.

    Attributes:
        field_type: The Django field type class
        is_required: Whether the field is required (not null)
        default_value: The default value for the field
        help_text: Help text for the field
        has_auto_now: Whether the field has auto_now=True
        has_auto_now_add: Whether the field has auto_now_add=True
        blank: Whether the field allows blank values
        has_default: Whether the field has a default value
    """

    def __init__(
        self,
        field_type: Any,
        is_required: bool,
        default_value: Any,
        help_text: str,
        has_auto_now: bool = False,
        has_auto_now_add: bool = False,
        blank: bool = True,
        has_default: bool = False,
    ):
        self.field_type = field_type
        self.is_required = is_required
        self.default_value = default_value
        self.help_text = help_text
        self.has_auto_now = has_auto_now
        self.has_auto_now_add = has_auto_now_add
        self.blank = blank
        self.has_default = has_default


class RelationshipInfo:
    """
    Stores metadata about a model relationship.

    Attributes:
        related_model: The related Django model class
        relationship_type: Type of relationship (ForeignKey, ManyToManyField, etc.)
        to_field: The field name on the related model
        from_field: The field name on the current model
    """

    def __init__(
        self,
        related_model: Type[models.Model],
        relationship_type: str,
        to_field: str,
        from_field: str,
    ):
        self.related_model = related_model
        self.relationship_type = relationship_type
        self.to_field = to_field
        self.from_field = from_field


class MethodInfo:
    """
    Information about a model method.

    Attributes:
        name: Method name
        arguments: Dictionary of argument names and their metadata
        return_type: The return type annotation
        is_async: Whether the method is asynchronous
        is_mutation: Whether the method should be treated as a mutation
        is_private: Whether the method is private (starts with _)
        method: The actual method callable
    """

    def __init__(
        self,
        name: str,
        arguments: Dict[str, Any],
        return_type: Any,
        is_async: bool,
        is_mutation: bool = False,
        is_private: bool = False,
        method: callable = None,
    ):
        self.name = name
        self.arguments = arguments
        self.return_type = return_type
        self.is_async = is_async
        self.is_mutation = is_mutation
        self.is_private = is_private
        self.method = method


class PropertyInfo:
    """
    Stores metadata about a model property.

    Attributes:
        return_type: The return type annotation of the property
        verbose_name: Optional human-friendly title, from fget.short_description
    """

    def __init__(self, return_type: Any, verbose_name: Optional[str] = None):
        self.return_type = return_type
        self.verbose_name = verbose_name


class ManagerInfo:
    """
    Stores metadata about a Django model manager.

    Attributes:
        name: The manager name (e.g., 'objects', 'published', 'active')
        manager_class: The manager class type
        is_default: Whether this is the default manager (usually 'objects')
        custom_methods: Dict of custom methods available on the manager
    """

    def __init__(
        self,
        name: str,
        manager_class: Type,
        is_default: bool = False,
        custom_methods: Dict[str, Any] = None,
    ):
        self.name = name
        self.manager_class = manager_class
        self.is_default = is_default
        self.custom_methods = custom_methods or {}


class InheritanceInfo:
    """
    Stores metadata about model inheritance.

    Attributes:
        base_classes: List of base model classes
        is_abstract: Whether the model is abstract
    """

    def __init__(self, base_classes: List[Type[models.Model]], is_abstract: bool):
        self.base_classes = base_classes
        self.is_abstract = is_abstract


class ModelIntrospector:
    """
    Analyzes Django models to extract metadata for GraphQL schema generation.

    This class provides comprehensive introspection capabilities for Django models,
    extracting information about fields, relationships, methods, properties, and
    inheritance hierarchies. The introspection results are cached to avoid
    redundant analysis.

    Features:
    - Field analysis with type information and constraints
    - Relationship discovery (ForeignKey, ManyToMany, OneToOne)
    - Method signature extraction with type annotations
    - Property detection and analysis
    - Inheritance hierarchy mapping
    - Caching for performance optimization

    Args:
        model: The Django model class to introspect
        schema_name: Optional schema name for context (for future multi-schema support)

    Example:
        >>> from myapp.models import User
        >>> introspector = ModelIntrospector(User)
        >>> fields = introspector.fields
        >>> relationships = introspector.relationships
        >>> methods = introspector.methods
    """

    def __init__(self, model: Type[models.Model], schema_name: Optional[str] = None):
        self.model = model
        self.schema_name = schema_name or "default"
        self._meta = getattr(model, "_meta", None)

    @cached_property
    def managers(self) -> Dict[str, ManagerInfo]:
        """Discovers model managers and their metadata."""
        manager_info = {}

        # Get all managers from the model
        for name in dir(self.model):
            attr = getattr(self.model, name)

            # Check if it's a manager (has a model attribute and get_queryset method)
            if (
                hasattr(attr, "model")
                and hasattr(attr, "get_queryset")
                and callable(getattr(attr, "get_queryset"))
                and not name.startswith("_")
            ):
                # Determine if this is the default manager
                is_default = name == "objects"

                # Get custom methods from the manager
                custom_methods = {}
                for method_name in dir(attr):
                    if (
                        not method_name.startswith("_")
                        and method_name
                        not in [
                            "model",
                            "get_queryset",
                            "all",
                            "filter",
                            "exclude",
                            "get",
                            "create",
                            "update",
                            "delete",
                        ]
                        and callable(getattr(attr, method_name))
                    ):
                        custom_methods[method_name] = getattr(attr, method_name)

                manager_info[name] = ManagerInfo(
                    name=name,
                    manager_class=type(attr),
                    is_default=is_default,
                    custom_methods=custom_methods,
                )

        return manager_info

    @cached_property
    def fields(self) -> Dict[str, FieldInfo]:
        """Extracts model fields with their types and constraints."""
        if not self._meta:
            return {}

        field_info = {}
        for field in self._meta.get_fields():
            # Skip relationship fields and reverse relationship fields
            if isinstance(field, (ForeignKey, OneToOneField, ManyToManyField)):
                continue

            # Skip reverse relationship fields (they don't have null or default attributes)
            if not hasattr(field, "null") or not hasattr(field, "default"):
                continue

            # Check for auto_now and auto_now_add fields
            has_auto_now = getattr(field, "auto_now", False)
            has_auto_now_add = getattr(field, "auto_now_add", False)

            # Check if field has a default value
            has_default = field.default is not models.NOT_PROVIDED

            # Get blank attribute (defaults to False for most fields)
            blank = getattr(field, "blank", False)

            field_info[field.name] = FieldInfo(
                field_type=type(field),
                is_required=not field.null,
                default_value=field.default if has_default else None,
                help_text=str(field.help_text),
                has_auto_now=has_auto_now,
                has_auto_now_add=has_auto_now_add,
                blank=blank,
                has_default=has_default,
            )
        return field_info

    @cached_property
    def relationships(self) -> Dict[str, RelationshipInfo]:
        """Identifies model relationships (ForeignKey, ManyToMany, OneToOne)."""
        if not self._meta:
            return {}

        relationship_info = {}
        for field in self._meta.get_fields():
            if isinstance(field, (ForeignKey, OneToOneField, ManyToManyField)):
                relationship_info[field.name] = RelationshipInfo(
                    related_model=field.related_model,
                    relationship_type=type(field).__name__,
                    to_field=field.remote_field.name if field.remote_field else None,
                    from_field=field.name,
                )
        return relationship_info

    @cached_property
    def methods(self) -> Dict[str, MethodInfo]:
        """Discovers model methods and their signatures."""
        method_info = {}

        # Use inspect.isfunction for class methods, not inspect.ismethod
        for name, member in inspect.getmembers(
            self.model, predicate=inspect.isfunction
        ):
            # Skip Django model built-in methods and PolymorphicModel methods
            if self._is_django_builtin_method(name, member):
                continue

            # Skip private methods (starting with _)
            if name.startswith("_"):
                continue

            # Get method signature
            try:
                sig = inspect.signature(member)
                arguments = {}
                for param_name, param in sig.parameters.items():
                    if param_name != "self":  # Skip 'self' parameter
                        arguments[param_name] = {
                            "type": param.annotation
                            if param.annotation != inspect.Parameter.empty
                            else Any,
                            "default": param.default
                            if param.default != inspect.Parameter.empty
                            else None,
                            "required": param.default == inspect.Parameter.empty,
                        }

                return_type = (
                    sig.return_annotation
                    if sig.return_annotation != inspect.Signature.empty
                    else Any
                )
            except (ValueError, TypeError):
                # Skip methods with problematic signatures
                continue

            # Determine if method is a mutation (modifies state)
            is_mutation = self._is_mutation_method(name, member)
            is_private = name.startswith("_") or hasattr(member, "_private")

            method_info[name] = MethodInfo(
                name=name,
                arguments=arguments,
                return_type=return_type,
                is_async=inspect.iscoroutinefunction(member),
                is_mutation=is_mutation,
                is_private=is_private,
                method=member,
            )
        return method_info

    def _is_django_builtin_method(self, method_name: str, method: callable) -> bool:
        """
        Determines if a method is a Django model built-in method or PolymorphicModel method.

        Args:
            method_name: Name of the method
            method: The method object

        Returns:
            bool: True if the method should be ignored
        """
        # Django Model built-in methods to ignore
        django_builtin_methods = {
            "clean",
            "clean_fields",
            "full_clean",
            "validate_unique",
            "validate_constraints",
            "save",
            "save_base",
            "delete",
            "adelete",
            "refresh_from_db",
            "arefresh_from_db",
            "get_absolute_url",
            "get_deferred_fields",
            "serializable_value",
            "prepare_database_save",
            "unique_error_message",
            "date_error_message",
            "get_constraints",
            "asave",
        }

        # PolymorphicModel methods to ignore
        polymorphic_methods = {
            "get_real_instance",
            "get_real_instance_class",
            "get_real_concrete_instance_class",
            "get_polymorphic_value",
            "polymorphic_super",
        }

        # Django auto-generated methods (get_next_by_*, get_previous_by_*, get_*_display)
        auto_generated_patterns = [
            "get_next_by_",
            "get_previous_by_",
            "get_",
            "_display",
        ]

        # Check exact matches
        if method_name in django_builtin_methods or method_name in polymorphic_methods:
            return True

        # Check patterns for auto-generated methods
        for pattern in auto_generated_patterns:
            if pattern in method_name:
                # Additional check for get_*_display methods
                if method_name.endswith("_display"):
                    return True
                # Check for get_next_by_* and get_previous_by_* methods
                if method_name.startswith(("get_next_by_", "get_previous_by_")):
                    return True

        # Check if method is defined in Django's Model class or its parents
        try:
            # Get the method resolution order
            for cls in self.model.__mro__:
                if cls.__name__ in ["Model", "PolymorphicModel"] and hasattr(
                    cls, method_name
                ):
                    return True
        except AttributeError:
            pass

        return False

    def _is_mutation_method(self, method_name: str, method: callable) -> bool:
        """
        Determines if a method is a mutation (modifies state).

        Args:
            method_name: Name of the method
            method: The method object

        Returns:
            bool: True if the method is considered a mutation
        """

        # Check for explicit mutation decorator or attribute
        if hasattr(method, "_is_mutation"):
            return method._is_mutation

        # Check for business logic decorator

        if hasattr(method, "_is_business_logic"):
            return method._is_business_logic

        # Check method name patterns that suggest mutations
        mutation_patterns = [
            "create",
            "update",
            "delete",
            "remove",
            "add",
            "set",
            "clear",
            "activate",
            "deactivate",
            "enable",
            "disable",
            "toggle",
            "approve",
            "reject",
            "publish",
            "unpublish",
            "archive",
            "process",
            "execute",
            "perform",
            "handle",
            "trigger",
            "send",
            "notify",
            "calculate",
            "generate",
            "sync",
        ]

        method_lower = method_name.lower()
        for pattern in mutation_patterns:
            if pattern in method_lower:
                return True

        # Check docstring for mutation indicators
        if method.__doc__:
            doc_lower = method.__doc__.lower()
            mutation_keywords = [
                "modify",
                "change",
                "update",
                "create",
                "delete",
                "save",
                "process",
                "execute",
            ]
            for keyword in mutation_keywords:
                if keyword in doc_lower:
                    return True

        return False

    @cached_property
    def properties(self) -> Dict[str, PropertyInfo]:
        """Discovers model properties and their return types."""
        property_info = {}
        for name, member in inspect.getmembers(
            self.model, predicate=lambda x: isinstance(x, property)
        ):
            if name.startswith("_"):
                continue

            # Infer return type from property's fget method if available
            return_type = Any
            verbose_name = None
            if member.fget:
                sig = inspect.signature(member.fget)
                return_type = sig.return_annotation
                # Capture admin-style short_description as title if present
                verbose_name = getattr(member.fget, "short_description", None)

            property_info[name] = PropertyInfo(
                return_type=return_type, verbose_name=verbose_name
            )
        return property_info

    @cached_property
    def inheritance(self) -> InheritanceInfo:
        """Analyzes the model's inheritance hierarchy."""
        if not self._meta:
            return InheritanceInfo(base_classes=[], is_abstract=False)

        return InheritanceInfo(
            base_classes=[
                b for b in self.model.__bases__ if isinstance(b, type(models.Model))
            ],
            is_abstract=self._meta.abstract,
        )

    def get_model_fields(self) -> Dict[str, FieldInfo]:
        return self.fields

    def get_model_relationships(self) -> Dict[str, RelationshipInfo]:
        return self.relationships

    def get_model_methods(self) -> Dict[str, MethodInfo]:
        return self.methods

    def get_model_properties(self) -> Dict[str, PropertyInfo]:
        return self.properties

    def get_model_managers(self) -> Dict[str, ManagerInfo]:
        return self.managers

    def analyze_inheritance(self) -> InheritanceInfo:
        return self.inheritance

    def get_manytoone_relations(self) -> Dict[str, Type[models.Model]]:
        """
        Get reverse relationships for the model (e.g., comments for Post).

        Returns:
            Dict mapping field names to related models
        """
        reverse_relations = {}
        if not self._meta:
            return reverse_relations

        # For modern Django versions, use related_objects
        if hasattr(self._meta, "related_objects"):
            for rel in self._meta.related_objects:
                # Get the accessor name (e.g., 'comments' for Comment.post -> Post)
                if type(rel) == models.ManyToOneRel:
                    accessor_name = rel.get_accessor_name()
                    reverse_relations[accessor_name] = rel.related_model

        # Fallback for Django versions that use get_fields() with related fields
        elif hasattr(self._meta, "get_fields"):
            try:
                for field in self._meta.get_fields():
                    # Check if it's a reverse relation (ForeignKey, OneToOneField, ManyToManyField)
                    if hasattr(field, "related_model") and hasattr(
                        field, "get_accessor_name"
                    ):
                        print(type(field), field.__class__)
                        accessor_name = field.get_accessor_name()
                        reverse_relations[accessor_name] = field.related_model
            except AttributeError:
                # If get_fields doesn't work as expected, continue without reverse relations
                pass
        else:
            # Final fallback for very old Django versions
            try:
                for rel in self._meta.get_all_related_objects():
                    if hasattr(rel, "get_accessor_name"):
                        accessor_name = rel.get_accessor_name()
                    else:
                        accessor_name = rel.name

                    reverse_relations[accessor_name] = rel.related_model
            except AttributeError:
                # If get_all_related_objects doesn't exist, skip reverse relations
                pass

        return reverse_relations

    def get_reverse_relations(self) -> Dict[str, Type[models.Model]]:
        """
        Get reverse relationships for the model (e.g., comments for Post).

        Returns:
            Dict mapping field names to related models
        """
        reverse_relations = {}

        if not self._meta:
            return reverse_relations

        # For modern Django versions, use related_objects
        if hasattr(self._meta, "related_objects"):
            for rel in self._meta.related_objects:
                # Get the accessor name (e.g., 'comments' for Comment.post -> Post)
                accessor_name = rel.get_accessor_name()
                reverse_relations[accessor_name] = rel.related_model
        # Fallback for Django versions that use get_fields() with related fields
        elif hasattr(self._meta, "get_fields"):
            try:
                for field in self._meta.get_fields():
                    # Check if it's a reverse relation (ForeignKey, OneToOneField, ManyToManyField)
                    if hasattr(field, "related_model") and hasattr(
                        field, "get_accessor_name"
                    ):
                        accessor_name = field.get_accessor_name()
                        reverse_relations[accessor_name] = field.related_model
            except AttributeError:
                # If get_fields doesn't work as expected, continue without reverse relations
                pass
        else:
            # Final fallback for very old Django versions
            try:
                for rel in self._meta.get_all_related_objects():
                    if hasattr(rel, "get_accessor_name"):
                        accessor_name = rel.get_accessor_name()
                    else:
                        accessor_name = rel.name

                    reverse_relations[accessor_name] = rel.related_model
            except AttributeError:
                # If get_all_related_objects doesn't exist, skip reverse relations
                pass

        return reverse_relations

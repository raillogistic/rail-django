"""
Django Model Inheritance Support for GraphQL Auto-Generation

This module provides comprehensive support for Django model inheritance patterns
including abstract models, multi-table inheritance, and proxy models in GraphQL schemas.
"""

from typing import Any, Dict, List, Optional, Set, Type, Union

import graphene
from django.db import models
from django.db.models import Q
from django.db.models.base import ModelBase
from graphene_django import DjangoObjectType


class InheritanceHandler:
    """
    Handles Django model inheritance patterns for GraphQL schema generation.
    Supports abstract models, multi-table inheritance, and proxy models.
    """

    def __init__(self):
        self._inheritance_cache: Dict[Type[models.Model], Dict[str, Any]] = {}
        self._abstract_fields_cache: Dict[Type[models.Model], List[str]] = {}
        self._mixin_fields_cache: Dict[Type, List[str]] = {}

    def analyze_model_inheritance(self, model: Type[models.Model]) -> Dict[str, Any]:
        """
        Analyze a model's inheritance structure and return comprehensive information.

        Args:
            model: Django model class to analyze

        Returns:
            Dictionary containing inheritance information:
            - 'is_abstract': Whether the model is abstract
            - 'is_proxy': Whether the model is a proxy
            - 'parent_models': List of parent model classes
            - 'abstract_parents': List of abstract parent classes
            - 'concrete_parents': List of concrete parent classes
            - 'child_models': List of child model classes
            - 'inherited_fields': Fields inherited from parents
            - 'own_fields': Fields defined on this model
            - 'mixin_classes': Non-model mixin classes
        """
        if model in self._inheritance_cache:
            return self._inheritance_cache[model]

        analysis = {
            'is_abstract': model._meta.abstract,
            'is_proxy': model._meta.proxy,
            'parent_models': [],
            'abstract_parents': [],
            'concrete_parents': [],
            'child_models': [],
            'inherited_fields': [],
            'own_fields': [],
            'mixin_classes': []
        }

        # Analyze parent classes
        for base in model.__bases__:
            if isinstance(base, ModelBase) and issubclass(base, models.Model) and hasattr(base, '_meta'):
                analysis['parent_models'].append(base)
                if base._meta.abstract:
                    analysis['abstract_parents'].append(base)
                else:
                    analysis['concrete_parents'].append(base)
            elif hasattr(base, '__mro__') and base != object and base != models.Model:
                # Non-model mixin class
                analysis['mixin_classes'].append(base)

        # Find child models
        analysis['child_models'] = self._find_child_models(model)

        # Analyze fields
        own_field_names = set()
        inherited_field_names = set()

        # Get fields defined on this model
        for field in model._meta.get_fields():
            if hasattr(field, 'model') and field.model == model:
                own_field_names.add(field.name)
                analysis['own_fields'].append(field.name)

        # Get inherited fields
        for parent in analysis['parent_models']:
            for field in parent._meta.get_fields():
                if field.name not in own_field_names:
                    inherited_field_names.add(field.name)
                    analysis['inherited_fields'].append(field.name)

        # Cache the analysis
        self._inheritance_cache[model] = analysis
        return analysis

    def _find_child_models(self, model: Type[models.Model]) -> List[Type[models.Model]]:
        """Find all child models that inherit from the given model."""
        child_models = []

        # Get all registered models
        from django.apps import apps
        for app_config in apps.get_app_configs():
            for child_model in app_config.get_models():
                if (child_model != model and
                    issubclass(child_model, model) and
                        not child_model._meta.abstract):
                    child_models.append(child_model)

        return child_models

    def get_abstract_fields(self, abstract_model: Type[models.Model]) -> List[str]:
        """
        Get all fields defined in an abstract model.

        Args:
            abstract_model: Abstract model class

        Returns:
            List of field names defined in the abstract model
        """
        if abstract_model in self._abstract_fields_cache:
            return self._abstract_fields_cache[abstract_model]

        if not abstract_model._meta.abstract:
            return []

        fields = []
        for field in abstract_model._meta.get_fields():
            if hasattr(field, 'model') and field.model == abstract_model:
                fields.append(field.name)

        self._abstract_fields_cache[abstract_model] = fields
        return fields

    def get_mixin_fields(self, mixin_class: Type) -> List[str]:
        """
        Get all fields and methods defined in a mixin class.

        Args:
            mixin_class: Mixin class to analyze

        Returns:
            List of attribute names defined in the mixin
        """
        if mixin_class in self._mixin_fields_cache:
            return self._mixin_fields_cache[mixin_class]

        fields = []
        for attr_name in dir(mixin_class):
            if not attr_name.startswith('_'):
                attr = getattr(mixin_class, attr_name)
                if not callable(attr) or hasattr(attr, 'fget'):  # Include properties
                    fields.append(attr_name)

        self._mixin_fields_cache[mixin_class] = fields
        return fields

    def create_interface_for_abstract_model(
        self,
        abstract_model: Type[models.Model],
        type_generator: Any
    ) -> Optional[Type[graphene.Interface]]:
        """
        Create a GraphQL interface for an abstract Django model.

        Args:
            abstract_model: Abstract model class
            type_generator: Type generator instance for creating field types

        Returns:
            GraphQL interface class or None if not applicable
        """
        if not abstract_model._meta.abstract:
            return None

        # Get fields from the abstract model
        fields = {}
        for field in abstract_model._meta.get_fields():
            if hasattr(field, 'model') and field.model == abstract_model:
                try:
                    graphql_field = type_generator._convert_django_field_to_graphql(field)
                    if graphql_field:
                        fields[field.name] = graphql_field
                except Exception:
                    continue  # Skip fields that can't be converted

        # Add methods and properties from the abstract model
        for attr_name in dir(abstract_model):
            if (not attr_name.startswith('_') and
                attr_name not in fields and
                    hasattr(abstract_model, attr_name)):

                attr = getattr(abstract_model, attr_name)
                if callable(attr) and not isinstance(attr, type):
                    try:
                        # Create a field for the method
                        method_field = type_generator._create_method_field(attr)
                        if method_field:
                            fields[attr_name] = method_field
                    except Exception:
                        continue

        if not fields:
            return None

        # Create the interface class
        interface_name = f"{abstract_model.__name__}Interface"

        class Meta:
            name = interface_name

        interface_attrs = fields.copy()
        interface_attrs['Meta'] = Meta

        return type(interface_name, (graphene.Interface,), interface_attrs)

    def create_union_for_inheritance_tree(
        self,
        base_model: Type[models.Model],
        type_generator: Any
    ) -> Optional[Type[graphene.Union]]:
        """
        Create a GraphQL union type for a model inheritance tree.

        Args:
            base_model: Base model class
            type_generator: Type generator instance

        Returns:
            GraphQL union class or None if not applicable
        """
        analysis = self.analyze_model_inheritance(base_model)
        child_models = analysis['child_models']

        if not child_models:
            return None

        # Get GraphQL types for all child models (including the base model)
        union_types = []

        # Add the base model type if it's not abstract
        if not base_model._meta.abstract:
            try:
                base_type = type_generator.generate_object_type(base_model)
                if base_type:
                    union_types.append(base_type)
            except Exception:
                pass

        # Add child model types
        for child_model in child_models:
            try:
                child_type = type_generator.generate_object_type(child_model)
                if child_type:
                    union_types.append(child_type)
            except Exception:
                continue

        if not union_types:
            return None

        # Create the union class
        union_name = f"{base_model.__name__}Union"

        class Meta:
            types = tuple(union_types)

        union_class = type(union_name, (graphene.Union,), {'Meta': Meta})

        # Add resolve_type method to the union
        def resolve_type(root, info):
            """Resolve the correct GraphQL type for polymorphic instances"""
            instance_type = type(root)

            # Look up the GraphQL type for this instance
            for union_type in union_types:
                if hasattr(union_type, '_meta') and hasattr(union_type._meta, 'model'):
                    if union_type._meta.model == instance_type:
                        return union_type

            # Fallback to first type
            return union_types[0] if union_types else None

        union_class.resolve_type = staticmethod(resolve_type)

        return union_class

    def enhance_type_with_inheritance(
        self,
        model: Type[models.Model],
        graphql_type: Type[DjangoObjectType],
        type_generator: Any
    ) -> Type[DjangoObjectType]:
        """
        Enhance a GraphQL type with inheritance-related features.

        Args:
            model: Django model class
            graphql_type: Existing GraphQL type
            type_generator: Type generator instance

        Returns:
            Enhanced GraphQL type with inheritance support
        """
        analysis = self.analyze_model_inheritance(model)

        # Create interfaces for abstract parents
        interfaces = []
        for abstract_parent in analysis['abstract_parents']:
            interface = self.create_interface_for_abstract_model(abstract_parent, type_generator)
            if interface:
                interfaces.append(interface)

        # Add mixin fields
        additional_fields = {}
        for mixin_class in analysis['mixin_classes']:
            mixin_fields = self.get_mixin_fields(mixin_class)
            for field_name in mixin_fields:
                if hasattr(mixin_class, field_name):
                    attr = getattr(mixin_class, field_name)
                    try:
                        if callable(attr):
                            method_field = type_generator._create_method_field(attr)
                            if method_field:
                                additional_fields[field_name] = method_field
                        else:
                            # Handle properties and other attributes
                            additional_fields[field_name] = graphene.String()
                    except Exception:
                        continue

        # If we have interfaces or additional fields, create an enhanced type
        if interfaces or additional_fields:
            # Get existing fields
            existing_fields = {}
            if hasattr(graphql_type, '_meta') and hasattr(graphql_type._meta, 'fields'):
                existing_fields = graphql_type._meta.fields.copy()

            # Merge fields
            all_fields = {**existing_fields, **additional_fields}

            # Create new type class
            enhanced_name = f"Enhanced{graphql_type.__name__}"

            class Meta:
                model = model
                interfaces = tuple(interfaces) if interfaces else ()
                fields = '__all__'

            enhanced_attrs = all_fields.copy()
            enhanced_attrs['Meta'] = Meta

            return type(enhanced_name, (DjangoObjectType,), enhanced_attrs)

        return graphql_type

    def get_polymorphic_resolver(
        self,
        base_model: Type[models.Model],
        type_generator: Any
    ) -> Optional[callable]:
        """
        Create a polymorphic resolver for inheritance hierarchies.

        Args:
            base_model: Base model class
            type_generator: Type generator instance

        Returns:
            Resolver function that returns appropriate type based on instance
        """
        analysis = self.analyze_model_inheritance(base_model)
        child_models = analysis['child_models']

        if not child_models:
            return None

        # Create mapping of model classes to GraphQL types
        type_mapping = {}
        for child_model in child_models:
            try:
                child_type = type_generator.generate_object_type(child_model)
                if child_type:
                    type_mapping[child_model] = child_type
            except Exception:
                continue

        def polymorphic_resolver(root, info, **kwargs):
            """
            Resolver that returns the instance but with proper type resolution.
            The GraphQL type resolution happens at the schema level.
            """
            if root is None:
                return None

            # For polymorphic queries, we need to handle the database query
            if not kwargs:
                return None

            filters = Q()
            for key, value in kwargs.items():
                filters |= Q(**{key: value})

            try:
                # Get the instance from the base model queryset
                instance = base_model.objects.get(filters)

                # Return the actual instance - GraphQL will resolve the correct type
                # based on the instance's actual class
                return instance
            except base_model.DoesNotExist:
                return None

        return polymorphic_resolver

    def create_inheritance_aware_queries(
        self,
        model: Type[models.Model],
        query_generator: Any
    ) -> Dict[str, graphene.Field]:
        """
        Create inheritance-aware queries for a model.

        Args:
            model: Django model class
            query_generator: Query generator instance

        Returns:
            Dictionary of query fields that handle inheritance
        """
        queries = {}
        analysis = self.analyze_model_inheritance(model)

        # Create polymorphic queries for models with children
        if analysis['child_models']:
            # Use the base model type instead of union type for polymorphic queries
            # The polymorphic_type field will indicate the actual class
            base_type = query_generator.type_generator.generate_object_type(model)
            if base_type:
                def polymorphic_list_resolver(root, info, **kwargs):
                    """Resolver that returns instances of any child type."""
                    queryset = model.objects.all()

                    # Apply filters if provided
                    if kwargs:
                        queryset = queryset.filter(**kwargs)

                    return queryset

                queries[f"all_{model.__name__.lower()}_polymorphic"] = graphene.List(
                    base_type,
                    resolver=polymorphic_list_resolver,
                    description=f"Get all {model.__name__} instances including child types"
                )

        # Create type-specific queries for concrete child models
        for child_model in analysis['child_models']:
            if not child_model._meta.abstract:
                try:
                    child_queries = query_generator.generate_all_queries(child_model)
                    queries.update(child_queries)
                except Exception:
                    continue

        return queries


# Global inheritance handler instance
inheritance_handler = InheritanceHandler()

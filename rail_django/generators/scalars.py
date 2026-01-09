"""
Custom Scalar Types and Method Return Type Analysis for Django GraphQL Auto-Generation

This module provides advanced scalar type support and method return type analysis
for complex GraphQL schemas with custom data types and method-based fields.
"""

import inspect
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type, Union, get_type_hints
from uuid import UUID

import graphene
from django.db import models
from graphene import Scalar


class JSONScalar(Scalar):
    """
    Custom scalar for JSON data that can handle complex nested structures.
    """

    @staticmethod
    def serialize(value):
        """Serialize Python object to JSON string."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                # Validate that it's valid JSON
                json.loads(value)
                return value
            except (json.JSONDecodeError, TypeError):
                return json.dumps(value)
        return json.dumps(value, default=str)

    @staticmethod
    def parse_literal(node):
        """Parse GraphQL literal to Python object."""
        if isinstance(node, graphene.language.ast.StringValueNode):
            try:
                return json.loads(node.value)
            except (json.JSONDecodeError, TypeError):
                return node.value
        return None

    @staticmethod
    def parse_value(value):
        """Parse GraphQL variable to Python object."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value


class DateTimeScalar(Scalar):
    """
    Custom scalar for DateTime with timezone support.
    """

    @staticmethod
    def serialize(value):
        """Serialize datetime to ISO string."""
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @staticmethod
    def parse_literal(node):
        """Parse GraphQL literal to datetime."""
        if isinstance(node, graphene.language.ast.StringValueNode):
            try:
                return datetime.fromisoformat(node.value.replace('Z', '+00:00'))
            except ValueError:
                return None
        return None

    @staticmethod
    def parse_value(value):
        """Parse GraphQL variable to datetime."""
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return None
        return value


class DecimalScalar(Scalar):
    """
    Custom scalar for high-precision decimal numbers.
    """

    @staticmethod
    def serialize(value):
        """Serialize Decimal to string."""
        if isinstance(value, Decimal):
            return str(value)
        return value

    @staticmethod
    def parse_literal(node):
        """Parse GraphQL literal to Decimal."""
        if isinstance(node, (graphene.language.ast.StringValueNode, graphene.language.ast.FloatValueNode)):
            try:
                return Decimal(str(node.value))
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def parse_value(value):
        """Parse GraphQL variable to Decimal."""
        if isinstance(value, (str, int, float)):
            try:
                return Decimal(str(value))
            except (ValueError, TypeError):
                return None
        return value


class UUIDScalar(Scalar):
    """
    Custom scalar for UUID values.
    """

    @staticmethod
    def serialize(value):
        """Serialize UUID to string."""
        if isinstance(value, UUID):
            return str(value)
        return value

    @staticmethod
    def parse_literal(node):
        """Parse GraphQL literal to UUID."""
        if isinstance(node, graphene.language.ast.StringValueNode):
            try:
                return UUID(node.value)
            except ValueError:
                return None
        return None

    @staticmethod
    def parse_value(value):
        """Parse GraphQL variable to UUID."""
        if isinstance(value, str):
            try:
                return UUID(value)
            except ValueError:
                return None
        return value


class DurationScalar(Scalar):
    """
    Custom scalar for time duration values.
    """

    @staticmethod
    def serialize(value):
        """Serialize timedelta to total seconds."""
        if isinstance(value, timedelta):
            return value.total_seconds()
        return value

    @staticmethod
    def parse_literal(node):
        """Parse GraphQL literal to timedelta."""
        if isinstance(node, (graphene.language.ast.IntValueNode, graphene.language.ast.FloatValueNode)):
            try:
                return timedelta(seconds=float(node.value))
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def parse_value(value):
        """Parse GraphQL variable to timedelta."""
        if isinstance(value, (int, float)):
            try:
                return timedelta(seconds=float(value))
            except (ValueError, TypeError):
                return None
        return value


class CustomScalarRegistry:
    """
    Registry for managing custom scalar types and their mappings.
    """

    def __init__(self):
        self._scalars: Dict[Type, Type[Scalar]] = {
            # Built-in Python types
            dict: JSONScalar,
            list: JSONScalar,
            tuple: JSONScalar,
            set: JSONScalar,

            # Date/time types
            datetime: DateTimeScalar,
            date: graphene.Date,
            time: graphene.Time,
            timedelta: DurationScalar,

            # Numeric types
            Decimal: DecimalScalar,

            # Other types
            UUID: UUIDScalar,
            bytes: graphene.String,  # Serialize as base64 string
        }

        # Django field mappings
        self._django_field_mappings: Dict[Type[models.Field], Type[Scalar]] = {
            models.JSONField: JSONScalar,
            models.UUIDField: UUIDScalar,
            models.DecimalField: DecimalScalar,
            models.DurationField: DurationScalar,
        }

    def register_scalar(self, python_type: Type, scalar_type: Type[Scalar]):
        """Register a custom scalar for a Python type."""
        self._scalars[python_type] = scalar_type

    def register_django_field_scalar(self, field_type: Type[models.Field], scalar_type: Type[Scalar]):
        """Register a custom scalar for a Django field type."""
        self._django_field_mappings[field_type] = scalar_type

    def get_scalar_for_type(self, python_type: Type) -> Optional[Type[Scalar]]:
        """Get the appropriate scalar type for a Python type."""
        return self._scalars.get(python_type)

    def get_scalar_for_django_field(self, field: models.Field) -> Optional[Type[Scalar]]:
        """Get the appropriate scalar type for a Django field."""
        field_type = type(field)
        return self._django_field_mappings.get(field_type)

    def get_graphene_type_for_python_type(self, python_type: Type) -> Type:
        """
        Get the appropriate GraphQL type for a Python type.
        Returns custom scalar if available, otherwise falls back to built-in types.
        """
        # Check for custom scalars first
        scalar_type = self.get_scalar_for_type(python_type)
        if scalar_type:
            return scalar_type

        # Built-in type mappings
        type_mappings = {
            str: graphene.String,
            int: graphene.Int,
            float: graphene.Float,
            bool: graphene.Boolean,
            type(None): graphene.String,  # Fallback for None type
        }

        return type_mappings.get(python_type, graphene.String)


class MethodReturnTypeAnalyzer:
    """
    Analyzes method return types to determine appropriate GraphQL types.
    """

    def __init__(self, scalar_registry: Optional[CustomScalarRegistry] = None):
        self.scalar_registry = scalar_registry or CustomScalarRegistry()

    def analyze_method_return_type(self, method: callable) -> Dict[str, Any]:
        """
        Analyze a method's return type and determine the appropriate GraphQL type.

        Args:
            method: The method to analyze

        Returns:
            Dictionary containing type information:
            - 'graphql_type': The GraphQL type to use
            - 'is_list': Whether the return type is a list
            - 'is_optional': Whether the return type is optional
            - 'python_type': The original Python type
        """
        try:
            # Get type hints
            type_hints = get_type_hints(method)
            return_type = type_hints.get('return', type(None))

            # Analyze the return type
            analysis = self._analyze_type(return_type)

            # Add method-specific information
            analysis['method_name'] = method.__name__
            analysis['method_doc'] = inspect.getdoc(method)

            return analysis

        except Exception as e:
            # Fallback for methods without type hints
            return {
                'graphql_type': graphene.String,
                'is_list': False,
                'is_optional': True,
                'python_type': type(None),
                'method_name': method.__name__,
                'method_doc': inspect.getdoc(method),
                'analysis_error': str(e)
            }

    def _analyze_type(self, python_type: Type) -> Dict[str, Any]:
        """
        Analyze a Python type and return GraphQL type information.
        """
        # Handle Union types (including Optional)
        if hasattr(python_type, '__origin__') and python_type.__origin__ is Union:
            args = python_type.__args__
            # Check if it's Optional (Union with None)
            if len(args) == 2 and type(None) in args:
                non_none_type = args[0] if args[1] is type(None) else args[1]
                analysis = self._analyze_type(non_none_type)
                analysis['is_optional'] = True
                return analysis
            else:
                # Handle other Union types - use String as fallback
                return {
                    'graphql_type': graphene.String,
                    'is_list': False,
                    'is_optional': True,
                    'python_type': python_type
                }

        # Handle List types
        if hasattr(python_type, '__origin__') and python_type.__origin__ in (list, List):
            if hasattr(python_type, '__args__') and python_type.__args__:
                item_type = python_type.__args__[0]
                item_analysis = self._analyze_type(item_type)
                return {
                    'graphql_type': graphene.List(item_analysis['graphql_type']),
                    'is_list': True,
                    'is_optional': False,
                    'python_type': python_type,
                    'item_type': item_analysis
                }
            else:
                return {
                    'graphql_type': graphene.List(graphene.String),
                    'is_list': True,
                    'is_optional': False,
                    'python_type': python_type
                }

        # Handle Dict types
        if hasattr(python_type, '__origin__') and python_type.__origin__ in (dict, Dict):
            return {
                'graphql_type': JSONScalar,
                'is_list': False,
                'is_optional': False,
                'python_type': python_type
            }

        # Handle basic types
        graphql_type = self.scalar_registry.get_graphene_type_for_python_type(python_type)

        return {
            'graphql_type': graphql_type,
            'is_list': False,
            'is_optional': False,
            'python_type': python_type
        }

    def create_method_field(self, method: callable, model_instance: Any = None) -> graphene.Field:
        """
        Create a GraphQL field for a method based on its return type analysis.

        Args:
            method: The method to create a field for
            model_instance: Optional model instance for context

        Returns:
            GraphQL field configured for the method
        """
        analysis = self.analyze_method_return_type(method)

        def resolver(root, info, **kwargs):
            """Dynamic resolver for method-based fields."""
            try:
                if root is None:
                    return None

                # Get the method from the instance
                instance_method = getattr(root, analysis['method_name'], None)
                if instance_method is None:
                    return None

                # Call the method
                if callable(instance_method):
                    # Check if method accepts arguments
                    sig = inspect.signature(instance_method)
                    if len(sig.parameters) > 0:
                        # Method accepts arguments - pass kwargs
                        return instance_method(**kwargs)
                    else:
                        # Method doesn't accept arguments
                        return instance_method()
                else:
                    # It's a property
                    return instance_method

            except Exception as e:
                # Log error and return None
                return None

        # Create the field with appropriate type
        field_type = analysis['graphql_type']
        if analysis['is_optional']:
            return graphene.Field(field_type, resolver=resolver, description=analysis.get('method_doc'))
        else:
            return graphene.Field(field_type, required=True, resolver=resolver, description=analysis.get('method_doc'))


# Global registry instance
scalar_registry = CustomScalarRegistry()
method_analyzer = MethodReturnTypeAnalyzer(scalar_registry)

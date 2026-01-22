"""
JSON custom scalar.
"""

import json
from typing import Any, Union

from graphene import Scalar
from graphql.error import GraphQLError
from graphql.language import ast

from .ast_utils import (
    _BOOLEAN_VALUE_TYPES,
    _FLOAT_VALUE_TYPES,
    _INT_VALUE_TYPES,
    _LIST_VALUE_TYPES,
    _NULL_VALUE_TYPES,
    _OBJECT_VALUE_TYPES,
    _STRING_VALUE_TYPES,
)


class JSON(Scalar):
    """
    Custom JSON scalar that handles JSON data.

    Serializes Python objects to JSON strings.
    Parses JSON strings to Python objects.
    """

    @staticmethod
    def serialize(value: Any) -> str:
        """Serialize Python object to JSON string."""
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            raise GraphQLError(f"Cannot serialize value as JSON: {e}")

    @staticmethod
    def parse_literal(node: ast.Node, _variables=None) -> Any:
        """Parse AST literal to Python object."""
        if _STRING_VALUE_TYPES and isinstance(node, _STRING_VALUE_TYPES):
            return JSON.parse_value(node.value)
        elif _OBJECT_VALUE_TYPES and isinstance(node, _OBJECT_VALUE_TYPES):
            return {field.name.value: JSON.parse_literal(field.value) for field in node.fields}
        elif _LIST_VALUE_TYPES and isinstance(node, _LIST_VALUE_TYPES):
            return [JSON.parse_literal(value) for value in node.values]
        elif _BOOLEAN_VALUE_TYPES and isinstance(node, _BOOLEAN_VALUE_TYPES):
            return node.value
        elif _INT_VALUE_TYPES and isinstance(node, _INT_VALUE_TYPES):
            return int(node.value)
        elif _FLOAT_VALUE_TYPES and isinstance(node, _FLOAT_VALUE_TYPES):
            return float(node.value)
        elif _NULL_VALUE_TYPES and isinstance(node, _NULL_VALUE_TYPES):
            return None

        raise GraphQLError(f"Cannot parse {type(node).__name__} as JSON")

    @staticmethod
    def parse_value(value: Union[str, dict, list]) -> Any:
        """Parse value to Python object."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError) as e:
                raise GraphQLError(f"Invalid JSON format: {e}")

        return value

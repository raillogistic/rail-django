"""
AST utility types for GraphQL scalars.
"""

from graphql.language import ast

_AST_STRING_VALUE = getattr(ast, "StringValue", None)
_AST_STRING_VALUE_NODE = getattr(ast, "StringValueNode", None)
_AST_OBJECT_VALUE = getattr(ast, "ObjectValue", None)
_AST_OBJECT_VALUE_NODE = getattr(ast, "ObjectValueNode", None)
_AST_LIST_VALUE = getattr(ast, "ListValue", None)
_AST_LIST_VALUE_NODE = getattr(ast, "ListValueNode", None)
_AST_BOOLEAN_VALUE = getattr(ast, "BooleanValue", None)
_AST_BOOLEAN_VALUE_NODE = getattr(ast, "BooleanValueNode", None)
_AST_INT_VALUE = getattr(ast, "IntValue", None)
_AST_INT_VALUE_NODE = getattr(ast, "IntValueNode", None)
_AST_FLOAT_VALUE = getattr(ast, "FloatValue", None)
_AST_FLOAT_VALUE_NODE = getattr(ast, "FloatValueNode", None)
_AST_NULL_VALUE = getattr(ast, "NullValue", None)
_AST_NULL_VALUE_NODE = getattr(ast, "NullValueNode", None)

_STRING_VALUE_TYPES = tuple(t for t in (_AST_STRING_VALUE, _AST_STRING_VALUE_NODE) if t)
_OBJECT_VALUE_TYPES = tuple(t for t in (_AST_OBJECT_VALUE, _AST_OBJECT_VALUE_NODE) if t)
_LIST_VALUE_TYPES = tuple(t for t in (_AST_LIST_VALUE, _AST_LIST_VALUE_NODE) if t)
_BOOLEAN_VALUE_TYPES = tuple(
    t for t in (_AST_BOOLEAN_VALUE, _AST_BOOLEAN_VALUE_NODE) if t
)
_INT_VALUE_TYPES = tuple(t for t in (_AST_INT_VALUE, _AST_INT_VALUE_NODE) if t)
_FLOAT_VALUE_TYPES = tuple(t for t in (_AST_FLOAT_VALUE, _AST_FLOAT_VALUE_NODE) if t)
_NULL_VALUE_TYPES = tuple(t for t in (_AST_NULL_VALUE, _AST_NULL_VALUE_NODE) if t)

try:
    from graphql import Undefined as _UNDEFINED
except Exception:
    try:
        from graphql.pyutils import Undefined as _UNDEFINED
    except Exception:
        _UNDEFINED = None

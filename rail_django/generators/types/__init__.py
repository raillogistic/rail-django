"""
Type Generation System Package.

This package provides the TypeGenerator class, which is responsible for converting
Django model fields and relationships into GraphQL types.
"""

from .constants import FIELD_TYPE_MAP, PYTHON_TYPE_MAP
from .generator import TypeGenerator
from .dataloaders import RelatedObjectsLoader
from .enums import get_or_create_enum_for_field
from .inputs import generate_input_type
from .objects import generate_object_type
from .inheritance import inheritance_handler

__all__ = [
    "TypeGenerator",
    "FIELD_TYPE_MAP",
    "PYTHON_TYPE_MAP",
    "RelatedObjectsLoader",
    "get_or_create_enum_for_field",
    "generate_input_type",
    "generate_object_type",
    "inheritance_handler",
]

"""
TypeGeneratorSettings implementation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import graphene
from django.db.models import Field
from .base import _get_library_defaults, _get_global_settings, _get_schema_registry_settings, _merge_settings_dicts


@dataclass
class TypeGeneratorSettings:
    """Settings for controlling GraphQL type generation."""
    exclude_fields: Dict[str, List[str]] = field(default_factory=dict)
    excluded_fields: Dict[str, List[str]] = field(default_factory=dict)
    include_fields: Optional[Dict[str, List[str]]] = None
    custom_field_mappings: Dict[type[Field], type[graphene.Scalar]] = field(default_factory=dict)
    generate_filters: bool = True
    enable_filtering: bool = True
    auto_camelcase: bool = True
    generate_descriptions: bool = True

    @classmethod
    def from_schema(cls, schema_name: str) -> "TypeGeneratorSettings":
        defaults = _get_library_defaults().get("type_generation_settings", {})
        global_settings = _get_global_settings(schema_name).get("type_generation_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get("type_generation_settings", {})
        merged = _merge_settings_dicts(defaults, global_settings, schema_settings)
        valid_fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in merged.items() if k in valid_fields})

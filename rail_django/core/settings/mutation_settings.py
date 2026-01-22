"""
MutationGeneratorSettings implementation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .base import _get_library_defaults, _get_global_settings, _get_schema_registry_settings, _merge_settings_dicts


@dataclass
class MutationGeneratorSettings:
    """Settings for controlling GraphQL mutation generation."""
    generate_create: bool = True
    generate_update: bool = True
    generate_delete: bool = True
    generate_bulk: bool = False
    enable_create: bool = True
    enable_update: bool = True
    enable_delete: bool = True
    enable_bulk_operations: bool = True
    enable_method_mutations: bool = True
    require_model_permissions: bool = True
    model_permission_codenames: Dict[str, str] = field(default_factory=lambda: {"create": "add", "update": "change", "delete": "delete"})
    bulk_batch_size: int = 100
    bulk_include_models: List[str] = field(default_factory=list)
    bulk_exclude_models: List[str] = field(default_factory=list)
    required_update_fields: Dict[str, List[str]] = field(default_factory=dict)
    enable_nested_relations: bool = True
    nested_relations_config: Dict[str, bool] = field(default_factory=dict)
    nested_field_config: Dict[str, Dict[str, bool]] = field(default_factory=dict)

    @classmethod
    def from_schema(cls, schema_name: str) -> "MutationGeneratorSettings":
        defaults = _get_library_defaults().get("mutation_settings", {})
        global_settings = _get_global_settings(schema_name).get("mutation_settings", {})
        schema_settings = _get_schema_registry_settings(schema_name).get("mutation_settings", {})
        merged = _merge_settings_dicts(defaults, global_settings, schema_settings)
        valid_fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in merged.items() if k in valid_fields})

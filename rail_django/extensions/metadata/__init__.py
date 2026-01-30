"""
Metadata: Rich Model Introspection for Frontend UI Generation.

This package provides comprehensive metadata exposure for Django models,
enabling frontends to build forms, tables, and detail views automatically.
"""

from .queries import ModelSchemaQuery
from .extractor import ModelSchemaExtractor
from .types import (
    ChoiceType,
    ComputedFilterSchemaType,
    FieldGroupType,
    FieldSchemaType,
    FilterConfigType,
    FilterOptionSchemaType,
    FilterPresetType,
    FilterSchemaType,
    FilterStyleEnum,
    FSMTransitionType,
    InputFieldSchemaType,
    ModelInfoType,
    ModelPermissionsType,
    ModelSchemaType,
    MutationSchemaType,
    RelationFilterSchemaType,
    RelationshipSchemaType,
    TemplateInfoType,
    ValidatorInfoType,
)
from .utils import (
    _classify_field,
    _get_cache_key,
    _get_fsm_transitions,
    _is_fsm_field,
    invalidate_metadata_cache,
)
from .mapping import FieldTypeRegistry, registry

__all__ = [
    # Queries
    "ModelSchemaQuery",
    # Extractor
    "ModelSchemaExtractor",
    # Types
    "ChoiceType",
    "ComputedFilterSchemaType",
    "FieldGroupType",
    "FieldSchemaType",
    "FilterConfigType",
    "FilterOptionSchemaType",
    "FilterPresetType",
    "FilterSchemaType",
    "FilterStyleEnum",
    "FSMTransitionType",
    "InputFieldSchemaType",
    "ModelInfoType",
    "ModelPermissionsType",
    "ModelSchemaType",
    "MutationSchemaType",
    "RelationFilterSchemaType",
    "RelationshipSchemaType",
    "TemplateInfoType",
    "ValidatorInfoType",
    # Utils
    "invalidate_metadata_cache",
    "_get_cache_key",
    "_classify_field",
    "_get_fsm_transitions",
    "_is_fsm_field",
    # Mapping
    "FieldTypeRegistry",
    "registry",
]

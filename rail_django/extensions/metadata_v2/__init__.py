"""
Metadata V2: Rich Model Introspection for Frontend UI Generation.

This package provides comprehensive metadata exposure for Django models,
enabling frontends to build forms, tables, and detail views automatically.
"""

from .queries import ModelSchemaQueryV2
from .extractor import ModelSchemaExtractor
from .types import (
    ChoiceTypeV2,
    ComputedFilterSchemaType,
    FieldGroupType,
    FieldSchemaType,
    FilterConfigTypeV2,
    FilterOptionSchemaType,
    FilterPresetType,
    FilterSchemaTypeV2,
    FilterStyleEnumV2,
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
    invalidate_metadata_v2_cache,
)

__all__ = [
    # Queries
    "ModelSchemaQueryV2",
    # Extractor
    "ModelSchemaExtractor",
    # Types
    "ChoiceTypeV2",
    "ComputedFilterSchemaType",
    "FieldGroupType",
    "FieldSchemaType",
    "FilterConfigTypeV2",
    "FilterOptionSchemaType",
    "FilterPresetType",
    "FilterSchemaTypeV2",
    "FilterStyleEnumV2",
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
    "invalidate_metadata_v2_cache",
    "_get_cache_key",
    "_classify_field",
    "_get_fsm_transitions",
    "_is_fsm_field",
]

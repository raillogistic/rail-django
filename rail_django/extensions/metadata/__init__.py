"""
Metadata: Rich Model Introspection for Frontend UI Generation.

This package provides comprehensive metadata exposure for Django models,
enabling frontends to build forms, tables, and detail views automatically.
"""

from .queries import ModelSchemaQuery
from .extractor import ModelSchemaExtractor
from .detail_extractor import DetailContractExtractor
from .detail_actions import (
    bind_action_template,
    execute_detail_action,
    emit_action_audit_event,
    extract_detail_action_definitions,
    resolve_detail_action_execution,
)
from .types import (
    ChoiceType,
    ComputedFilterSchemaType,
    DetailActionDefinitionType,
    DetailContractInputType,
    DetailContractResultType,
    DetailFieldDescriptorType,
    DetailLayoutNodeType,
    DetailPermissionSnapshotType,
    DetailRelationDataSourceType,
    DetailViewContractType,
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
    "DetailContractExtractor",
    # Detail actions
    "extract_detail_action_definitions",
    "resolve_detail_action_execution",
    "execute_detail_action",
    "bind_action_template",
    "emit_action_audit_event",
    # Types
    "ChoiceType",
    "ComputedFilterSchemaType",
    "DetailActionDefinitionType",
    "DetailContractInputType",
    "DetailContractResultType",
    "DetailFieldDescriptorType",
    "DetailLayoutNodeType",
    "DetailPermissionSnapshotType",
    "DetailRelationDataSourceType",
    "DetailViewContractType",
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

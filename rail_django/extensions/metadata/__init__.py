"""Metadata extension package.

This package provides metadata types and utilities for exposing
Django model information via GraphQL. It supports comprehensive
metadata extraction for models, forms, and tables with caching,
signal-based invalidation, and cache warmup utilities.

Package Structure:
    - types/: Dataclasses and GraphQL types for metadata
    - extractors/: Model, form, and table metadata extractors
    - cache: Caching utilities and decorators
    - queries: GraphQL query definitions
    - signals: Cache invalidation signal handlers
    - warmup: Cache warmup utilities

Example Usage:
    from rail_django.extensions.metadata import (
        # Extractors
        ModelMetadataExtractor,
        ModelFormMetadataExtractor,
        ModelTableExtractor,
        # GraphQL types
        ModelMetadataType,
        FieldMetadataType,
        # Caching
        cache_metadata,
        invalidate_metadata_cache,
        # Query
        ModelMetadataQuery,
    )
"""

# Types (dataclasses and GraphQL types)
from .types import (
    # Dataclasses
    FieldMetadata,
    FieldPermissionMetadata,
    FormFieldMetadata,
    FormRelationshipMetadata,
    InputFieldMetadata,
    ModelFormMetadata,
    ModelMetadata,
    ModelPermissionMatrix,
    ModelTableMetadata,
    MutationMetadata,
    RelationshipMetadata,
    TableFieldMetadata,
    TemplateActionMetadata,
    # GraphQL types - filter and input types
    ChoiceType,
    FieldPermissionMetadataType,
    FilterConfigType,
    FilterFieldType,
    FilterOptionType,
    FilterPresetType,
    FilterSchemaType,
    FilterStyleEnum,
    InputFieldMetadataType,
    ModelPermissionMatrixType,
    MutationMetadataType,
    RelationFilterType,
    # GraphQL types - model, form, and table types
    FieldMetadataType,
    FormFieldMetadataType,
    FormRelationshipMetadataType,
    ModelFormMetadataType,
    ModelMetadataType,
    ModelTableType,
    RelationshipMetadataType,
    TableFieldMetadataType,
    TemplateActionMetadataType,
)

# Extractors
from .extractors import (
    # Main extractors
    ModelMetadataExtractor,
    ModelFormMetadataExtractor,
    ModelTableExtractor,
    # Base classes
    BaseMetadataExtractor,
    JsonSerializerMixin,
    TranslationMixin,
    # Extraction mixins
    ModelFieldExtractionMixin,
    MutationExtractionMixin,
    InputFieldExtractionMixin,
    FormFieldExtractionMixin,
    TableFieldExtractionMixin,
    TableFilterExtractionMixin,
    # Helper functions
    _build_field_permission_snapshot,
    _build_model_permission_matrix,
    _is_fsm_field_instance,
    _relationship_cardinality,
)

# Cache utilities
from .cache import (
    cache_metadata,
    invalidate_metadata_cache,
    invalidate_cache_on_startup,
)

# GraphQL queries
from .queries import (
    AvailableModelType,
    ModelMetadataQuery,
    resolve_filter_schema,
)

# Signal handlers
from .signals import (
    invalidate_model_metadata_cache_on_save,
    invalidate_model_metadata_cache_on_delete,
    invalidate_m2m_metadata_cache,
    reset_migration_context_cache,
)

# Cache warmup utilities
from .warmup import (
    warm_metadata_cache,
    warm_table_metadata_cache,
    get_cache_stats,
    get_metadata_cache_stats,
    get_combined_cache_stats,
    clear_all_caches,
)


__all__ = [
    # Dataclasses
    "FieldMetadata",
    "FieldPermissionMetadata",
    "FormFieldMetadata",
    "FormRelationshipMetadata",
    "InputFieldMetadata",
    "ModelFormMetadata",
    "ModelMetadata",
    "ModelPermissionMatrix",
    "ModelTableMetadata",
    "MutationMetadata",
    "RelationshipMetadata",
    "TableFieldMetadata",
    "TemplateActionMetadata",
    # GraphQL types - filter and input
    "ChoiceType",
    "FieldPermissionMetadataType",
    "FilterConfigType",
    "FilterFieldType",
    "FilterOptionType",
    "FilterPresetType",
    "FilterSchemaType",
    "FilterStyleEnum",
    "InputFieldMetadataType",
    "ModelPermissionMatrixType",
    "MutationMetadataType",
    "RelationFilterType",
    # GraphQL types - model, form, table
    "FieldMetadataType",
    "FormFieldMetadataType",
    "FormRelationshipMetadataType",
    "ModelFormMetadataType",
    "ModelMetadataType",
    "ModelTableType",
    "RelationshipMetadataType",
    "TableFieldMetadataType",
    "TemplateActionMetadataType",
    # Extractors
    "ModelMetadataExtractor",
    "ModelFormMetadataExtractor",
    "ModelTableExtractor",
    "BaseMetadataExtractor",
    "JsonSerializerMixin",
    "TranslationMixin",
    # Extraction mixins
    "ModelFieldExtractionMixin",
    "MutationExtractionMixin",
    "InputFieldExtractionMixin",
    "FormFieldExtractionMixin",
    "TableFieldExtractionMixin",
    "TableFilterExtractionMixin",
    # Cache utilities
    "cache_metadata",
    "invalidate_metadata_cache",
    "invalidate_cache_on_startup",
    # GraphQL queries
    "AvailableModelType",
    "ModelMetadataQuery",
    "resolve_filter_schema",
    # Signal handlers
    "invalidate_model_metadata_cache_on_save",
    "invalidate_model_metadata_cache_on_delete",
    "invalidate_m2m_metadata_cache",
    "reset_migration_context_cache",
    # Cache warmup
    "warm_metadata_cache",
    "warm_table_metadata_cache",
    "get_cache_stats",
    "get_metadata_cache_stats",
    "get_combined_cache_stats",
    "clear_all_caches",
    # Internal helpers (exported for backward compatibility)
    "_build_field_permission_snapshot",
    "_build_model_permission_matrix",
    "_is_fsm_field_instance",
    "_relationship_cardinality",
]

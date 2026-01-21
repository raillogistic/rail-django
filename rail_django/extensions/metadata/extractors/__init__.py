"""Metadata extractors package.

This package provides classes for extracting metadata from Django models
for use in GraphQL schema generation and frontend applications.

Extractors:
    - ModelMetadataExtractor: Extracts comprehensive model metadata including
      fields, relationships, permissions, filters, and mutations.
    - ModelFormMetadataExtractor: Extracts form-specific metadata for frontend
      form generation with validation rules and widget types.
    - ModelTableExtractor: Extracts table display metadata including fields,
      filters, mutations, and PDF template actions.

Base utilities:
    - BaseMetadataExtractor: Base class with shared functionality.
    - JsonSerializerMixin: JSON serialization utilities.
    - TranslationMixin: Filter help text translation utilities.
    - _build_field_permission_snapshot: Build field-level permission info.
    - _build_model_permission_matrix: Build model-level CRUD permissions.

Mixins:
    - ModelFieldExtractionMixin: Model field extraction functionality.
    - MutationExtractionMixin: Mutation metadata extraction functionality.
    - InputFieldExtractionMixin: Input field extraction from models/methods.
    - FormFieldExtractionMixin: Form field extraction functionality.
    - TableFieldExtractionMixin: Table field extraction functionality.
    - TableFilterExtractionMixin: Table filter extraction functionality.
"""

from .base import (
    BaseMetadataExtractor,
    JsonSerializerMixin,
    TranslationMixin,
    _build_field_permission_snapshot,
    _build_model_permission_matrix,
    _is_fsm_field_instance,
    _relationship_cardinality,
)
from .form_extractor import ModelFormMetadataExtractor
from .form_fields import FormFieldExtractionMixin
from .model_extractor import ModelMetadataExtractor
from .model_fields import ModelFieldExtractionMixin
from .model_mutations import MutationExtractionMixin
from .mutation_inputs import InputFieldExtractionMixin
from .table_extractor import ModelTableExtractor
from .table_fields import TableFieldExtractionMixin, TableFilterExtractionMixin

__all__ = [
    # Extractors
    "ModelMetadataExtractor",
    "ModelFormMetadataExtractor",
    "ModelTableExtractor",
    # Base classes and mixins
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
    # Helper functions
    "_build_field_permission_snapshot",
    "_build_model_permission_matrix",
    "_is_fsm_field_instance",
    "_relationship_cardinality",
]

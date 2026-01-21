"""Metadata types package.

This package provides dataclasses and GraphQL types for representing
metadata about Django models, fields, relationships, forms, tables,
and permissions.
"""

# Dataclasses
from .base import (
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
)

# GraphQL types - filter and input types
from .graphql_types import (
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
)

# GraphQL types - model, form, and table types
from .model_types import (
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
    # GraphQL types - filter and input types
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
    # GraphQL types - model, form, and table types
    "FieldMetadataType",
    "FormFieldMetadataType",
    "FormRelationshipMetadataType",
    "ModelFormMetadataType",
    "ModelMetadataType",
    "ModelTableType",
    "RelationshipMetadataType",
    "TableFieldMetadataType",
    "TemplateActionMetadataType",
]

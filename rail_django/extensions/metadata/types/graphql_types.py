"""GraphQL types for filter and input metadata.

This module contains Graphene ObjectType classes for filters, inputs,
mutations, and permissions used in the metadata schema.
"""

import graphene


class ChoiceType(graphene.ObjectType):
    """GraphQL type for choice options."""

    value = graphene.String(required=True, description="Choice value")
    label = graphene.String(required=True, description="Choice label")


class FilterOptionType(graphene.ObjectType):
    """GraphQL type for individual filter options within a grouped filter."""

    name = graphene.String(
        required=True, description="Filter option name (e.g., 'slug__iexact')"
    )
    lookup_expr = graphene.String(
        required=True, description="Django lookup expression (e.g., 'iexact')"
    )
    help_text = graphene.String(
        required=True,
        description="Filter help text in French using field verbose_name",
    )
    filter_type = graphene.String(
        required=True, description="Filter class type (e.g., 'CharFilter')"
    )
    choices = graphene.List(
        ChoiceType,
        description="Available choices for the field (if any, typically for CharField)",
    )


class FilterFieldType(graphene.ObjectType):
    """GraphQL type for grouped filter field metadata."""

    field_name = graphene.String(required=True, description="Target model field name")
    is_nested = graphene.Boolean(
        required=True, description="Whether this is a nested filter"
    )
    related_model = graphene.String(description="Related model name for nested filters")
    is_custom = graphene.Boolean(
        required=True, description="Whether this includes custom filters"
    )
    field_label = graphene.String(
        required=True, description="Human-readable label for the field"
    )

    options = graphene.List(
        FilterOptionType,
        required=True,
        description="List of filter options for this field",
    )

    # Nested filter fields for related lookups (e.g., famille__code)
    nested = graphene.List(
        lambda: FilterFieldType,
        description="Nested filter fields for related model attributes",
    )

    # New fields for nested filter style support
    filter_input_type = graphene.String(
        description="Nested filter input type (e.g., StringFilterInput)"
    )
    available_operators = graphene.List(
        graphene.String,
        description="Available operators for nested filter style",
    )


class FilterPresetType(graphene.ObjectType):
    """Filter preset metadata for introspection."""

    name = graphene.String(required=True, description="Preset name")
    description = graphene.String(description="Preset description")
    filter_json = graphene.JSONString(
        required=True, description="Filter configuration"
    )


class FilterSchemaType(graphene.ObjectType):
    """Schema for model filter introspection."""

    model = graphene.String(required=True, description="Model name")
    fields = graphene.List(
        lambda: FilterFieldType, required=True, description="Available filter fields"
    )
    presets = graphene.List(
        FilterPresetType, required=True, description="Available filter presets"
    )
    supports_fts = graphene.Boolean(
        required=True, description="Whether full-text search is supported"
    )
    supports_aggregation = graphene.Boolean(
        required=True, description="Whether aggregation filtering is supported"
    )


class FilterStyleEnum(graphene.Enum):
    """Filter input style enumeration."""

    FLAT = "flat"
    NESTED = "nested"


class FilterConfigType(graphene.ObjectType):
    """Filter configuration for a model."""

    style = graphene.Field(
        FilterStyleEnum, required=True, description="Filter input style"
    )
    argument_name = graphene.String(
        required=True, description="GraphQL argument name ('filters' or 'where')"
    )
    input_type_name = graphene.String(
        required=True, description="Filter input type name"
    )
    supports_and = graphene.Boolean(required=True, description="Supports AND operator")
    supports_or = graphene.Boolean(required=True, description="Supports OR operator")
    supports_not = graphene.Boolean(required=True, description="Supports NOT operator")
    dual_mode_enabled = graphene.Boolean(
        required=True, description="Both filter styles available"
    )


class RelationFilterType(graphene.ObjectType):
    """Relation filter metadata for M2M and reverse relations."""

    relation_name = graphene.String(required=True, description="Relation field name")
    relation_type = graphene.String(
        required=True, description="Type (MANY_TO_MANY, REVERSE_FK)"
    )
    supports_some = graphene.Boolean(
        required=True, description="Supports _some quantifier"
    )
    supports_every = graphene.Boolean(
        required=True, description="Supports _every quantifier"
    )
    supports_none = graphene.Boolean(
        required=True, description="Supports _none quantifier"
    )
    supports_count = graphene.Boolean(
        required=True, description="Supports _count filter"
    )
    nested_filter_type = graphene.String(
        description="Nested filter input type for the related model"
    )


class InputFieldMetadataType(graphene.ObjectType):
    """GraphQL type for input field metadata."""

    name = graphene.String(required=True, description="Field name")
    field_type = graphene.String(required=True, description="Field data type")
    required = graphene.Boolean(required=True, description="Whether field is required")
    default_value = graphene.JSONString(description="Default value for the field")
    description = graphene.String(description="Field description")
    choices = graphene.List(
        graphene.JSONString, description="Available choices for the field"
    )
    validation_rules = graphene.JSONString(description="Validation rules as JSON")
    widget_type = graphene.String(description="Recommended UI widget type")
    placeholder = graphene.String(description="Placeholder text for input")
    help_text = graphene.String(description="Help text for the field")
    min_length = graphene.Int(description="Minimum length for string fields")
    max_length = graphene.Int(description="Maximum length for string fields")
    min_value = graphene.Float(description="Minimum value for numeric fields")
    max_value = graphene.Float(description="Maximum value for numeric fields")
    pattern = graphene.String(description="Regex pattern for validation")
    related_model = graphene.String(description="Related model name for foreign keys")
    multiple = graphene.Boolean(
        required=True, description="Whether field accepts multiple values"
    )


class MutationMetadataType(graphene.ObjectType):
    """GraphQL type for mutation metadata."""

    name = graphene.String(required=True, description="Mutation name")
    method_name = graphene.String(description="Underlying model method name")
    description = graphene.String(description="Mutation description")
    input_fields = graphene.List(
        InputFieldMetadataType,
        required=True,
        description="Input fields for the mutation",
    )
    return_type = graphene.String(description="Return type of the mutation")
    input_type = graphene.String(description="GraphQL input type for the mutation")
    requires_authentication = graphene.Boolean(
        required=True, description="Whether mutation requires authentication"
    )
    required_permissions = graphene.List(
        graphene.String,
        required=True,
        description="Required permissions to execute mutation",
    )
    mutation_type = graphene.String(
        required=True, description="Type of mutation (create, update, delete, custom)"
    )
    model_name = graphene.String(description="Associated model name")
    form_config = graphene.JSONString(description="Frontend form configuration")
    validation_schema = graphene.JSONString(
        description="Validation schema for the mutation"
    )
    success_message = graphene.String(description="Success message template")
    error_messages = graphene.JSONString(description="Error message templates")
    action = graphene.JSONString(description="UI action metadata for row actions")


class FieldPermissionMetadataType(graphene.ObjectType):
    """GraphQL type exposing field-level permission metadata."""

    can_read = graphene.Boolean(
        required=True, description="Whether the current user may read the field"
    )
    can_write = graphene.Boolean(
        required=True, description="Whether the current user may edit the field"
    )
    visibility = graphene.String(
        required=True,
        description="Resolved visibility (visible, hidden, masked, redacted)",
    )
    access_level = graphene.String(
        required=True, description="Access level value (none, read, write, admin)"
    )
    mask_value = graphene.String(
        description="Mask value used when the field is partially hidden"
    )
    reason = graphene.String(
        description="Optional explanation describing why the field is restricted"
    )


class ModelPermissionMatrixType(graphene.ObjectType):
    """GraphQL type describing model-level permissions for the current user."""

    can_create = graphene.Boolean(
        required=True, description="Whether create operations are permitted"
    )
    can_update = graphene.Boolean(
        required=True, description="Whether update operations are permitted"
    )
    can_delete = graphene.Boolean(
        required=True, description="Whether delete operations are permitted"
    )
    can_read = graphene.Boolean(
        required=True, description="Whether retrieve/detail operations are permitted"
    )
    can_list = graphene.Boolean(
        required=True, description="Whether listing operations are permitted"
    )
    can_history = graphene.Boolean(
        required=True,
        description="Whether history operations are permitted",
    )
    reasons = graphene.JSONString(
        description="Optional mapping of operation identifiers to denial reasons"
    )

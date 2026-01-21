"""GraphQL types for model, form, and table metadata.

This module contains Graphene ObjectType classes for model fields,
relationships, forms, and table metadata used in the metadata schema.
"""

import graphene
from graphene.types.generic import GenericScalar

from .graphql_types import (
    ChoiceType,
    FieldPermissionMetadataType,
    FilterFieldType,
    ModelPermissionMatrixType,
    MutationMetadataType,
)


class FieldMetadataType(graphene.ObjectType):
    """GraphQL type for field metadata."""

    name = graphene.String(required=True, description="Field name")
    field_type = graphene.String(required=True, description="Django field type")
    is_required = graphene.Boolean(
        required=True, description="Whether field is required"
    )
    is_nullable = graphene.Boolean(
        required=True, description="Whether field can be null"
    )
    null = graphene.Boolean(required=True, description="Whether field can be null")
    default_value = graphene.String(description="Default value as string")
    help_text = graphene.String(description="Field help text")
    db_column = graphene.String(description="Database column name")
    db_type = graphene.String(description="Database column type")
    internal_type = graphene.String(description="Django internal field type")
    max_length = graphene.Int(description="Maximum length for string fields")
    min_length = graphene.Int(description="Minimum length for string fields")
    min_value = GenericScalar(description="Minimum allowed value")
    max_value = GenericScalar(description="Maximum allowed value")
    regex = graphene.String(description="Regex validation pattern")
    choices = graphene.List(ChoiceType, description="Field choices")
    is_primary_key = graphene.Boolean(
        required=True, description="Whether field is primary key"
    )
    is_foreign_key = graphene.Boolean(
        required=True, description="Whether field is foreign key"
    )
    is_unique = graphene.Boolean(
        required=True, description="Whether field has unique constraint"
    )
    is_indexed = graphene.Boolean(required=True, description="Whether field is indexed")
    has_auto_now = graphene.Boolean(
        required=True, description="Whether field has auto_now"
    )
    has_auto_now_add = graphene.Boolean(
        required=True, description="Whether field has auto_now_add"
    )
    blank = graphene.Boolean(required=True, description="Whether field can be blank")
    editable = graphene.Boolean(required=True, description="Whether field is editable")
    verbose_name = graphene.String(required=True, description="Field verbose name")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission for this field"
    )


class RelationshipMetadataType(graphene.ObjectType):
    """GraphQL type for relationship metadata."""

    name = graphene.String(required=True, description="Relationship field name")
    relationship_type = graphene.String(
        required=True, description="Type of relationship"
    )
    cardinality = graphene.String(
        required=True, description="Relationship cardinality"
    )
    related_model = graphene.String(
        required=True,
        description="Related model name",
    )
    related_app = graphene.String(required=True, description="Related model app")
    to_field = graphene.String(description="Target field name")
    from_field = graphene.String(required=True, description="Source field name")
    is_reverse = graphene.Boolean(
        required=True, description="Whether this is a reverse relationship"
    )
    is_required = graphene.Boolean(
        required=True, description="Whether this is a reverse relationship"
    )
    many_to_many = graphene.Boolean(
        required=True, description="Whether this is many-to-many"
    )
    one_to_one = graphene.Boolean(
        required=True, description="Whether this is one-to-one"
    )
    foreign_key = graphene.Boolean(
        required=True, description="Whether this is foreign key"
    )
    on_delete = graphene.String(description="On delete behavior")
    related_name = graphene.String(description="Related name for reverse lookups")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission for this relationship"
    )
    verbose_name = graphene.String(required=True, description="Model verbose name")


class ModelMetadataType(graphene.ObjectType):
    """GraphQL type for complete model metadata."""

    metadataVersion = graphene.String(
        required=True,
        description="Stable metadata version identifier for this model metadata",
        source="metadata_version",
    )
    app_name = graphene.String(required=True, description="Django app name")
    model_name = graphene.String(required=True, description="Model class name")
    verbose_name = graphene.String(required=True, description="Model verbose name")
    verbose_name_plural = graphene.String(
        required=True, description="Model verbose name plural"
    )
    table_name = graphene.String(required=True, description="Database table name")
    primary_key_field = graphene.String(
        required=True, description="Primary key field name"
    )
    fields = graphene.List(FieldMetadataType, required=True, description="Model fields")
    relationships = graphene.List(
        RelationshipMetadataType, required=True, description="Model relationships"
    )
    permissions = graphene.List(
        graphene.String, required=True, description="Available permissions"
    )
    ordering = graphene.List(
        graphene.String, required=True, description="Default ordering"
    )
    default_ordering = graphene.List(
        graphene.String,
        required=True,
        description="Fallback ordering applied when no explicit ordering is set",
    )
    unique_together = graphene.List(
        graphene.List(graphene.String),
        required=True,
        description="Unique together constraints",
    )
    unique_constraints = graphene.List(
        graphene.JSONString,
        required=True,
        description="Unique constraints defined on the model",
    )
    indexes = graphene.List(
        graphene.JSONString, required=True, description="Database indexes"
    )
    abstract = graphene.Boolean(required=True, description="Whether model is abstract")
    proxy = graphene.Boolean(required=True, description="Whether model is proxy")
    managed = graphene.Boolean(
        required=True, description="Whether model is managed by Django"
    )
    filters = graphene.List(
        FilterFieldType, required=True, description="Available filter fields"
    )
    mutations = graphene.List(
        MutationMetadataType,
        required=True,
        description="Available mutations for this model",
    )


class FormFieldMetadataType(graphene.ObjectType):
    """GraphQL type for form field metadata."""

    name = graphene.String(required=True, description="Field name")
    field_type = graphene.String(required=True, description="Django field type")
    is_required = graphene.Boolean(
        required=True, description="Whether field is required"
    )
    verbose_name = graphene.String(required=True, description="Field verbose name")
    help_text = graphene.String(description="Field help text")
    widget_type = graphene.String(
        required=True, description="Recommended UI widget type"
    )
    placeholder = graphene.String(description="Placeholder text for input")
    default_value = graphene.JSONString(description="Default value for the field")
    choices = graphene.List(ChoiceType, description="Field choices")
    max_length = graphene.Int(description="Maximum length for string fields")
    min_length = graphene.Int(description="Minimum length for string fields")
    decimal_places = graphene.Int(description="Number of decimal places")
    max_digits = graphene.Int(description="Maximum number of digits")
    min_value = graphene.Float(description="Minimum value for numeric fields")
    max_value = graphene.Float(description="Maximum value for numeric fields")
    auto_now = graphene.Boolean(required=True, description="Whether field has auto_now")
    auto_now_add = graphene.Boolean(
        required=True, description="Whether field has auto_now_add"
    )
    blank = graphene.Boolean(required=True, description="Whether field can be blank")
    null = graphene.Boolean(required=True, description="Whether field can be null")
    unique = graphene.Boolean(
        required=True, description="Whether field has unique constraint"
    )
    editable = graphene.Boolean(required=True, description="Whether field is editable")
    validators = graphene.List(graphene.String, description="Field validators")
    error_messages = graphene.JSONString(description="Custom error messages")
    disabled = graphene.Boolean(
        required=True, description="Whether field is disabled in form"
    )
    readonly = graphene.Boolean(
        required=True, description="Whether field is readonly in form"
    )
    css_classes = graphene.String(description="CSS classes for form field")
    data_attributes = graphene.JSONString(description="Data attributes for form field")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission to access this field"
    )
    permissions = graphene.Field(
        FieldPermissionMetadataType,
        description="Detailed permission metadata for the field",
    )


class FormRelationshipMetadataType(graphene.ObjectType):
    """GraphQL type for form relationship metadata."""

    name = graphene.String(required=True, description="Relationship field name")
    relationship_type = graphene.String(
        required=True, description="Type of relationship"
    )
    cardinality = graphene.String(
        required=True, description="Relationship cardinality"
    )
    verbose_name = graphene.String(required=True, description="Field verbose name")
    help_text = graphene.String(description="Field help text")
    widget_type = graphene.String(
        required=True, description="Recommended UI widget type"
    )
    is_required = graphene.Boolean(
        required=True, description="Whether field is required"
    )
    related_model = graphene.String(
        required=True,
        description="Related model name",
    )
    related_app = graphene.String(required=True, description="Related model app")
    to_field = graphene.String(description="Target field name")
    from_field = graphene.String(required=True, description="Source field name")
    many_to_many = graphene.Boolean(
        required=True, description="Whether this is many-to-many"
    )
    one_to_one = graphene.Boolean(
        required=True, description="Whether this is one-to-one"
    )
    foreign_key = graphene.Boolean(
        required=True, description="Whether this is foreign key"
    )
    is_reverse = graphene.Boolean(
        required=True, description="Whether this is a reverse relationship"
    )
    multiple = graphene.Boolean(
        required=True, description="Whether field accepts multiple values"
    )
    queryset_filters = graphene.JSONString(description="Queryset filters for choices")
    empty_label = graphene.String(description="Empty choice label")
    limit_choices_to = graphene.JSONString(
        description="Limit choices to specific criteria"
    )
    disabled = graphene.Boolean(
        required=True, description="Whether field is disabled in form"
    )
    readonly = graphene.Boolean(
        required=True, description="Whether field is readonly in form"
    )
    css_classes = graphene.String(description="CSS classes for form field")
    data_attributes = graphene.JSONString(description="Data attributes for form field")
    has_permission = graphene.Boolean(
        required=True, description="Whether user has permission to access this field"
    )
    permissions = graphene.Field(
        FieldPermissionMetadataType,
        description="Detailed permission metadata for this relationship",
    )


class ModelFormMetadataType(graphene.ObjectType):
    """GraphQL type for complete model form metadata."""

    metadataVersion = graphene.String(
        required=True,
        description="Stable metadata version identifier for cache coordination",
        source="metadata_version",
    )
    app_name = graphene.String(required=True, description="Django app name")
    model_name = graphene.String(required=True, description="Model class name")
    verbose_name = graphene.String(required=True, description="Model verbose name")
    verbose_name_plural = graphene.String(
        required=True, description="Model verbose name plural"
    )
    # Relationship linkage information for nested metadata entries
    # These are typically only populated for nested entries
    name = graphene.String(
        description="Deprecated: use field_name; retained for compatibility"
    )
    field_name = graphene.String(
        description="Parent relationship field name that produced this nested metadata"
    )
    relationship_type = graphene.String(
        description="Relationship type for the parent field "
        "(ForeignKey, ManyToManyField, OneToOneField)"
    )
    to_field = graphene.String(
        description="Target field name on the related model (if specified)"
    )
    from_field = graphene.String(description="Source field name on the parent model")
    is_required = graphene.Boolean(
        description="Whether the parent relationship field is required"
    )
    form_title = graphene.String(required=True, description="Form title")
    form_description = graphene.String(description="Form description")
    fields = graphene.List(
        FormFieldMetadataType, required=True, description="Form fields"
    )
    relationships = graphene.List(
        FormRelationshipMetadataType, required=True, description="Form relationships"
    )
    nested = graphene.List(
        lambda: ModelFormMetadataType,
        required=True,
        description="Nested form metadata for specified fields",
    )
    # Form configuration
    field_order = graphene.List(graphene.String, description="Field display order")
    exclude_fields = graphene.List(
        graphene.String, required=True, description="Fields to exclude from form"
    )
    readonly_fields = graphene.List(
        graphene.String, required=True, description="Fields that are readonly"
    )
    # Validation and permissions
    required_permissions = graphene.List(
        graphene.String, required=True, description="Required permissions"
    )
    form_validation_rules = graphene.JSONString(description="Form validation rules")
    # UI configuration
    form_layout = graphene.JSONString(description="Form layout configuration")
    css_classes = graphene.String(description="CSS classes for form")
    form_attributes = graphene.JSONString(description="Form HTML attributes")
    permissions = graphene.Field(
        ModelPermissionMatrixType,
        description="Operation-level permissions for the current user",
    )


class TableFieldMetadataType(graphene.ObjectType):
    """GraphQL type for table field metadata used in data grid."""

    name = graphene.String(required=True, description="Field name")
    accessor = graphene.String(required=True, description="Field accessor")
    display = graphene.String(required=True, description="Field display accessor")
    editable = graphene.Boolean(required=True, description="Whether field is editable")
    field_type = graphene.String(required=True, description="Field data type")
    filterable = graphene.Boolean(
        required=True, description="Whether field is filterable"
    )
    sortable = graphene.Boolean(required=True, description="Whether field is sortable")
    title = graphene.String(required=True, description="Field title (verbose name)")
    help_text = graphene.String(required=True, description="Help text or description")
    is_property = graphene.Boolean(
        required=True, description="Whether field is a property"
    )
    is_related = graphene.Boolean(required=True, description="Whether field is related")
    permissions = graphene.Field(
        FieldPermissionMetadataType,
        description="Permission metadata for this table column",
    )


class TemplateActionMetadataType(graphene.ObjectType):
    """GraphQL type exposing printable template metadata for ModelTable consumers."""

    key = graphene.String(
        required=True, description="Stable identifier for the template"
    )
    methodName = graphene.String(
        required=True,
        description="Model method name declared with @model_pdf_template",
        source="method_name",
    )
    title = graphene.String(required=True, description="Human readable title")
    endpoint = graphene.String(
        required=True,
        description="Relative endpoint prefix under /api for this template",
    )
    urlPath = graphene.String(
        required=True,
        description="Template path appended to the templating URL prefix",
        source="url_path",
    )
    guard = graphene.String(
        description="GraphQL guard name enforced when rendering this template"
    )
    requireAuthentication = graphene.Boolean(
        required=True,
        description="Whether authentication is required to hit this endpoint",
        source="require_authentication",
    )
    roles = graphene.List(
        graphene.String,
        required=True,
        description="Roles required to access the template",
    )
    permissions = graphene.List(
        graphene.String,
        required=True,
        description="Permissions required to access the template",
    )
    allowed = graphene.Boolean(
        required=True, description="Whether the current user passes static checks"
    )
    denialReason = graphene.String(
        description="Reason describing why the template is unavailable",
        source="denial_reason",
    )
    allowClientData = graphene.Boolean(
        required=True,
        description="Permet a l'utilisateur de fournir des donnees personnalisees",
        source="allow_client_data",
    )
    clientDataFields = graphene.List(
        graphene.String,
        required=True,
        description="Cles autorisees pour les donnees client",
        source="client_data_fields",
    )
    clientDataSchema = graphene.List(
        graphene.JSONString,
        required=True,
        description="Schema des champs client (name/type)",
        source="client_data_schema",
    )


class ModelTableType(graphene.ObjectType):
    """GraphQL type for comprehensive table metadata for a Django model."""

    metadataVersion = graphene.String(
        required=True,
        description="Stable metadata version identifier for this table metadata",
        source="metadata_version",
    )
    app = graphene.String(required=True, description="Application name")
    model = graphene.String(required=True, description="Model name")
    verbose_name = graphene.String(required=True, description="Singular verbose name")
    verbose_name_plural = graphene.String(
        required=True, description="Plural verbose name"
    )
    table_name = graphene.String(required=True, description="Database table name")
    primary_key = graphene.String(required=True, description="Primary key field name")
    ordering = graphene.List(
        graphene.String, required=True, description="Default ordering fields"
    )
    default_ordering = graphene.List(
        graphene.String, required=True, description="Fallback ordering fields"
    )
    get_latest_by = graphene.String(description="Field used by 'latest' manager")
    managers = graphene.List(
        graphene.String, required=True, description="Manager names"
    )
    managed = graphene.Boolean(
        required=True, description="Whether Django manages the table"
    )
    fields = graphene.List(
        TableFieldMetadataType, required=True, description="All field metadata"
    )
    generics = graphene.List(
        TableFieldMetadataType, required=True, description="GenericRelation fields"
    )
    filters = graphene.List(
        FilterFieldType,
        required=True,
        description="Available filters with field structure",
    )
    permissions = graphene.Field(
        ModelPermissionMatrixType,
        description="Operation-level permissions for listing and mutations",
    )
    mutations = graphene.List(
        MutationMetadataType,
        description="Available GraphQL mutations relevant to this model",
    )
    pdfTemplates = graphene.List(
        TemplateActionMetadataType,
        description="Printable templates derived from @model_pdf_template decorators",
        source="pdf_templates",
    )

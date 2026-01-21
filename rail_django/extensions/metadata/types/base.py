"""Base dataclasses for metadata schema.

This module contains all dataclasses used for representing metadata about
Django models, fields, relationships, forms, tables, and permissions.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class InputFieldMetadata:
    """Metadata for mutation input fields."""

    name: str
    field_type: str
    required: bool
    default_value: Optional[Any] = None
    description: Optional[str] = None
    choices: Optional[list[dict[str, Any]]] = None
    validation_rules: Optional[dict[str, Any]] = None
    widget_type: Optional[str] = None
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None
    related_model: Optional[str] = None
    multiple: bool = False


@dataclass
class MutationMetadata:
    """Metadata for GraphQL mutations."""

    name: str
    method_name: Optional[str] = None
    description: Optional[str] = None
    input_fields: list[InputFieldMetadata] = field(default_factory=list)
    return_type: Optional[str] = None
    input_type: Optional[str] = None
    requires_authentication: bool = True
    required_permissions: list[str] = field(default_factory=list)
    mutation_type: str = "custom"  # create, update, delete, custom
    model_name: Optional[str] = None
    form_config: Optional[dict[str, Any]] = None
    validation_schema: Optional[dict[str, Any]] = None
    success_message: Optional[str] = None
    error_messages: Optional[dict[str, str]] = None
    action: Optional[dict[str, Any]] = None


@dataclass
class FieldMetadata:
    """Metadata for a single model field."""

    name: str
    field_type: str
    is_required: bool
    is_nullable: bool
    null: bool
    default_value: Any
    help_text: str
    db_column: Optional[str]
    db_type: Optional[str]
    internal_type: Optional[str]
    max_length: Optional[int]
    min_length: Optional[int]
    min_value: Optional[Union[int, float]]
    max_value: Optional[Union[int, float]]
    regex: Optional[str]
    choices: Optional[list[dict[str, str]]]
    is_primary_key: bool
    is_foreign_key: bool
    is_unique: bool
    is_indexed: bool
    has_auto_now: bool
    has_auto_now_add: bool
    blank: bool
    editable: bool
    verbose_name: str
    has_permission: bool


@dataclass
class RelationshipMetadata:
    """Metadata for model relationships."""

    name: str
    relationship_type: str
    cardinality: str
    related_model: str
    related_app: str
    to_field: Optional[str]
    from_field: str
    is_reverse: bool
    is_required: bool
    many_to_many: bool
    one_to_one: bool
    foreign_key: bool
    on_delete: Optional[str]
    related_name: Optional[str]
    has_permission: bool
    verbose_name: str


@dataclass
class FieldPermissionMetadata:
    """Permission snapshot for a field."""

    can_read: bool
    can_write: bool
    visibility: str
    access_level: str
    mask_value: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class ModelPermissionMatrix:
    """Model-level CRUD permissions for the current user."""

    can_create: bool = True
    can_update: bool = True
    can_delete: bool = True
    can_read: bool = True
    can_list: bool = True
    can_history: bool = True
    reasons: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class ModelMetadata:
    """Complete metadata for a Django model."""

    metadata_version: str
    app_name: str
    model_name: str
    verbose_name: str
    verbose_name_plural: str
    table_name: str
    primary_key_field: str
    fields: list[FieldMetadata]
    relationships: list[RelationshipMetadata]
    permissions: list[str]
    ordering: list[str]
    default_ordering: list[str]
    unique_together: list[list[str]]
    unique_constraints: list[dict[str, Any]]
    indexes: list[dict[str, Any]]
    abstract: bool
    proxy: bool
    managed: bool
    filters: list[dict[str, Any]]
    mutations: list["MutationMetadata"]


@dataclass
class FormFieldMetadata:
    """Metadata for form fields with Django-specific attributes."""

    name: str
    field_type: str
    is_required: bool
    verbose_name: str
    help_text: str
    widget_type: str
    placeholder: Optional[str] = None
    default_value: Any = None
    choices: Optional[list[dict[str, str]]] = None
    # Django CharField attributes
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    # Django DecimalField attributes
    decimal_places: Optional[int] = None
    max_digits: Optional[int] = None
    # Django IntegerField/FloatField attributes
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    # Django DateField/DateTimeField attributes
    auto_now: bool = False
    auto_now_add: bool = False
    # Common field attributes
    blank: bool = False
    null: bool = False
    unique: bool = False
    editable: bool = True
    # Validation attributes
    validators: Optional[list[str]] = None
    error_messages: Optional[dict[str, str]] = None
    # Form-specific attributes
    disabled: bool = False
    readonly: bool = False
    css_classes: Optional[str] = None
    data_attributes: Optional[dict[str, str]] = None
    has_permission: bool = True
    permissions: Optional[FieldPermissionMetadata] = None


@dataclass
class FormRelationshipMetadata:
    """Metadata for form relationship fields with nested model information."""

    name: str
    relationship_type: str
    cardinality: str
    verbose_name: str
    help_text: str
    widget_type: str
    is_required: bool
    # Related model information
    related_model: str
    related_app: str
    to_field: Optional[str] = None
    from_field: str = ""
    # Relationship characteristics
    many_to_many: bool = False
    one_to_one: bool = False
    foreign_key: bool = False
    is_reverse: bool = False
    # Form-specific attributes
    multiple: bool = False
    queryset_filters: Optional[dict[str, Any]] = None
    empty_label: Optional[str] = None
    limit_choices_to: Optional[dict[str, Any]] = None
    # UI attributes
    disabled: bool = False
    readonly: bool = False
    css_classes: Optional[str] = None
    data_attributes: Optional[dict[str, str]] = None
    has_permission: bool = True
    permissions: Optional[FieldPermissionMetadata] = None


@dataclass
class ModelFormMetadata:
    """Complete metadata for Django model forms."""

    metadata_version: str
    app_name: str
    model_name: str
    verbose_name: str
    verbose_name_plural: str
    form_title: str

    form_description: Optional[str]
    fields: list[FormFieldMetadata]
    relationships: list[FormRelationshipMetadata]
    nested: list["ModelFormMetadata"] = field(default_factory=list)
    # Form configuration
    field_order: Optional[list[str]] = None
    # When this instance is produced as a nested metadata entry for a relationship,
    # these attributes describe the parent relationship that led to this nesting.
    # They remain None for top-level metadata.
    name: Optional[str] = None
    field_name: Optional[str] = None
    relationship_type: Optional[str] = None
    to_field: Optional[str] = None
    from_field: Optional[str] = None
    is_required: Optional[bool] = None
    exclude_fields: list[str] = field(default_factory=list)
    readonly_fields: list[str] = field(default_factory=list)
    # Validation and permissions
    required_permissions: list[str] = field(default_factory=list)
    form_validation_rules: Optional[dict[str, Any]] = None
    # UI configuration
    form_layout: Optional[dict[str, Any]] = None
    css_classes: Optional[str] = None
    form_attributes: Optional[dict[str, str]] = None
    permissions: Optional[ModelPermissionMatrix] = None


@dataclass
class TableFieldMetadata:
    """Metadata for a table field used in data grid displays."""

    name: str
    accessor: str
    display: str
    editable: bool
    field_type: str
    filterable: bool
    sortable: bool
    title: str
    help_text: str
    is_property: bool
    is_related: bool
    permissions: Optional[FieldPermissionMetadata] = None


@dataclass
class TemplateActionMetadata:
    """Metadata describing a printable template action exposed to the frontend."""

    key: str
    method_name: str
    title: str
    endpoint: str
    url_path: str
    guard: Optional[str]
    require_authentication: bool
    roles: list[str]
    permissions: list[str]
    allowed: bool
    denial_reason: Optional[str] = None
    allow_client_data: bool = False
    client_data_fields: list[str] = field(default_factory=list)
    client_data_schema: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ModelTableMetadata:
    """Comprehensive table metadata for a Django model, including fields and filters."""

    metadata_version: str
    app: str
    model: str
    verbose_name: str
    verbose_name_plural: str
    table_name: str
    primary_key: str
    ordering: list[str]
    default_ordering: list[str]
    get_latest_by: Optional[str]
    managers: list[str]
    managed: bool
    fields: list[TableFieldMetadata]
    generics: list[TableFieldMetadata]
    filters: list[dict[str, Any]]
    permissions: Optional[ModelPermissionMatrix] = None
    mutations: list[MutationMetadata] = field(default_factory=list)
    pdf_templates: list[TemplateActionMetadata] = field(default_factory=list)

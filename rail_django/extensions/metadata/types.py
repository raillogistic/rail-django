"""
GraphQL types for Metadata V2.

This module contains Graphene ObjectType classes for model schema introspection.
"""

import graphene


class ChoiceType(graphene.ObjectType):
    """Choice option for select fields."""

    value = graphene.String(required=True)
    label = graphene.String(required=True)
    group = graphene.String()
    disabled = graphene.Boolean()


class ValidatorInfoType(graphene.ObjectType):
    """Validator information."""

    type = graphene.String(required=True)
    params = graphene.JSONString()
    message = graphene.String()


class FSMTransitionType(graphene.ObjectType):
    """FSM state transition."""

    name = graphene.String(required=True)
    source = graphene.List(graphene.String, required=True)
    target = graphene.String(required=True)
    label = graphene.String()
    description = graphene.String()
    permission = graphene.String()
    allowed = graphene.Boolean(required=True)


class FieldSchemaType(graphene.ObjectType):
    """Complete field schema for UI rendering."""

    # Identity
    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    help_text = graphene.String()

    # Type info
    field_type = graphene.String(required=True)
    graphql_type = graphene.String(required=True)
    python_type = graphene.String()

    # Constraints
    required = graphene.Boolean(required=True)
    nullable = graphene.Boolean(required=True)
    blank = graphene.Boolean(required=True)
    editable = graphene.Boolean(required=True)
    unique = graphene.Boolean(required=True)

    # Value constraints
    max_length = graphene.Int()
    min_length = graphene.Int()
    max_value = graphene.Float()
    min_value = graphene.Float()
    decimal_places = graphene.Int()
    max_digits = graphene.Int()

    # Choices
    choices = graphene.List(ChoiceType)

    # Default
    default_value = graphene.JSONString()
    has_default = graphene.Boolean(required=True)
    auto_now = graphene.Boolean(required=True)
    auto_now_add = graphene.Boolean(required=True)

    # Validators
    validators = graphene.List(ValidatorInfoType)
    regex_pattern = graphene.String()

    # Permissions
    readable = graphene.Boolean(required=True)
    writable = graphene.Boolean(required=True)
    visibility = graphene.String(required=True)

    # Classification flags
    is_primary_key = graphene.Boolean(required=True)
    is_indexed = graphene.Boolean(required=True)
    is_relation = graphene.Boolean(required=True)
    is_computed = graphene.Boolean(required=True)
    is_file = graphene.Boolean(required=True)
    is_image = graphene.Boolean(required=True)
    is_json = graphene.Boolean(required=True)
    is_date = graphene.Boolean(required=True)
    is_datetime = graphene.Boolean(required=True)
    is_numeric = graphene.Boolean(required=True)
    is_boolean = graphene.Boolean(required=True)
    is_text = graphene.Boolean(required=True)
    is_rich_text = graphene.Boolean(required=True)
    is_fsm_field = graphene.Boolean(required=True)

    # FSM
    fsm_transitions = graphene.List(FSMTransitionType)

    # Custom metadata
    custom_metadata = graphene.JSONString()


class RelationshipSchemaType(graphene.ObjectType):
    """Relationship field schema."""

    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    help_text = graphene.String()

    # Related model
    related_app = graphene.String(required=True)
    related_model = graphene.String(required=True)
    related_model_verbose = graphene.String(required=True)

    # Relationship type
    relation_type = graphene.String(required=True)
    is_reverse = graphene.Boolean(required=True)
    is_to_one = graphene.Boolean(required=True)
    is_to_many = graphene.Boolean(required=True)

    # Config
    on_delete = graphene.String()
    related_name = graphene.String()
    through_model = graphene.String()

    # Constraints
    required = graphene.Boolean(required=True)
    nullable = graphene.Boolean(required=True)
    editable = graphene.Boolean(required=True)

    # Lookup
    lookup_field = graphene.String(required=True)
    search_fields = graphene.List(graphene.String)

    # Permissions
    readable = graphene.Boolean(required=True)
    writable = graphene.Boolean(required=True)
    can_create_inline = graphene.Boolean(required=True)

    # Custom
    custom_metadata = graphene.JSONString()


class InputFieldSchemaType(graphene.ObjectType):
    """Mutation input field schema."""

    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    field_type = graphene.String(required=True)
    graphql_type = graphene.String(required=True)
    required = graphene.Boolean(required=True)
    default_value = graphene.JSONString()
    description = graphene.String()
    choices = graphene.List(ChoiceType)
    related_model = graphene.String()


class MutationSchemaType(graphene.ObjectType):
    """Available mutation schema."""

    name = graphene.String(required=True)
    operation = graphene.String(required=True)
    description = graphene.String()
    method_name = graphene.String()
    input_fields = graphene.List(InputFieldSchemaType, required=True)
    allowed = graphene.Boolean(required=True)
    required_permissions = graphene.List(graphene.String)
    reason = graphene.String()

    # Extra fields for compatibility/frontend
    mutation_type = graphene.String()
    model_name = graphene.String()
    form_config = graphene.JSONString()
    success_message = graphene.String()
    requires_authentication = graphene.Boolean()


class FilterOptionSchemaType(graphene.ObjectType):
    """Filter option/operator schema."""

    name = graphene.String(required=True)
    lookup = graphene.String(required=True)
    label = graphene.String(
        required=True, description="Human-readable label (e.g. 'Equals')"
    )
    help_text = graphene.String()
    choices = graphene.List(ChoiceType)
    graphql_type = graphene.String(description="GraphQL type for this operator")
    is_list = graphene.Boolean(description="Whether this operator accepts a list")


class FilterStyleEnum(graphene.Enum):
    """Filter input style."""

    FLAT = "flat"
    NESTED = "nested"


class RelationFilterSchemaType(graphene.ObjectType):
    """Relation filter schema for M2M and reverse relations."""

    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    relation_type = graphene.String(required=True)
    supports_some = graphene.Boolean(required=True)
    supports_every = graphene.Boolean(required=True)
    supports_none = graphene.Boolean(required=True)
    supports_count = graphene.Boolean(required=True)
    nested_filter_type = graphene.String()


class FilterPresetType(graphene.ObjectType):
    """Filter preset metadata."""

    name = graphene.String(required=True)
    preset_name = graphene.String(required=True)
    description = graphene.String()
    filter_json = graphene.JSONString(required=True)


class FilterSchemaType(graphene.ObjectType):
    """Filter field schema with support for both flat and nested styles."""

    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    field_label = graphene.String(required=True)
    base_type = graphene.String(
        description="Base type of the field (String, Int, Date, etc.) for UI widget selection"
    )
    is_nested = graphene.Boolean(required=True)
    related_model = graphene.String()
    options = graphene.List(FilterOptionSchemaType, required=True)

    # New fields for nested filter style
    filter_input_type = graphene.String(
        description="Filter input type (e.g., StringFilterInput)"
    )
    available_operators = graphene.List(
        graphene.String, description="Available operators for nested style"
    )


class ComputedFilterSchemaType(graphene.ObjectType):
    """Computed filter schema."""

    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    filter_type = graphene.String(required=True)
    description = graphene.String()


class FilterConfigType(graphene.ObjectType):
    """Overall filter configuration for a model."""

    style = graphene.Field(FilterStyleEnum, required=True)
    argument_name = graphene.String(
        required=True, description="'where' for nested filtering"
    )
    input_type_name = graphene.String(required=True, description="e.g., UserWhereInput")
    supports_and = graphene.Boolean(required=True)
    supports_or = graphene.Boolean(required=True)
    supports_not = graphene.Boolean(required=True)
    dual_mode_enabled = graphene.Boolean(
        required=True, description="Both filter styles available"
    )
    # Advanced filtering capabilities
    supports_fts = graphene.Boolean(
        required=True, description="Full-text search supported"
    )
    supports_aggregation = graphene.Boolean(
        required=True, description="Aggregation filters supported"
    )
    presets = graphene.List(FilterPresetType, description="Available filter presets")
    computed_filters = graphene.List(
        ComputedFilterSchemaType, description="Available computed filters"
    )


class ModelPermissionsType(graphene.ObjectType):
    """Model-level permissions for current user."""

    can_list = graphene.Boolean(required=True)
    can_retrieve = graphene.Boolean(required=True)
    can_create = graphene.Boolean(required=True)
    can_update = graphene.Boolean(required=True)
    can_delete = graphene.Boolean(required=True)
    can_bulk_create = graphene.Boolean(required=True)
    can_bulk_update = graphene.Boolean(required=True)
    can_bulk_delete = graphene.Boolean(required=True)
    can_export = graphene.Boolean(required=True)
    denial_reasons = graphene.JSONString()


class FieldGroupType(graphene.ObjectType):
    """Field grouping hint for frontend organization."""

    key = graphene.String(required=True)
    label = graphene.String(required=True)
    description = graphene.String()
    fields = graphene.List(graphene.String, required=True)
    collapsed = graphene.Boolean()


class TemplateInfoType(graphene.ObjectType):
    """Available template info."""

    key = graphene.String(required=True)
    title = graphene.String(required=True)
    description = graphene.String()
    endpoint = graphene.String(required=True)
    url_path = graphene.String()
    guard = graphene.String()
    require_authentication = graphene.Boolean()
    roles = graphene.List(graphene.String)
    permissions = graphene.List(graphene.String)
    allowed = graphene.Boolean()
    denial_reason = graphene.String()
    allow_client_data = graphene.Boolean()
    client_data_fields = graphene.List(graphene.String)
    client_data_schema = graphene.JSONString()


class ModelInfoType(graphene.ObjectType):
    """Basic model info."""

    app = graphene.String(required=True)
    model = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    verbose_name_plural = graphene.String(required=True)


class ModelSchemaType(graphene.ObjectType):
    """Complete model schema for UI generation."""

    # Identity
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    verbose_name_plural = graphene.String(required=True)

    # Structure
    primary_key = graphene.String(required=True)
    ordering = graphene.List(graphene.String)
    unique_together = graphene.List(graphene.List(graphene.String))

    # Fields
    fields = graphene.List(FieldSchemaType, required=True)
    relationships = graphene.List(RelationshipSchemaType, required=True)

    # Filters
    filters = graphene.List(FilterSchemaType, required=True)
    filter_config = graphene.Field(
        FilterConfigType, description="Filter style configuration"
    )
    relation_filters = graphene.List(
        RelationFilterSchemaType,
        description="Relation filters for M2M and reverse relations (nested style)",
    )

    # Mutations
    mutations = graphene.List(MutationSchemaType, required=True)

    # Permissions
    permissions = graphene.Field(ModelPermissionsType, required=True)

    # Hints
    field_groups = graphene.List(FieldGroupType)

    # Templates
    templates = graphene.List(TemplateInfoType)

    # Cache
    metadata_version = graphene.String(required=True)

    # Custom
    custom_metadata = graphene.JSONString()

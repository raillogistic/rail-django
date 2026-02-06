"""
GraphQL types for Form API.
"""

from __future__ import annotations

import graphene


class ModelRefInput(graphene.InputObjectType):
    app = graphene.String(required=True)
    model = graphene.String(required=True)

    class Meta:
        name = "ModelRef"


class FormModeEnum(graphene.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    VIEW = "VIEW"

    class Meta:
        name = "FormMode"


class FieldInputTypeEnum(graphene.Enum):
    TEXT = "TEXT"
    TEXTAREA = "TEXTAREA"
    NUMBER = "NUMBER"
    DECIMAL = "DECIMAL"
    EMAIL = "EMAIL"
    PASSWORD = "PASSWORD"
    URL = "URL"
    PHONE = "PHONE"
    SELECT = "SELECT"
    MULTISELECT = "MULTISELECT"
    RADIO = "RADIO"
    CHECKBOX = "CHECKBOX"
    SWITCH = "SWITCH"
    DATE = "DATE"
    TIME = "TIME"
    DATETIME = "DATETIME"
    FILE = "FILE"
    IMAGE = "IMAGE"
    JSON = "JSON"
    RICH_TEXT = "RICH_TEXT"
    COLOR = "COLOR"
    SLUG = "SLUG"
    UUID = "UUID"
    HIDDEN = "HIDDEN"
    CUSTOM = "CUSTOM"

    class Meta:
        name = "FieldInputType"


class FieldConstraintsType(graphene.ObjectType):
    max_length = graphene.Int()
    min_length = graphene.Int()
    max_value = graphene.Float()
    min_value = graphene.Float()
    pattern = graphene.String()
    pattern_message = graphene.String()
    decimal_places = graphene.Int()
    max_digits = graphene.Int()
    allowed_extensions = graphene.List(graphene.String)
    max_file_size = graphene.Int()


class ChoiceOptionType(graphene.ObjectType):
    value = graphene.String(required=True)
    label = graphene.String(required=True)
    group = graphene.String()
    disabled = graphene.Boolean()
    description = graphene.String()


class ValidatorTypeEnum(graphene.Enum):
    REQUIRED = "REQUIRED"
    MIN_LENGTH = "MIN_LENGTH"
    MAX_LENGTH = "MAX_LENGTH"
    MIN_VALUE = "MIN_VALUE"
    MAX_VALUE = "MAX_VALUE"
    PATTERN = "PATTERN"
    EMAIL = "EMAIL"
    URL = "URL"
    UNIQUE = "UNIQUE"
    CUSTOM = "CUSTOM"

    class Meta:
        name = "ValidatorType"


class ValidatorConfigType(graphene.ObjectType):
    type = graphene.String(required=True)
    params = graphene.JSONString()
    message = graphene.String()
    async_field = graphene.Boolean(required=True, name="async")


class UploadStrategyEnum(graphene.Enum):
    GRAPHQL_UPLOAD = "GRAPHQL_UPLOAD"
    DIRECT_UPLOAD = "DIRECT_UPLOAD"

    class Meta:
        name = "UploadStrategy"


class UploadConfigType(graphene.ObjectType):
    strategy = UploadStrategyEnum(required=True)
    allowed_extensions = graphene.List(graphene.String)
    max_file_size = graphene.Int()
    max_files = graphene.Int()
    direct_upload_url = graphene.String()


class FieldConfigType(graphene.ObjectType):
    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    label = graphene.String(required=True)
    description = graphene.String()
    input_type = FieldInputTypeEnum(required=True)
    graphql_type = graphene.String(required=True)
    python_type = graphene.String(required=True)
    required = graphene.Boolean(required=True)
    nullable = graphene.Boolean(required=True)
    read_only = graphene.Boolean(required=True)
    disabled = graphene.Boolean(required=True)
    hidden = graphene.Boolean(required=True)
    constraints = graphene.Field(FieldConstraintsType)
    choices = graphene.List(ChoiceOptionType)
    default_value = graphene.JSONString()
    has_default = graphene.Boolean(required=True)
    validators = graphene.List(ValidatorConfigType)
    placeholder = graphene.String()
    help_text = graphene.String()
    order = graphene.Int()
    col_span = graphene.Int()
    input_props = graphene.JSONString()
    metadata = graphene.JSONString()
    upload_config = graphene.Field(UploadConfigType)


class RelationTypeEnum(graphene.Enum):
    FOREIGN_KEY = "FOREIGN_KEY"
    ONE_TO_ONE = "ONE_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"
    REVERSE_FK = "REVERSE_FK"
    REVERSE_M2M = "REVERSE_M2M"

    class Meta:
        name = "RelationType"


class RelationOperationsType(graphene.ObjectType):
    can_connect = graphene.Boolean(required=True)
    can_create = graphene.Boolean(required=True)
    can_update = graphene.Boolean(required=True)
    can_disconnect = graphene.Boolean(required=True)
    can_set = graphene.Boolean(required=True)
    can_delete = graphene.Boolean(required=True)
    can_clear = graphene.Boolean(required=True)
    connect_permission = graphene.String()
    create_permission = graphene.String()
    update_permission = graphene.String()
    delete_permission = graphene.String()


class RelationQueryConfigType(graphene.ObjectType):
    query_name = graphene.String()
    value_field = graphene.String(required=True)
    label_field = graphene.String(required=True)
    description_field = graphene.String()
    search_fields = graphene.List(graphene.String)
    ordering = graphene.List(graphene.String)
    limit = graphene.Int()
    filters = graphene.JSONString()


class NestedFormLayoutType(graphene.ObjectType):
    columns = graphene.Int()
    style = graphene.String()


class NestedFormConfigType(graphene.ObjectType):
    enabled = graphene.Boolean(required=True)
    fields = graphene.List(graphene.String)
    exclude_fields = graphene.List(graphene.String)
    layout = graphene.Field(NestedFormLayoutType)
    max_items = graphene.Int()
    min_items = graphene.Int()


class RelationConfigType(graphene.ObjectType):
    name = graphene.String(required=True)
    field_name = graphene.String(required=True)
    label = graphene.String(required=True)
    description = graphene.String()
    related_app = graphene.String(required=True)
    related_model = graphene.String(required=True)
    related_verbose_name = graphene.String(required=True)
    relation_type = RelationTypeEnum(required=True)
    is_to_many = graphene.Boolean(required=True)
    required = graphene.Boolean(required=True)
    read_only = graphene.Boolean(required=True)
    disabled = graphene.Boolean(required=True)
    hidden = graphene.Boolean(required=True)
    operations = graphene.Field(RelationOperationsType, required=True)
    query_config = graphene.Field(RelationQueryConfigType)
    nested_form_config = graphene.Field(NestedFormConfigType)
    placeholder = graphene.String()
    help_text = graphene.String()
    order = graphene.Int()
    metadata = graphene.JSONString()


class SectionConfigType(graphene.ObjectType):
    id = graphene.String(required=True)
    title = graphene.String()
    description = graphene.String()
    fields = graphene.List(graphene.String, required=True)
    columns = graphene.Int()
    collapsible = graphene.Boolean()
    default_collapsed = graphene.Boolean()
    condition = graphene.JSONString()


class MutationOperationEnum(graphene.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CUSTOM = "CUSTOM"

    class Meta:
        name = "MutationOperation"


class MutationInputFieldType(graphene.ObjectType):
    name = graphene.String(required=True)
    type = graphene.String(required=True)
    required = graphene.Boolean(required=True)
    default_value = graphene.JSONString()
    description = graphene.String()


class MutationConfigType(graphene.ObjectType):
    name = graphene.String(required=True)
    operation = MutationOperationEnum(required=True)
    description = graphene.String()
    input_fields = graphene.List(MutationInputFieldType, required=True)
    allowed = graphene.Boolean(required=True)
    permission = graphene.String()
    denial_reason = graphene.String()
    success_message = graphene.String()
    requires_optimistic_lock = graphene.Boolean(required=True)
    optimistic_lock_field = graphene.String()


class FormPermissionsType(graphene.ObjectType):
    can_create = graphene.Boolean(required=True)
    can_update = graphene.Boolean(required=True)
    can_delete = graphene.Boolean(required=True)
    can_view = graphene.Boolean(required=True)
    field_permissions = graphene.List(lambda: FieldPermissionType, required=True)


class FieldPermissionType(graphene.ObjectType):
    field = graphene.String(required=True)
    can_read = graphene.Boolean(required=True)
    can_write = graphene.Boolean(required=True)
    visibility = graphene.String(required=True)


class ConditionalActionEnum(graphene.Enum):
    SHOW = "SHOW"
    HIDE = "HIDE"
    ENABLE = "ENABLE"
    DISABLE = "DISABLE"
    REQUIRE = "REQUIRE"
    UNREQUIRE = "UNREQUIRE"
    SET_VALUE = "SET_VALUE"

    class Meta:
        name = "ConditionalAction"


class LogicOperatorEnum(graphene.Enum):
    AND = "AND"
    OR = "OR"

    class Meta:
        name = "LogicOperator"


class ConditionOperatorEnum(graphene.Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    IS_EMPTY = "IS_EMPTY"
    IS_NOT_EMPTY = "IS_NOT_EMPTY"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"
    MATCHES = "MATCHES"

    class Meta:
        name = "ConditionOperator"


class ConditionType(graphene.ObjectType):
    field = graphene.String(required=True)
    operator = ConditionOperatorEnum(required=True)
    value = graphene.JSONString()


class ConditionalRuleType(graphene.ObjectType):
    id = graphene.String(required=True)
    target_field = graphene.String(required=True)
    action = ConditionalActionEnum(required=True)
    dsl_version = graphene.String(required=True)
    expression = graphene.JSONString()
    logic = LogicOperatorEnum(required=True)
    conditions = graphene.List(ConditionType, required=True)


class ComputedTriggerEnum(graphene.Enum):
    ON_CHANGE = "ON_CHANGE"
    ON_BLUR = "ON_BLUR"
    ON_SUBMIT = "ON_SUBMIT"
    ON_INIT = "ON_INIT"

    class Meta:
        name = "ComputedTrigger"


class ComputedFieldType(graphene.ObjectType):
    name = graphene.String(required=True)
    expression = graphene.String(required=True)
    dsl_version = graphene.String(required=True)
    dependencies = graphene.List(graphene.String, required=True)
    trigger = ComputedTriggerEnum(required=True)
    client_side = graphene.Boolean(required=True)


class CrossFieldValidationTypeEnum(graphene.Enum):
    REQUIRED_IF = "REQUIRED_IF"
    REQUIRED_UNLESS = "REQUIRED_UNLESS"
    SAME_AS = "SAME_AS"
    DIFFERENT_FROM = "DIFFERENT_FROM"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    SUM_EQUALS = "SUM_EQUALS"
    AT_LEAST_ONE = "AT_LEAST_ONE"
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"
    CUSTOM = "CUSTOM"

    class Meta:
        name = "CrossFieldValidationType"


class ValidationRuleType(graphene.ObjectType):
    id = graphene.String(required=True)
    fields = graphene.List(graphene.String, required=True)
    type = CrossFieldValidationTypeEnum(required=True)
    params = graphene.JSONString()
    message = graphene.String(required=True)


class FormConfigType(graphene.ObjectType):
    id = graphene.ID(required=True)
    app = graphene.String(required=True)
    model = graphene.String(required=True)
    verbose_name = graphene.String(required=True)
    verbose_name_plural = graphene.String(required=True)
    fields = graphene.List(FieldConfigType, required=True)
    relations = graphene.List(RelationConfigType, required=True)
    sections = graphene.List(SectionConfigType)
    create_mutation = graphene.Field(MutationConfigType)
    update_mutation = graphene.Field(MutationConfigType)
    delete_mutation = graphene.Field(MutationConfigType)
    custom_mutations = graphene.List(MutationConfigType, required=True)
    permissions = graphene.Field(FormPermissionsType, required=True)
    conditional_rules = graphene.List(ConditionalRuleType, required=True)
    computed_fields = graphene.List(ComputedFieldType, required=True)
    validation_rules = graphene.List(ValidationRuleType, required=True)
    version = graphene.String(required=True)
    config_version = graphene.String(required=True)
    generated_at = graphene.DateTime(required=True)


class FormDataType(graphene.ObjectType):
    config = graphene.Field(FormConfigType, required=True)
    initial_values = graphene.JSONString(required=True)
    readonly_values = graphene.JSONString()


class TypeDefinitionOutputType(graphene.ObjectType):
    typescript = graphene.String(required=True)
    generated_at = graphene.DateTime(required=True)
    models = graphene.List(graphene.String, required=True)


class RelationUpdateInput(graphene.InputObjectType):
    id = graphene.ID(required=True)
    values = graphene.JSONString(required=True)


class RelationInput(graphene.InputObjectType):
    connect = graphene.List(graphene.ID)
    create = graphene.List(graphene.JSONString)
    update = graphene.List(RelationUpdateInput)
    disconnect = graphene.List(graphene.ID)
    delete = graphene.List(graphene.ID)
    set = graphene.List(graphene.ID)
    clear = graphene.Boolean()

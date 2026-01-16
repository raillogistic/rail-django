# Metadata V2: Unified UI Schema System

## Executive Summary

This document proposes a complete redesign of the `rail_django.extensions.metadata` module to address scalability, maintainability, and feature gaps. The new architecture introduces a **Unified UI Schema** specification that serves all frontend use cases (tables, forms, details, cards) through composable components and a single query endpoint.

---

## Current State Analysis

### File Statistics

- **File**: `rail_django/extensions/metadata.py`
- **Lines**: 6,063
- **Size**: 254 KB
- **Classes**: 30+ dataclasses and GraphQL types
- **Extractors**: 3 separate classes with overlapping logic

### Identified Issues

| Issue                                      | Impact                                                                                          | Severity  |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------- | --------- |
| **Monolithic file**                        | Hard to navigate, test, and maintain                                                            | 🔴 High   |
| **Three extractors with code duplication** | Logic repeated in `ModelMetadataExtractor`, `ModelFormMetadataExtractor`, `ModelTableExtractor` | 🔴 High   |
| **Dataclass + GraphQL type duplication**   | Every metadata struct has both Python and GraphQL definitions                                   | 🟡 Medium |
| **No layout/section support**              | Forms are flat field lists, no grouping                                                         | 🔴 High   |
| **No detail view support**                 | Read-only views must use form metadata                                                          | 🟡 Medium |
| **No conditional field logic**             | Can't show/hide fields based on other values                                                    | 🔴 High   |
| **Scattered permission checks**            | Permission logic duplicated across extractors                                                   | 🟡 Medium |
| **No state/workflow integration**          | FSM transitions not exposed                                                                     | 🟡 Medium |
| **Translation logic embedded**             | French help text generation hardcoded                                                           | 🟢 Low    |
| **No URL/action generation**               | Frontend builds URLs manually                                                                   | 🟡 Medium |

---

## Proposed Architecture

### Design Principles

1. **Single Source of Truth**: One introspector, one cache, one permission evaluator
2. **Composable Components**: Build complex UIs from simple, reusable specs
3. **Schema-Driven UI**: Declarative configuration in `GraphQLMeta.ui_schema`
4. **View-Agnostic Core**: Same field specs power tables, forms, and details
5. **Extension Points**: Registry pattern for widgets, validators, and actions
6. **Backward Compatibility**: Adapter layer for existing v1 queries

### Core Concepts

```
┌─────────────────────────────────────────────────────────────────────┐
│                         UI Schema System                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │
│  │  FieldSpec   │   │  LayoutSpec  │   │  ActionSpec  │            │
│  │              │   │              │   │              │            │
│  │ • name       │   │ • sections   │   │ • name       │            │
│  │ • type       │   │ • groups     │   │ • type       │            │
│  │ • widget     │   │ • tabs       │   │ • mutation   │            │
│  │ • validation │   │ • columns    │   │ • permissions│            │
│  │ • conditions │   │ • order      │   │ • conditions │            │
│  └──────────────┘   └──────────────┘   └──────────────┘            │
│          │                  │                  │                    │
│          └──────────────────┼──────────────────┘                    │
│                             ▼                                       │
│                    ┌──────────────────┐                             │
│                    │    ViewSpec      │                             │
│                    │                  │                             │
│                    │ • TableView      │                             │
│                    │ • FormView       │                             │
│                    │ • DetailView     │                             │
│                    │ • CardView       │                             │
│                    └──────────────────┘                             │
│                             │                                       │
│                             ▼                                       │
│                    ┌──────────────────┐                             │
│                    │  UISchemaQuery   │                             │
│                    │                  │                             │
│                    │ modelUISchema()  │                             │
│                    └──────────────────┘                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Structure

```
rail_django/extensions/metadata_v2/
├── __init__.py                 # Public API exports
├── core/
│   ├── __init__.py
│   ├── introspector.py         # Unified model introspector
│   ├── registry.py             # Widget, validator, action registries
│   └── cache.py                # Centralized cache management
├── specs/
│   ├── __init__.py
│   ├── base.py                 # BaseSpec with common functionality
│   ├── field_spec.py           # FieldSpec definition
│   ├── layout_spec.py          # LayoutSpec (sections, groups, tabs)
│   ├── action_spec.py          # ActionSpec (buttons, mutations)
│   ├── filter_spec.py          # FilterSpec (reuse/refactor existing)
│   └── relation_spec.py        # RelationSpec (inline, modal, lookup)
├── views/
│   ├── __init__.py
│   ├── base.py                 # BaseViewSpec
│   ├── table_view.py           # TableViewSpec
│   ├── form_view.py            # FormViewSpec
│   ├── detail_view.py          # DetailViewSpec
│   └── card_view.py            # CardViewSpec
├── builders/
│   ├── __init__.py
│   ├── field_builder.py        # Builds FieldSpec from Django field
│   ├── layout_builder.py       # Builds LayoutSpec from model
│   ├── action_builder.py       # Builds ActionSpec from mutations
│   ├── filter_builder.py       # Builds FilterSpec from model
│   └── view_builder.py         # Orchestrates all builders
├── graphql/
│   ├── __init__.py
│   ├── types.py                # GraphQL ObjectTypes
│   ├── inputs.py               # GraphQL InputTypes
│   ├── enums.py                # GraphQL Enums
│   └── queries.py              # UISchemaQuery
├── permissions/
│   ├── __init__.py
│   └── evaluator.py            # Centralized permission evaluation
└── compat/
    ├── __init__.py
    └── v1_adapter.py           # Maps v2 to v1 query responses
```

---

## Specification Details

### 1. FieldSpec

The atomic unit describing a model field for any UI context.

```python
@dataclass
class FieldSpec:
    """
    Complete field specification for UI rendering.

    Attributes:
        name: Field name (snake_case).
        verbose_name: Human-readable label.
        field_type: Django field type (CharField, ForeignKey, etc.).
        graphql_type: GraphQL type string (String, ID, Int, etc.).
        widget: Recommended widget identifier.

        # Validation
        required: Whether field is required.
        nullable: Whether field accepts null.
        validators: List of validation rules.
        min_length: Minimum string length.
        max_length: Maximum string length.
        min_value: Minimum numeric value.
        max_value: Maximum numeric value.
        pattern: Regex pattern for validation.

        # Display
        help_text: Field description/instructions.
        placeholder: Input placeholder text.
        default_value: Default value for creation.
        choices: List of {value, label} options.

        # Relation
        is_relation: Whether field is a relationship.
        relation_type: FK, M2M, O2O, reverse.
        related_model: Related model identifier (app.Model).
        relation_spec: Nested RelationSpec for configuration.

        # Conditions
        visible_when: Conditions for field visibility.
        required_when: Conditions for field requirement.
        disabled_when: Conditions for field disablement.
        computed_value: Expression for auto-computed values.

        # Permissions
        readable: Whether current user can read.
        writable: Whether current user can write.
        visibility: visible | masked | hidden | redacted.

        # View-specific
        table_display: Display configuration for tables.
        form_display: Display configuration for forms.
        detail_display: Display configuration for detail views.
    """
    name: str
    verbose_name: str
    field_type: str
    graphql_type: str
    widget: str

    required: bool = False
    nullable: bool = True
    validators: list[dict] = field(default_factory=list)
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None

    help_text: str = ""
    placeholder: Optional[str] = None
    default_value: Any = None
    choices: Optional[list[dict]] = None

    is_relation: bool = False
    relation_type: Optional[str] = None
    related_model: Optional[str] = None
    relation_spec: Optional["RelationSpec"] = None

    visible_when: Optional[dict] = None
    required_when: Optional[dict] = None
    disabled_when: Optional[dict] = None
    computed_value: Optional[str] = None

    readable: bool = True
    writable: bool = True
    visibility: str = "visible"

    table_display: Optional["TableFieldDisplay"] = None
    form_display: Optional["FormFieldDisplay"] = None
    detail_display: Optional["DetailFieldDisplay"] = None
```

### 2. LayoutSpec

Defines how fields are arranged in the UI.

```python
@dataclass
class LayoutSpec:
    """
    Layout specification for organizing fields in views.

    Attributes:
        type: Layout type (sections, tabs, columns, steps, accordion).
        items: List of layout items (sections, groups, or field names).
    """
    type: str = "sections"  # sections | tabs | columns | steps | accordion
    items: list["LayoutItem"] = field(default_factory=list)


@dataclass
class LayoutItem:
    """
    A single layout container (section, tab, group, column).

    Attributes:
        key: Unique identifier for the item.
        title: Display title.
        description: Optional description text.
        icon: Optional icon identifier.
        fields: List of field names in this container.
        collapsed: Whether section starts collapsed.
        columns: Number of columns for fields (1-4).
        visible_when: Condition to show this section.
        children: Nested layout items for complex layouts.
    """
    key: str
    title: str
    description: Optional[str] = None
    icon: Optional[str] = None
    fields: list[str] = field(default_factory=list)
    collapsed: bool = False
    columns: int = 1
    visible_when: Optional[dict] = None
    children: Optional[list["LayoutItem"]] = None
```

**Example Layout Definition:**

```python
class Order(models.Model):
    # fields...

    class GraphQLMeta:
        ui_schema = UISchema(
            layout=LayoutSpec(
                type="tabs",
                items=[
                    LayoutItem(
                        key="general",
                        title="Informations générales",
                        icon="info-circle",
                        fields=["reference", "date", "status", "customer"],
                        columns=2,
                    ),
                    LayoutItem(
                        key="items",
                        title="Articles",
                        icon="list",
                        fields=["order_items"],  # Inline relation
                    ),
                    LayoutItem(
                        key="shipping",
                        title="Livraison",
                        icon="truck",
                        visible_when={"status__in": ["confirmed", "shipped"]},
                        fields=["shipping_address", "tracking_number"],
                    ),
                    LayoutItem(
                        key="payment",
                        title="Paiement",
                        icon="credit-card",
                        fields=["payment_method", "total", "paid_at"],
                    ),
                ]
            )
        )
```

### 3. ActionSpec

Defines interactive actions available in the UI.

```python
@dataclass
class ActionSpec:
    """
    Action specification for buttons, menu items, and row actions.

    Attributes:
        key: Unique action identifier.
        label: Display label.
        description: Action description (for tooltips).
        icon: Icon identifier.

        # Execution
        type: Action type (mutation, link, modal, download, confirm).
        mutation: GraphQL mutation name (if type=mutation).
        url: URL pattern (if type=link or download).
        modal: Modal configuration (if type=modal).
        confirm: Confirmation dialog config (if type=confirm).

        # Input
        requires_selection: Whether action needs selected rows.
        selection_mode: single | multiple | none.
        input_fields: Additional input fields for the action.

        # State
        enabled_when: Condition for action availability.
        visible_when: Condition for action visibility.

        # Permissions
        permission: Required permission string.
        roles: Required roles.

        # Display
        variant: primary | secondary | danger | success | warning.
        position: toolbar | row | bulk | context.
        order: Sort order for positioning.
    """
    key: str
    label: str
    description: Optional[str] = None
    icon: Optional[str] = None

    type: str = "mutation"
    mutation: Optional[str] = None
    url: Optional[str] = None
    modal: Optional["ModalConfig"] = None
    confirm: Optional["ConfirmConfig"] = None

    requires_selection: bool = False
    selection_mode: str = "none"
    input_fields: list["FieldSpec"] = field(default_factory=list)

    enabled_when: Optional[dict] = None
    visible_when: Optional[dict] = None

    permission: Optional[str] = None
    roles: list[str] = field(default_factory=list)

    variant: str = "primary"
    position: str = "toolbar"
    order: int = 0


@dataclass
class ConfirmConfig:
    """Configuration for confirmation dialogs."""
    title: str
    message: str
    confirm_label: str = "Confirmer"
    cancel_label: str = "Annuler"
    variant: str = "danger"
```

### 4. RelationSpec

Defines how relationship fields are handled.

```python
@dataclass
class RelationSpec:
    """
    Specification for relationship field rendering and interaction.

    Attributes:
        mode: How to display the relation (select, modal, inline, lookup).
        display_field: Field to show as label (default: __str__).
        search_fields: Fields to search when looking up.
        preload: Whether to preload options.
        preload_limit: Max options to preload.
        create_allowed: Whether inline creation is allowed.
        filters: Default filters for the relation queryset.
        order_by: Default ordering for options.

        # For inline mode
        inline_columns: Columns to show in inline table.
        inline_layout: Layout for inline forms.
        inline_min: Minimum inline items.
        inline_max: Maximum inline items.
    """
    mode: str = "select"  # select | modal | inline | lookup | autocomplete
    display_field: str = "__str__"
    search_fields: list[str] = field(default_factory=list)
    preload: bool = True
    preload_limit: int = 100
    create_allowed: bool = False
    filters: Optional[dict] = None
    order_by: Optional[list[str]] = None

    inline_columns: Optional[list[str]] = None
    inline_layout: Optional["LayoutSpec"] = None
    inline_min: int = 0
    inline_max: Optional[int] = None
```

### 5. Conditional Logic

Support for dynamic field behavior.

```python
# Condition syntax (JSON-serializable)
{
    "field_name": "value",           # Exact match
    "field_name__in": ["a", "b"],    # In list
    "field_name__gt": 10,            # Greater than
    "field_name__isnull": True,      # Is null
    "$and": [...],                   # Logical AND
    "$or": [...],                    # Logical OR
    "$not": {...},                   # Logical NOT
}


# Example usage in GraphQLMeta
class Order(models.Model):
    is_discounted = models.BooleanField(default=False)
    discount_code = models.CharField(max_length=50, blank=True)
    discount_percent = models.DecimalField(null=True)

    class GraphQLMeta:
        ui_schema = UISchema(
            fields={
                "discount_code": FieldSpec(
                    visible_when={"is_discounted": True},
                    required_when={"is_discounted": True},
                ),
                "discount_percent": FieldSpec(
                    visible_when={"is_discounted": True},
                    min_value=0,
                    max_value=100,
                ),
            }
        )
```

---

## View Specifications

### TableViewSpec

```python
@dataclass
class TableViewSpec:
    """
    Complete table view specification.

    Attributes:
        columns: List of column configurations.
        filters: Filter specifications.
        actions: Available actions (toolbar, row, bulk).
        sorting: Default and allowed sort fields.
        pagination: Pagination configuration.
        selection: Selection mode configuration.
        grouping: Optional grouping configuration.
        export: Export options.
    """
    columns: list["TableColumn"]
    filters: list["FilterSpec"]
    actions: list["ActionSpec"]

    default_sort: Optional[str] = None
    sortable_fields: list[str] = field(default_factory=list)

    page_size: int = 25
    page_size_options: list[int] = field(default_factory=lambda: [10, 25, 50, 100])

    selection_mode: str = "multiple"  # none | single | multiple

    row_click_action: Optional[str] = None  # Action key or "detail"

    grouping: Optional["GroupingSpec"] = None
    export_formats: list[str] = field(default_factory=lambda: ["csv", "xlsx"])


@dataclass
class TableColumn:
    """
    Table column configuration.

    Attributes:
        field: Field spec reference.
        width: Column width (px, %, auto).
        align: Text alignment.
        sortable: Whether column is sortable.
        filterable: Whether column has quick filter.
        visible: Default visibility.
        pinned: Pin to left/right.
        cell_renderer: Custom cell renderer identifier.
        cell_class: CSS class for cells.
        header_class: CSS class for header.
    """
    field: FieldSpec
    width: Optional[str] = None
    align: str = "left"
    sortable: bool = True
    filterable: bool = True
    visible: bool = True
    pinned: Optional[str] = None  # left | right
    cell_renderer: Optional[str] = None
    cell_class: Optional[str] = None
    header_class: Optional[str] = None
```

### FormViewSpec

```python
@dataclass
class FormViewSpec:
    """
    Complete form view specification.

    Attributes:
        fields: Field specifications.
        layout: Layout configuration.
        actions: Form actions (submit, cancel, etc.).
        validation: Form-level validation rules.
        mode: Form mode (create, update, view).
        autosave: Autosave configuration.
    """
    fields: list[FieldSpec]
    layout: Optional[LayoutSpec] = None
    actions: list[ActionSpec] = field(default_factory=list)

    validation_rules: Optional[dict] = None

    mode: str = "create"  # create | update | view

    autosave: bool = False
    autosave_interval: int = 30  # seconds

    submit_mutation: Optional[str] = None
    success_redirect: Optional[str] = None
    success_message: Optional[str] = None
```

### DetailViewSpec

```python
@dataclass
class DetailViewSpec:
    """
    Complete detail (read-only) view specification.

    Attributes:
        sections: Content sections.
        fields: Field display configurations.
        actions: Available actions.
        related_data: Related data panels.
        header: Header configuration.
    """
    sections: list[LayoutItem]
    fields: list[FieldSpec]
    actions: list[ActionSpec] = field(default_factory=list)

    related_panels: list["RelatedPanel"] = field(default_factory=list)

    header: Optional["DetailHeader"] = None
    sidebar: Optional["DetailSidebar"] = None


@dataclass
class RelatedPanel:
    """
    Panel showing related objects.

    Attributes:
        key: Panel identifier.
        title: Panel title.
        relation_field: Field name of the relation.
        columns: Columns to display.
        actions: Panel actions.
        max_items: Maximum items to show.
        show_more_link: Link to full list.
    """
    key: str
    title: str
    relation_field: str
    columns: list[str] = field(default_factory=list)
    actions: list[ActionSpec] = field(default_factory=list)
    max_items: int = 5
    show_more_link: bool = True


@dataclass
class DetailHeader:
    """
    Header section for detail views.

    Attributes:
        title_field: Field to use as title.
        subtitle_field: Field for subtitle.
        image_field: Field for avatar/thumbnail.
        badges: Badge configurations.
        quick_actions: Header action buttons.
    """
    title_field: str
    subtitle_field: Optional[str] = None
    image_field: Optional[str] = None
    badges: list["BadgeConfig"] = field(default_factory=list)
    quick_actions: list[ActionSpec] = field(default_factory=list)


@dataclass
class BadgeConfig:
    """Badge display configuration."""
    field: str
    color_map: Optional[dict[str, str]] = None  # value -> color
    icon_map: Optional[dict[str, str]] = None   # value -> icon
```

---

## GraphQL API

### Unified Query Endpoint

```graphql
enum ViewType {
  TABLE
  FORM
  DETAIL
  CARD
}

type Query {
  """
  Retrieve the complete UI schema for a model and view type.
  """
  modelUISchema(
    appName: String!
    modelName: String!
    view: ViewType!
    mode: String # create | update | view (for forms)
    objectId: ID # for instance-specific permissions
  ): UISchemaResult!

  """
  Retrieve UI schemas for all models in an app.
  """
  appUISchemas(appName: String!, view: ViewType!): [UISchemaResult!]!

  """
  List all available models with basic info.
  """
  availableModels: [ModelInfo!]!
}

type UISchemaResult {
  model: ModelInfo!
  metadataVersion: String!

  # Core specs
  fields: [FieldSpecType!]!
  layout: LayoutSpecType
  actions: [ActionSpecType!]!
  filters: [FilterSpecType!]

  # Permissions
  permissions: ModelPermissions!

  # View-specific
  tableConfig: TableConfigType
  formConfig: FormConfigType
  detailConfig: DetailConfigType
  cardConfig: CardConfigType
}

type ModelInfo {
  app: String!
  name: String!
  verboseName: String!
  verboseNamePlural: String!
  primaryKey: String!
  endpoints: ModelEndpoints!
}

type ModelEndpoints {
  list: String!
  detail: String!
  create: String!
  update: String!
  delete: String!
}

type ModelPermissions {
  canList: Boolean!
  canCreate: Boolean!
  canUpdate: Boolean!
  canDelete: Boolean!
  canExport: Boolean!
  fieldPermissions: [FieldPermission!]!
}
```

### Field Spec GraphQL Type

```graphql
type FieldSpecType {
  name: String!
  verboseName: String!
  fieldType: String!
  graphqlType: String!
  widget: String!

  # Validation
  required: Boolean!
  nullable: Boolean!
  validators: [ValidatorType!]
  minLength: Int
  maxLength: Int
  minValue: Float
  maxValue: Float
  pattern: String

  # Display
  helpText: String
  placeholder: String
  defaultValue: JSON
  choices: [ChoiceType!]

  # Relation
  isRelation: Boolean!
  relationType: String
  relatedModel: String
  relationSpec: RelationSpecType

  # Conditions (JSON expressions)
  visibleWhen: JSON
  requiredWhen: JSON
  disabledWhen: JSON
  computedValue: String

  # Permissions
  readable: Boolean!
  writable: Boolean!
  visibility: FieldVisibility!

  # View-specific displays
  tableDisplay: TableFieldDisplayType
  formDisplay: FormFieldDisplayType
  detailDisplay: DetailFieldDisplayType
}

enum FieldVisibility {
  VISIBLE
  MASKED
  HIDDEN
  REDACTED
}

type ValidatorType {
  type: String!
  params: JSON
  message: String
}
```

---

## Widget Registry

Extensible mapping of field types to frontend widgets.

```python
# rail_django/extensions/metadata_v2/core/registry.py

class WidgetRegistry:
    """
    Registry for mapping Django field types to frontend widget identifiers.

    Default mappings can be overridden per-project or per-field.
    """

    _default_widgets: dict[str, str] = {
        # Text
        "CharField": "text-input",
        "TextField": "textarea",
        "SlugField": "slug-input",
        "URLField": "url-input",
        "EmailField": "email-input",

        # Numbers
        "IntegerField": "number-input",
        "FloatField": "decimal-input",
        "DecimalField": "currency-input",
        "PositiveIntegerField": "number-input",

        # Boolean
        "BooleanField": "checkbox",
        "NullBooleanField": "tri-state-checkbox",

        # Date/Time
        "DateField": "date-picker",
        "DateTimeField": "datetime-picker",
        "TimeField": "time-picker",
        "DurationField": "duration-input",

        # Files
        "FileField": "file-upload",
        "ImageField": "image-upload",

        # JSON
        "JSONField": "json-editor",

        # Relations
        "ForeignKey": "relation-select",
        "OneToOneField": "relation-select",
        "ManyToManyField": "multi-relation-select",

        # Choices
        "CharField_choices": "select",
        "IntegerField_choices": "select",

        # Special
        "UUIDField": "text-input",
        "IPAddressField": "ip-input",
        "GenericIPAddressField": "ip-input",

        # GIS (if available)
        "PointField": "map-point-picker",
        "PolygonField": "map-polygon-drawer",
        "LineStringField": "map-line-drawer",

        # FSM (if available)
        "FSMField": "state-select",
    }

    _custom_widgets: dict[str, str] = {}

    @classmethod
    def register(cls, field_type: str, widget: str) -> None:
        """Register a custom widget for a field type."""
        cls._custom_widgets[field_type] = widget

    @classmethod
    def get_widget(cls, field_type: str, has_choices: bool = False) -> str:
        """Get the widget identifier for a field type."""
        if has_choices:
            lookup = f"{field_type}_choices"
            if lookup in cls._custom_widgets:
                return cls._custom_widgets[lookup]
            if lookup in cls._default_widgets:
                return cls._default_widgets[lookup]

        if field_type in cls._custom_widgets:
            return cls._custom_widgets[field_type]

        return cls._default_widgets.get(field_type, "text-input")
```

---

## Configuration

### GraphQLMeta UI Schema

```python
from rail_django.extensions.metadata_v2 import UISchema, FieldSpec, LayoutSpec, ActionSpec

class Order(models.Model):
    reference = models.CharField(max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"

    class GraphQLMeta:
        ui_schema = UISchema(
            # Field overrides
            fields={
                "reference": FieldSpec(
                    widget="readonly-text",
                    form_display=FormFieldDisplay(visible=False),  # Auto-generated
                ),
                "total": FieldSpec(
                    widget="currency-input",
                    detail_display=DetailFieldDisplay(
                        format="currency",
                        highlight=True,
                    ),
                ),
                "customer": FieldSpec(
                    relation_spec=RelationSpec(
                        mode="autocomplete",
                        search_fields=["name", "email"],
                        display_field="name",
                        create_allowed=True,
                    ),
                ),
            },

            # Form layout
            form_layout=LayoutSpec(
                type="sections",
                items=[
                    LayoutItem(
                        key="main",
                        title="Informations principales",
                        fields=["customer", "status"],
                        columns=2,
                    ),
                    LayoutItem(
                        key="details",
                        title="Détails",
                        fields=["notes", "total"],
                    ),
                ],
            ),

            # Detail layout
            detail_layout=LayoutSpec(
                type="tabs",
                items=[
                    LayoutItem(key="info", title="Informations", fields=["reference", "customer", "status", "total"]),
                    LayoutItem(key="items", title="Articles", fields=["order_items"]),
                    LayoutItem(key="history", title="Historique", fields=["created_at"]),
                ],
            ),

            # Actions
            actions=[
                ActionSpec(
                    key="confirm",
                    label="Confirmer",
                    icon="check",
                    type="mutation",
                    mutation="confirmOrder",
                    enabled_when={"status": "pending"},
                    variant="success",
                    position="toolbar",
                ),
                ActionSpec(
                    key="cancel",
                    label="Annuler",
                    icon="x",
                    type="confirm",
                    mutation="cancelOrder",
                    confirm=ConfirmConfig(
                        title="Annuler la commande ?",
                        message="Cette action est irréversible.",
                        variant="danger",
                    ),
                    enabled_when={"status__in": ["pending", "confirmed"]},
                    variant="danger",
                    position="row",
                ),
                ActionSpec(
                    key="export_pdf",
                    label="Exporter PDF",
                    icon="file-pdf",
                    type="download",
                    url="/api/orders/{id}/pdf/",
                    position="row",
                ),
            ],

            # Table configuration
            table_config=TableConfig(
                default_sort="-created_at",
                columns=["reference", "customer", "status", "total", "created_at"],
                row_click_action="detail",
            ),
        )
```

### Django Settings

```python
RAIL_DJANGO_GRAPHQL = {
    "metadata_v2_settings": {
        "enabled": True,
        "cache_enabled": True,
        "cache_timeout_seconds": 600,

        # Default layouts
        "default_form_columns": 2,
        "default_table_page_size": 25,

        # Auto-generation
        "auto_generate_layouts": True,
        "auto_detect_sections": True,  # Group by field prefixes

        # Permissions
        "require_authentication": True,
        "allowed_roles": None,  # None = all authenticated users

        # Localization
        "default_locale": "fr",
        "translate_help_text": True,

        # Widgets
        "widget_overrides": {
            "DecimalField": "currency-input",
            "TextField": "rich-text-editor",
        },
    }
}
```

---

## Migration Path

### Phase 1: Parallel Implementation

- Create `metadata_v2` module alongside existing `metadata`
- Implement core specs and builders
- Add `UISchemaQuery` alongside existing queries
- No breaking changes to v1 API

### Phase 2: Compatibility Adapter

- Create `v1_adapter.py` that translates v2 responses to v1 format
- Switch v1 queries to use adapter internally
- Mark v1 queries as deprecated

### Phase 3: Frontend Migration

- Update frontend components to use v2 API
- Leverage new layout and action features
- Remove v1-specific code

### Phase 4: Cleanup

- Remove deprecated v1 adapter
- Remove old `metadata.py` file
- Update documentation

---

## Benefits Summary

| Aspect                 | Current (v1)          | Proposed (v2)                  |
| ---------------------- | --------------------- | ------------------------------ |
| **File size**          | 6,063 lines in 1 file | ~2,500 lines across 20+ files  |
| **Maintainability**    | Hard to navigate      | Modular, clear ownership       |
| **Testability**        | Large test fixtures   | Small, isolated unit tests     |
| **Layout support**     | None                  | Sections, tabs, columns, steps |
| **Conditional fields** | None                  | Full expression support        |
| **Actions**            | Basic mutations       | Complete action system         |
| **Permissions**        | Scattered             | Centralized evaluator          |
| **Extensibility**      | Hard-coded            | Registry pattern               |
| **Detail views**       | Reuse form metadata   | Dedicated DetailViewSpec       |
| **Workflow**           | None                  | FSM integration ready          |

---

## Next Steps

1. **Approval**: Review and approve this specification
2. **Skeleton**: Create module structure with empty files
3. **Core Specs**: Implement `FieldSpec`, `LayoutSpec`, `ActionSpec`
4. **Builders**: Implement auto-generation from Django models
5. **GraphQL**: Implement `UISchemaQuery`
6. **Testing**: Comprehensive test suite
7. **Documentation**: API reference and migration guide
8. **Frontend SDK**: TypeScript types and React hooks

---

## Related Documentation

- [Current Metadata Extension](extensions/metadata.md)
- [GraphQLMeta Reference](reference/meta.md)
- [Permissions Guide](reference/security.md)
- [10 Enterprise Features Roadmap](10_features.md)

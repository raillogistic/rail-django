# Metadata V2: Rich Model Introspection

## Executive Summary

This document proposes a redesign of the `rail_django.extensions.metadata` module focused on exposing **rich, structured model information** that enables frontends to build their own UI components. The backend provides comprehensive data about models, fields, relationships, and permissions — the frontend decides how to render them.

**Philosophy**: _"Here's everything you need to know about this model — you decide how to display it."_

---

## Design Principles

1. **Information, not Prescription**: Expose data types, constraints, and relationships. Don't dictate layouts or widgets.
2. **Frontend Freedom**: The frontend chooses how to render fields. Text input or rich editor? The frontend decides.
3. **Complete Picture**: Provide ALL relevant information in one query to minimize round-trips.
4. **Permission-Aware**: Include what the current user can do with each field and model.
5. **Extensible**: Support custom metadata via `GraphQLMeta` without breaking the API.

---

## Current Issues

| Issue                              | Impact                                                       |
| ---------------------------------- | ------------------------------------------------------------ |
| 6,063-line monolithic file         | Hard to maintain                                             |
| 3 separate extractors with overlap | Duplicated logic                                             |
| Multiple queries needed            | `model_metadata`, `model_form_metadata`, `model_table`       |
| Missing information                | No FSM states, no computed field hints, no method signatures |

---

## Proposed Changes

### 1. Single Unified Query

Replace three separate queries with one comprehensive endpoint:

```graphql
query {
  modelSchema(app: "orders", model: "Order") {
    # Model info
    app
    name
    verbose_name
    verbose_name_plural
    primary_key

    # All fields with complete info
    fields { ... }

    # All relationships
    relationships { ... }

    # Available filters
    filters { ... }

    # Available mutations/actions
    mutations { ... }

    # User permissions
    permissions { ... }

    # Cache coordination
    metadata_version
  }
}
```

### 2. Rich Field Information

Each field exposes comprehensive metadata:

```graphql
type FieldSchema {
  # Identity
  name: String!
  verbose_name: String!
  help_text: String

  # Type information
  field_type: String! # CharField, ForeignKey, etc.
  graphql_type: String! # String, ID, Int, etc.
  python_type: String # str, int, datetime, etc.
  # Constraints
  required: Boolean!
  nullable: Boolean!
  blank: Boolean!
  editable: Boolean!
  unique: Boolean!

  # Value constraints
  max_length: Int
  min_length: Int
  max_value: Float
  min_value: Float
  decimal_places: Int
  max_digits: Int

  # Choices (if any)
  choices: [Choice!]

  # Default value
  default_value: JSON
  has_default: Boolean!
  auto_now: Boolean!
  auto_now_add: Boolean!

  # Validation
  validators: [ValidatorInfo!]
  regex_pattern: String

  # Permissions (for current user)
  readable: Boolean!
  writable: Boolean!
  visibility: FieldVisibility! # VISIBLE, MASKED, HIDDEN
  # Classification
  is_primary_key: Boolean!
  is_indexed: Boolean!
  is_relation: Boolean!
  is_computed: Boolean! # @property or annotated
  is_file: Boolean!
  is_image: Boolean!
  is_json: Boolean!
  is_date: Boolean!
  is_datetime: Boolean!
  is_numeric: Boolean!
  is_boolean: Boolean!
  is_text: Boolean! # CharField or TextField
  is_rich_text: Boolean! # TextField with rich content hint
  # FSM (if django-fsm field)
  is_fsm_field: Boolean!
  fsm_transitions: [FSMTransition!]

  # Custom metadata from GraphQLMeta
  custom_metadata: JSON
}

type Choice {
  value: String!
  label: String!
  group: String # For grouped choices
  disabled: Boolean
  description: String
}

type ValidatorInfo {
  type: String! # regex, email, url, min_length, etc.
  params: JSON
  message: String
}

enum FieldVisibility {
  VISIBLE
  MASKED
  HIDDEN
}
```

### 3. Rich Relationship Information

```graphql
type RelationshipSchema {
  # Identity
  name: String!
  verbose_name: String!
  help_text: String

  # Related model
  related_app: String!
  related_model: String!
  related_model_verbose: String!

  # Relationship type
  relation_type: RelationType! # FOREIGN_KEY, ONE_TO_ONE, MANY_TO_MANY, REVERSE_FK, REVERSE_M2M
  is_reverse: Boolean!

  # Cardinality
  is_to_one: Boolean! # FK or O2O
  is_to_many: Boolean! # M2M or reverse
  # Configuration
  on_delete: String # CASCADE, SET_NULL, etc.
  related_name: String
  through_model: String # For M2M with through
  # Constraints
  required: Boolean!
  nullable: Boolean!
  editable: Boolean!

  # For lookups
  lookup_field: String! # Field to use for display (usually __str__)
  search_fields: [String!] # Fields to search when looking up
  # Permissions
  readable: Boolean!
  writable: Boolean!
  can_create_inline: Boolean! # Can create related object inline
  # Related model schema (for nested operations)
  related_fields: [FieldSchema!]

  # Custom metadata
  custom_metadata: JSON
}

enum RelationType {
  FOREIGN_KEY
  ONE_TO_ONE
  MANY_TO_MANY
  REVERSE_FK
  REVERSE_M2M
  GENERIC_FK
}
```

### 4. Available Mutations

Expose what operations are available:

```graphql
type MutationSchema {
  # Identity
  name: String!
  operation: MutationType! # CREATE, UPDATE, DELETE, BULK_CREATE, BULK_UPDATE, BULK_DELETE, METHOD
  description: String

  # For method mutations
  method_name: String

  # Input fields
  input_fields: [InputFieldSchema!]!

  # Permissions
  allowed: Boolean!
  required_permissions: [String!]
  reason: String # If not allowed, why?
  # Custom metadata
  custom_metadata: JSON
}

type InputFieldSchema {
  name: String!
  field_type: String!
  graphql_type: String!
  required: Boolean!
  default_value: JSON
  description: String
  choices: [Choice!]
  validators: [ValidatorInfo!]
  related_model: String # For relation inputs
}

enum MutationType {
  CREATE
  UPDATE
  DELETE
  BULK_CREATE
  BULK_UPDATE
  BULK_DELETE
  METHOD
}
```

### 5. FSM Transitions (if django-fsm installed)

```graphql
type FSMTransition {
  name: String! # Method name
  source: [String!]! # Source states (or ["*"])
  target: String! # Target state
  label: String # Human-readable label
  description: String

  # For current instance (if objectId provided)
  available: Boolean
  reason: String # If not available, why?
  # Permissions
  permission: String
  allowed: Boolean!

  # Input parameters
  params: [InputFieldSchema!]
}
```

### 6. Filter Schema

Rail Django supports two filter input styles. The metadata exposes filter information accordingly:

```graphql
type FilterSchema {
  # Identity
  name: String!
  verbose_name: String!

  # Style information
  style: FilterStyle!              # FLAT or NESTED
  argument_name: String!           # "filters" or "where"
  input_type_name: String!         # e.g., "UserComplexFilter" or "UserWhereInput"

  # Available operators (for nested style)
  operators: [FilterOperator!]

  # Field filters
  field_filters: [FieldFilterSchema!]!

  # Relation filters (nested style only)
  relation_filters: [RelationFilterSchema!]

  # Boolean operators available
  supports_and: Boolean!
  supports_or: Boolean!
  supports_not: Boolean!
}

enum FilterStyle {
  FLAT    # Django-style: field__lookup
  NESTED  # Prisma/Hasura-style: field: { lookup: value }
}

type FilterOperator {
  name: String!           # eq, neq, icontains, etc.
  description: String!
  graphql_type: String!   # String, Int, Boolean, etc.
  is_list: Boolean!       # True for "in", "not_in", "between"
}

type FieldFilterSchema {
  field_name: String!
  field_type: String!           # CharField, IntegerField, etc.
  filter_input_type: String!    # StringFilterInput, IntFilterInput, etc.
  available_operators: [String!]!
}

type RelationFilterSchema {
  relation_name: String!
  relation_type: RelationType!

  # Quantifier filters (for M2M and reverse relations)
  supports_some: Boolean!       # {relation}_some
  supports_every: Boolean!      # {relation}_every
  supports_none: Boolean!       # {relation}_none
  supports_count: Boolean!      # {relation}_count

  # Nested filter type
  nested_filter_type: String    # e.g., "CategoryWhereInput"
}
```

#### Filter Style Configuration

Configure the filter style in Django settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        # "flat" (default Django-style) or "nested" (Prisma/Hasura-style)
        "filter_input_style": "nested",

        # Enable both styles simultaneously
        "enable_dual_filter_styles": True,
    }
}
```

#### Nested Filter Operators by Type

| Field Type | Operators |
|------------|-----------|
| String | `eq`, `neq`, `contains`, `icontains`, `starts_with`, `istarts_with`, `ends_with`, `iends_with`, `in`, `not_in`, `is_null`, `regex`, `iregex` |
| Int/Float | `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `between`, `is_null` |
| Boolean | `eq`, `is_null` |
| Date | All numeric operators + `year`, `month`, `day`, `week_day`, `today`, `yesterday`, `this_week`, `past_week`, `this_month`, `past_month`, `this_year`, `past_year` |
| DateTime | All Date operators + `hour`, `minute`, `date` |
| ID/UUID | `eq`, `neq`, `in`, `not_in`, `is_null` |
| JSON | `eq`, `is_null`, `has_key`, `has_keys`, `has_any_keys` |

### 7. Model Permissions Matrix

```graphql
type ModelPermissions {
  # CRUD
  can_list: Boolean!
  can_retrieve: Boolean!
  can_create: Boolean!
  can_update: Boolean!
  can_delete: Boolean!

  # Bulk operations
  can_bulk_create: Boolean!
  can_bulk_update: Boolean!
  can_bulk_delete: Boolean!

  # Export
  can_export: Boolean!
  export_formats: [String!]

  # Other
  can_history: Boolean! # django-simple-history
  # Denial reasons
  denial_reasons: JSON # { operation: reason }
}
```

---

## GraphQL Query

### Complete Query Endpoint

```graphql
type Query {
  """
  Get complete schema information for a model.
  Includes all fields, relationships, mutations, and permissions.
  """
  modelSchema(
    app: String!
    model: String!
    objectId: ID # For instance-specific permissions/transitions
  ): ModelSchema!

  """
  List all available models.
  """
  availableModels(
    app: String # Filter by app
  ): [ModelInfo!]!

  """
  Get schemas for all models in an app.
  """
  appSchemas(app: String!): [ModelSchema!]!
}

type ModelSchema {
  # Identity
  app: String!
  model: String!
  verbose_name: String!
  verbose_name_plural: String!

  # Structure
  primary_key: String!
  ordering: [String!]
  unique_together: [[String!]!]

  # Fields
  fields: [FieldSchema!]!
  relationships: [RelationshipSchema!]!

  # Filters
  filters: [FilterSchema!]!

  # Mutations
  mutations: [MutationSchema!]!

  # Permissions
  permissions: ModelPermissions!

  # Field groups (from GraphQLMeta)
  field_groups: [FieldGroup!]

  # Templates (from templating extension)
  templates: [TemplateInfo!]

  # Computed/annotated fields
  computed_fields: [ComputedFieldSchema!]

  # Cache
  metadata_version: String!

  # Custom metadata
  custom_metadata: JSON
}

type ModelInfo {
  app: String!
  model: String!
  verbose_name: String!
  verbose_name_plural: String!
}

type FieldGroup {
  key: String!
  label: String!
  description: String
  fields: [String!]!
}

type TemplateInfo {
  key: String!
  title: String!
  description: String
  endpoint: String!
}

type ComputedFieldSchema {
  name: String!
  verbose_name: String!
  return_type: String!
  description: String
  dependencies: [String!] # Fields this depends on
}
```

---

## GraphQLMeta Extensions

Allow models to provide additional metadata:

```python
class Order(models.Model):
    reference = models.CharField(max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"

    class GraphQLMeta:
        # Group fields for frontend organization hints
        field_groups = [
            {"key": "main", "label": "Informations principales", "fields": ["reference", "customer", "status"]},
            {"key": "details", "label": "Détails", "fields": ["notes", "total"]},
        ]

        # Custom metadata per field
        field_metadata = {
            "notes": {
                "is_rich_text": True,
                "editor_type": "markdown",
            },
            "total": {
                "format": "currency",
                "currency": "DZD",
            },
        }

        # Relationship hints
        relationship_metadata = {
            "customer": {
                "search_fields": ["name", "email", "code"],
                "display_template": "{name} ({code})",
            },
        }

        # Model-level custom metadata
        custom_metadata = {
            "icon": "shopping-cart",
            "color": "#4A90D9",
        }
```

---

## Module Structure

Simplified structure focused on extraction and exposure:

```
rail_django/extensions/metadata_v2/
├── __init__.py              # Public API
├── cache.py                 # Cache management
├── extractors/
│   ├── __init__.py
│   ├── base.py              # Base extractor class
│   ├── field.py             # Field extraction
│   ├── relationship.py      # Relationship extraction
│   ├── mutation.py          # Mutation extraction
│   ├── filter.py            # Filter extraction
│   └── permission.py        # Permission extraction
├── graphql/
│   ├── __init__.py
│   ├── types.py             # All GraphQL types
│   └── queries.py           # Query resolvers
└── utils.py                 # Helper functions
```

**Estimated size**: ~1,500 lines total (vs 6,063 current)

---

## Comparison with V1

| Aspect              | V1 (Current)            | V2 (Proposed)                   |
| ------------------- | ----------------------- | ------------------------------- |
| **Philosophy**      | Mixed (data + UI hints) | Pure data exposure              |
| **Queries**         | 3 separate              | 1 unified                       |
| **File size**       | 6,063 lines             | ~1,500 lines                    |
| **Structure**       | 1 monolithic file       | Modular extractors              |
| **Layouts**         | None                    | Not included (frontend decides) |
| **Widgets**         | Widget type hints       | Not included (frontend decides) |
| **FSM support**     | Limited                 | Full transitions exposed        |
| **Custom metadata** | Scattered               | Unified `custom_metadata`       |
| **Type hints**      | Partial                 | Complete classification flags   |

---

## Frontend Usage Example

The frontend receives rich data and builds UI accordingly:

```typescript
// Frontend receives this data
const schema = await fetchModelSchema("orders", "Order");

// Frontend decides how to build form
function buildForm(schema: ModelSchema) {
  const fields = schema.fields.filter((f) => f.editable && f.writable);

  return fields.map((field) => {
    // Frontend chooses widget based on field info
    if (field.is_relation) {
      return <RelationSelect field={field} />;
    }
    if (field.choices?.length) {
      return <Select field={field} options={field.choices} />;
    }
    if (field.is_rich_text) {
      return <RichTextEditor field={field} />;
    }
    if (field.is_datetime) {
      return <DateTimePicker field={field} />;
    }
    if (field.is_numeric && field.decimal_places) {
      return <CurrencyInput field={field} />;
    }
    if (field.max_length && field.max_length > 500) {
      return <TextArea field={field} />;
    }
    return <TextInput field={field} />;
  });
}

// Frontend decides how to build table
function buildTable(schema: ModelSchema) {
  const columns = schema.fields.filter((f) => !f.is_text || f.max_length < 200);
  // ... build AG Grid / TanStack Table config
}

// Frontend groups fields using hints (if provided)
function buildSections(schema: ModelSchema) {
  if (schema.field_groups?.length) {
    return schema.field_groups.map((group) => ({
      title: group.label,
      fields: group.fields.map((name) =>
        schema.fields.find((f) => f.name === name)
      ),
    }));
  }
  // Default: single section with all fields
  return [{ title: "Informations", fields: schema.fields }];
}
```

---

## Key Benefits

1. **Simpler Backend**: Just expose data, don't manage UI logic
2. **Frontend Freedom**: Teams can style and layout as they prefer
3. **Single Query**: One request gets everything needed
4. **Rich Classification**: Boolean flags (`is_date`, `is_numeric`, etc.) help frontend auto-detect appropriate widgets
5. **Optional Hints**: `field_groups` and `custom_metadata` provide organization hints without forcing structure
6. **FSM Ready**: Full transition information exposed for workflow fields
7. **Smaller Codebase**: ~75% reduction in code size

---

## Migration Path

1. **Phase 1**: Create `metadata_v2` module with new extractors
2. **Phase 2**: Add `modelSchema` query alongside existing queries
3. **Phase 3**: Update frontend to use new query
4. **Phase 4**: Deprecate old queries, remove after transition period

---

## Open Questions

1. **Include computed fields?** Currently proposed — useful for frontends to know what's available.
2. **Nested relationship schema?** Currently limited to one level — should we support deeper?
3. **Filter schema format?** Keep current grouped format or simplify?

---

## Next Steps

1. Review and approve simplified approach
2. Create module skeleton
3. Implement field extractor
4. Implement relationship extractor
5. Implement unified query
6. Add tests
7. Update frontend

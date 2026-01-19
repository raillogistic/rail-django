# Schema Metadata (Metadata V2)

## Overview

Rail Django exposes schema metadata to enable dynamic user interfaces. This guide covers configuration, available queries, and frontend integration.

---

## Table of Contents

1. [Activation](#activation)
2. [Available Queries](#available-queries)
3. [ModelSchema Structure](#modelschema-structure)
4. [Field Classification](#field-classification)
5. [Permissions and Visibility](#permissions-and-visibility)
6. [Frontend Integration](#frontend-integration)
7. [Customization](#customization)
8. [V1 vs V2 Comparison](#v1-vs-v2-comparison)

---

## Activation

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "show_metadata": True,
    },
}
```

---

## Available Queries

### modelSchema

Retrieves complete metadata for a specific model.

```graphql
query ModelMetadata($app: String!, $model: String!) {
  modelSchema(app_label: $app, model_name: $model) {
    app_label
    model_name
    verbose_name
    verbose_name_plural
    description
    fields {
      name
      verbose_name
      field_type
      graphql_type
      is_required
      is_read_only
      is_primary_key
      is_foreign_key
      related_model
      description
      default_value
      choices {
        value
        label
      }
      validators {
        type
        params
      }
    }
    filtering {
      quick_fields
      filter_fields {
        field
        lookups
      }
    }
    ordering {
      allowed_fields
      default_ordering
    }
    access {
      operations {
        operation
        roles
      }
    }
  }
}
```

### availableModelsV2

Lists all available models with summary information.

```graphql
query AvailableModels {
  availableModelsV2 {
    app_label
    model_name
    verbose_name
    verbose_name_plural
    description
    field_count
    has_mutations
    is_user_model
  }
}
```

### appSchemas

Retrieves all models for a specific application.

```graphql
query AppModels($app: String!) {
  appSchemas(app_label: $app) {
    model_name
    verbose_name
    description
    fields {
      name
      field_type
      is_required
    }
  }
}
```

---

## ModelSchema Structure

### Complete Structure

```graphql
type ModelSchema {
  # ─── Identification ───
  app_label: String!
  model_name: String!
  verbose_name: String
  verbose_name_plural: String
  description: String

  # ─── Fields ───
  fields: [FieldSchema!]!

  # ─── Filtering ───
  filtering: FilteringConfig

  # ─── Sorting ───
  ordering: OrderingConfig

  # ─── Permissions ───
  access: AccessConfig

  # ─── Classifications ───
  classifications: [String!]
}

type FieldSchema {
  name: String!
  verbose_name: String
  field_type: String!
  graphql_type: String!

  # ─── Constraints ───
  is_required: Boolean!
  is_read_only: Boolean!
  is_primary_key: Boolean!
  is_unique: Boolean!
  max_length: Int
  min_value: Float
  max_value: Float

  # ─── Relationships ───
  is_foreign_key: Boolean!
  is_many_to_many: Boolean!
  related_model: String
  related_name: String

  # ─── Display ───
  description: String
  help_text: String
  default_value: String
  placeholder: String

  # ─── Choices ───
  choices: [ChoiceOption!]

  # ─── Validation ───
  validators: [ValidatorInfo!]

  # ─── Classifications ───
  classifications: [String!]
}
```

---

## Field Classification

### Available Flags

| Flag              | Description               |
| ----------------- | ------------------------- |
| `is_primary_key`  | Primary identifier        |
| `is_foreign_key`  | Foreign key relationship  |
| `is_many_to_many` | Many-to-many relationship |
| `is_required`     | Mandatory field           |
| `is_read_only`    | Read-only field           |
| `is_unique`       | Unique constraint         |
| `is_indexed`      | Has database index        |
| `is_searchable`   | Included in quick search  |
| `is_filterable`   | Can be filtered           |
| `is_sortable`     | Can be sorted             |

### Classifications

Custom classifications for sensitive or special fields:

```python
class Customer(models.Model):
    email = models.EmailField()
    ssn = models.CharField(max_length=11)

    class GraphQLMeta:
        classifications = GraphQLMetaConfig.Classification(
            model=["crm", "customer_data"],
            fields={
                "email": ["pii", "contact"],
                "ssn": ["pii", "sensitive", "gdpr"],
            },
        )
```

Query classifications:

```graphql
query SensitiveFields($app: String!, $model: String!) {
  modelSchema(app_label: $app, model_name: $model) {
    fields {
      name
      classifications
    }
  }
}
```

---

## Permissions and Visibility

### Visibility Levels

```graphql
type FieldSchema {
  visibility: FieldVisibility!
  # visibility is one of: VISIBLE, MASKED, HIDDEN, REDACTED
}
```

### Per-Role Visibility Query

```graphql
query FieldVisibilityForRole($app: String!, $model: String!, $role: String!) {
  modelSchemaForRole(app_label: $app, model_name: $model, role: $role) {
    fields {
      name
      visibility
      can_read
      can_write
    }
  }
}
```

---

## Frontend Integration

### Dynamic Form Generation

```typescript
import { useQuery, gql } from "@apollo/client";

const MODEL_SCHEMA = gql`
  query ModelSchema($app: String!, $model: String!) {
    modelSchema(app_label: $app, model_name: $model) {
      fields {
        name
        verbose_name
        field_type
        is_required
        is_read_only
        choices {
          value
          label
        }
        max_length
      }
    }
  }
`;

function DynamicForm({ app, model }) {
  const { data, loading } = useQuery(MODEL_SCHEMA, {
    variables: { app, model },
  });

  if (loading) return <Loading />;

  return (
    <form>
      {data.modelSchema.fields.map((field) => (
        <FormField
          key={field.name}
          name={field.name}
          label={field.verbose_name}
          type={mapFieldType(field.field_type)}
          required={field.is_required}
          readOnly={field.is_read_only}
          options={field.choices}
          maxLength={field.max_length}
        />
      ))}
    </form>
  );
}

function mapFieldType(djangoType: string): string {
  const mapping = {
    CharField: "text",
    TextField: "textarea",
    IntegerField: "number",
    DecimalField: "number",
    BooleanField: "checkbox",
    DateField: "date",
    DateTimeField: "datetime-local",
    EmailField: "email",
    URLField: "url",
    FileField: "file",
  };
  return mapping[djangoType] || "text";
}
```

### Dynamic Table Generation

```typescript
function DynamicTable({ app, model }) {
  const { data: schemaData } = useQuery(MODEL_SCHEMA, {
    variables: { app, model },
  });

  const { data: listData } = useQuery(generateListQuery(app, model));

  if (!schemaData || !listData) return <Loading />;

  const columns = schemaData.modelSchema.fields
    .filter((f) => !f.is_read_only || f.is_primary_key)
    .map((field) => ({
      key: field.name,
      header: field.verbose_name,
      sortable: schemaData.modelSchema.ordering.allowed_fields.includes(
        field.name
      ),
    }));

  return <Table columns={columns} data={listData[`${model}s`]} />;
}
```

---

## Customization

### GraphQLMeta Configuration

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    """
    Product Model with complete metadata configuration.
    """
    name = models.CharField("Name", max_length=200)
    sku = models.CharField("SKU", max_length=50, unique=True)
    price = models.DecimalField("Price", max_digits=10, decimal_places=2)
    description = models.TextField("Description", blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        # ─── Display ───
        verbose_name = "Product"
        verbose_name_plural = "Products"
        description = "Catalog product"

        # ─── Fields ───
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_id"],
            read_only=["sku", "created_at"],
        )

        # ─── Field Metadata ───
        field_metadata = {
            "name": {
                "placeholder": "Enter product name",
                "help_text": "Full product display name",
            },
            "price": {
                "min_value": 0,
                "help_text": "Price excluding tax",
            },
        }

        # ─── Filtering ───
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["eq", "gt", "lt", "between"],
                ),
            },
        )

        # ─── Sorting ───
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at"],
            default=["-created_at"],
        )
```

---

## V1 vs V2 Comparison

| Feature              | V1              | V2               |
| -------------------- | --------------- | ---------------- |
| Query name           | `modelMetadata` | `modelSchema`    |
| Field types          | Django names    | Django + GraphQL |
| Classifications      | ❌              | ✅               |
| Validators           | ❌              | ✅               |
| Visibility levels    | ❌              | ✅               |
| Per-role queries     | ❌              | ✅               |
| Filter configuration | Basic           | Complete         |
| Sort configuration   | ❌              | ✅               |
| Nested relationships | Limited         | Complete         |

### Migration from V1

```graphql
# V1 (deprecated)
query {
  modelMetadata(app_label: "store", model_name: "Product") {
    fields {
      name
      type
    }
  }
}

# V2 (recommended)
query {
  modelSchema(app_label: "store", model_name: "Product") {
    fields {
      name
      field_type
      graphql_type
      validators {
        type
        params
      }
    }
  }
}
```

---

## See Also

- [Queries](../graphql/queries.md) - Using metadata for dynamic queries
- [Configuration](../graphql/configuration.md) - show_metadata setting
- [Permissions](../security/permissions.md) - Field visibility

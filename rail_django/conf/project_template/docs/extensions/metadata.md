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
  modelSchema(appLabel: $app, modelName: $model) {
    appLabel
    modelName
    verboseName
    verboseNamePlural
    description
    fields {
      name
      verboseName
      fieldType
      graphqlType
      isRequired
      isReadOnly
      isPrimaryKey
      isForeignKey
      relatedModel
      description
      defaultValue
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
      quickFields
      filterFields {
        field
        lookups
      }
    }
    ordering {
      allowedFields
      defaultOrdering
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
    appLabel
    modelName
    verboseName
    verboseNamePlural
    description
    fieldCount
    hasMutations
    isUserModel
  }
}
```

### appSchemas

Retrieves all models for a specific application.

```graphql
query AppModels($app: String!) {
  appSchemas(appLabel: $app) {
    modelName
    verboseName
    description
    fields {
      name
      fieldType
      isRequired
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
  appLabel: String!
  modelName: String!
  verboseName: String
  verboseNamePlural: String
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
  verboseName: String
  fieldType: String!
  graphqlType: String!

  # ─── Constraints ───
  isRequired: Boolean!
  isReadOnly: Boolean!
  isPrimaryKey: Boolean!
  isUnique: Boolean!
  maxLength: Int
  minValue: Float
  maxValue: Float

  # ─── Relationships ───
  isForeignKey: Boolean!
  isManyToMany: Boolean!
  relatedModel: String
  relatedName: String

  # ─── Display ───
  description: String
  helpText: String
  defaultValue: String
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
| `isPrimaryKey`    | Primary identifier        |
| `isForeignKey`    | Foreign key relationship  |
| `isManyToMany`    | Many-to-many relationship |
| `isRequired`      | Mandatory field           |
| `isReadOnly`      | Read-only field           |
| `isUnique`        | Unique constraint         |
| `isIndexed`       | Has database index        |
| `isSearchable`    | Included in quick search  |
| `isFilterable`    | Can be filtered           |
| `isSortable`      | Can be sorted             |

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
  modelSchema(appLabel: $app, modelName: $model) {
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
  modelSchemaForRole(appLabel: $app, modelName: $model, role: $role) {
    fields {
      name
      visibility
      canRead
      canWrite
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
    modelSchema(appLabel: $app, modelName: $model) {
      fields {
        name
        verboseName
        fieldType
        isRequired
        isReadOnly
        choices {
          value
          label
        }
        maxLength
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
          label={field.verboseName}
          type={mapFieldType(field.fieldType)}
          required={field.isRequired}
          readOnly={field.isReadOnly}
          options={field.choices}
          maxLength={field.maxLength}
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
    .filter((f) => !f.isReadOnly || f.isPrimaryKey)
    .map((field) => ({
      key: field.name,
      header: field.verboseName,
      sortable: schemaData.modelSchema.ordering.allowedFields.includes(
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
| Classifications      | No              | Yes              |
| Validators           | No              | Yes              |
| Visibility levels    | No              | Yes              |
| Per-role queries     | No              | Yes              |
| Filter configuration | Basic           | Complete         |
| Sort configuration   | No              | Yes              |
| Nested relationships | Limited         | Complete         |

### Migration from V1

```graphql
# V1 (deprecated)
query {
  modelMetadata(appLabel: "store", modelName: "Product") {
    fields {
      name
      type
    }
  }
}

# V2 (recommended)
query {
  modelSchema(appLabel: "store", modelName: "Product") {
    fields {
      name
      fieldType
      graphqlType
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

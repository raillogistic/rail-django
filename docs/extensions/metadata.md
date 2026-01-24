# Schema Metadata

Rail Django exposes comprehensive schema metadata to enable dynamic user interfaces, automated form generation, and intelligent frontend clients. This extension provides a deep look into your Django models through the GraphQL API.

## Overview

The metadata extension allows frontends to:
- Discover available models and their fields.
- Understand field types, constraints, and validation rules.
- Access display information (verbose names, help text, placeholders).
- Inspect filtering and sorting capabilities.
- Determine user permissions and field visibility.

## Activation

Enable the metadata extension in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "show_metadata": True,
    },
}
```

Metadata is protected and requires an authenticated user by default.

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

### availableModels

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

## Filter Metadata

The metadata extension exposes filter information that reflects the standard nested filter style used in Rail Django.

### Filter Style

Rail Django uses a type-safe nested filter style (Prisma/Hasura style):

| Style | Argument | Type Pattern | Example |
|-------|----------|--------------|---------|
| Nested | `where` | `{Model}WhereInput` | `where: { name: { icontains: "x" } }` |

### Nested Filter Operators

Each field type exposes typed operators:

- **String**: `eq`, `neq`, `contains`, `icontains`, `startsWith`, `endsWith`, `in`, `notIn`, `isNull`, `regex`
- **Numeric**: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `notIn`, `between`, `isNull`
- **Date/DateTime**: All numeric operators plus `year`, `month`, `day`, `today`, `thisWeek`, `thisMonth`, `pastYear`
- **Boolean**: `eq`, `isNull`
- **JSON**: `eq`, `isNull`, `hasKey`, `hasKeys`, `hasAnyKeys`

### Relation Filters

Nested style includes relation quantifiers for M2M and reverse relations:

- `{relation}_some`: At least one related object matches
- `{relation}_every`: All related objects match
- `{relation}_none`: No related objects match
- `{relation}_count`: Filter by count of related objects

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

Custom classifications can be used for sensitive or special fields in `GraphQLMeta`:

```python
class Customer(models.Model):
    email = models.EmailField()
    ssn = models.CharField(max_length=11)

    class GraphQLMeta:
        classifications = {
            "model": ["crm", "customer_data"],
            "fields": {
                "email": ["pii", "contact"],
                "ssn": ["pii", "sensitive", "gdpr"],
            },
        }
```

## Permissions and Visibility

The metadata respects the security system. You can query visibility levels per role:

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

Visibility levels include: `VISIBLE`, `MASKED`, `HIDDEN`, `REDACTED`.

## Customization

Use `GraphQLMeta` to configure how metadata is generated for your models:

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    name = models.CharField("Name", max_length=200)
    sku = models.CharField("SKU", max_length=50, unique=True)

    class GraphQLMeta(GraphQLMetaConfig):
        verbose_name = "Product"
        description = "Catalog product"

        # Field specific metadata
        field_metadata = {
            "name": {
                "placeholder": "Enter product name",
                "help_text": "Full product display name",
            }
        }

        # Filtering configuration
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={
                "price": ["eq", "gt", "lt", "between"],
            },
        )
```

## See Also

- [Filtering Guide](../guides/filtering.md)
- [Permissions](../security/permissions.md)
- [GraphQLMeta Reference](../reference/meta.md)

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

The metadata extension is enabled by default. You can disable it in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "show_metadata": False,
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
        message
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
  availableModels {
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

### Instance-Aware Metadata (FSM)

You can retrieve metadata specific to a model instance (for example, valid state transitions) by providing an `objectId`.

```graphql
query InstanceMetadata($app: String!, $model: String!, $id: ID!) {
  modelSchema(appLabel: $app, modelName: $model, objectId: $id) {
    fields {
      name
      isFsmField
      fsmTransitions {
        name
        source
        target
        label
        allowed  # True if transition is valid for this instance
      }
    }
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

### Dynamic Filtering UI

The metadata API provides specific fields to help build dynamic filtering interfaces automatically:

- **`base_type`**: Hints at the type of UI widget to render for the field (for example, "String", "Number", "Boolean", "Date", "Relationship", "JSON").
- **`label`** (on filter options): Human-readable, localized label for the operator (for example, "Equals", "Greater than").

Example query for building a filter panel:

```graphql
query FilterPanelMetadata($app: String!, $model: String!) {
  filterSchema(app: $app, model: $model) {
    fieldName
    fieldLabel
    baseType
    options {
      lookup
      label
      graphqlType
      isList
    }
  }
}
```

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

### Field Type Registry

You can extend the default type mapping for custom Django fields using the `FieldTypeRegistry`. This is useful if you have custom model fields (like `PhoneNumberField` or `ColorField`) that you want to map to specific GraphQL types.

```python
from rail_django.extensions.metadata.mapping import registry
from my_app.fields import PhoneNumberField

# Register GraphQL type mapping
registry.register_graphql_mapping(PhoneNumberField, "String")
# Or use a custom scalar if available
# registry.register_graphql_mapping(PhoneNumberField, "PhoneNumber")

# Register Python type mapping (for code generation tools)
registry.register_python_mapping(PhoneNumberField, "str")
```

### GraphQLMeta

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

## Caching

Metadata generation can be expensive for complex models. The extension uses Django's cache framework to store schema results.

### Versioning Strategy

Each model has a tracked version key (`metadata_version:{app}:{model}`). When metadata is requested:
1. The current version is retrieved (or initialized).
2. A cache key is built including the version, app, model, user hash (for permissions), and object ID (if applicable).
3. If a cached schema exists, it is returned immediately.

### Invalidation

To invalidate metadata for a specific model (for example, after a schema migration or permission change), use:

```python
from rail_django.extensions.metadata.utils import invalidate_metadata_cache

# Invalidate specific model
invalidate_metadata_cache(app="my_app", model="MyModel")
```

This bumps the version token, effectively invalidating all cached entries for that model without requiring a full cache flush.

## Internationalization (i18n)

The metadata extension supports internationalization. Field labels, help text, descriptions, and filter operator labels (for example, "At least one", "All") are returned in the active language of the request. Ensure `django.middleware.locale.LocaleMiddleware` is enabled.

## See Also

- [Filtering Guide](../core/filtering.md)
- [Permissions](../security/permissions.md)
- [GraphQLMeta Reference](../reference/meta.md)

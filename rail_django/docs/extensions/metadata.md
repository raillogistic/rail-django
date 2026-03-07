# Schema metadata

Rail Django exposes schema metadata through GraphQL so your frontend can
discover models, fields, permissions, filters, mutations, and templates
without hard-coding that information.

## Overview

Use the metadata extension when you want to build dynamic forms, tables,
detail screens, filter builders, or action menus from the server contract.
The API returns data that already respects model discovery rules, field
visibility, and per-user access checks.

The extension is enabled by default. You can disable it in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "show_metadata": False,
    },
}
```

Metadata queries are protected. In practice, callers must pass both model
discovery checks and any operation-specific permission checks embedded in the
metadata payload.

## Available queries

The metadata root adds these GraphQL fields:

- `modelSchema(app, model, objectId)`
- `availableModels(app)`
- `appSchemas(app)`
- `filterSchema(app, model)`
- `fieldFilterSchema(app, model, field)`
- `customMutation(app, model, functionName, objectId)`
- `customMutations(app, model, objectId)`
- `modelTemplate(app, model, functionName, objectId)`
- `modelTemplates(app, model, objectId)`
- `modelDetailContract(input)`
- `metadataDeployVersion(key)`
- `frontendRouteAccess`

## modelSchema

`modelSchema` returns the full metadata contract for one model. Use it when
you need fields, relationships, permissions, filters, generated mutations, and
registered templates in one request.

```graphql
query ProductSchema {
  modelSchema(app: "inventory", model: "Product") {
    app
    model
    verboseName
    verboseNamePlural
    fields {
      name
      fieldName
      fieldType
      graphqlType
      required
      readable
      writable
    }
    mutations {
      name
      operation
      methodName
      allowed
    }
    templates {
      key
      templateType
      title
      endpoint
    }
    permissions {
      canList
      canRetrieve
      canCreate
      canUpdate
      canDelete
    }
    metadataVersion
  }
}
```

Pass `objectId` when mutation availability, FSM transitions, or template
permissions depend on a specific record.

```graphql
query ProductSchemaForRecord {
  modelSchema(app: "inventory", model: "Product", objectId: "42") {
    fields {
      fieldName
      isFsmField
      fsmTransitions {
        name
        target
        allowed
      }
    }
    mutations {
      name
      allowed
      reason
    }
    templates {
      key
      allowed
      denialReason
    }
  }
}
```

## availableModels and appSchemas

`availableModels` is the lightweight discovery API. `appSchemas` is the
batched version of `modelSchema` for one Django app.

```graphql
query DiscoverInventory {
  availableModels(app: "inventory") {
    app
    model
    verboseName
    verboseNamePlural
  }
}
```

```graphql
query InventorySchemas {
  appSchemas(app: "inventory") {
    model
    fields {
      fieldName
      fieldType
    }
  }
}
```

## Filter metadata

`filterSchema` returns the filter fields that the current user can use for a
model. `fieldFilterSchema` returns the definition for one filter field.

```graphql
query ProductFilters {
  filterSchema(app: "inventory", model: "Product") {
    fieldName
    fieldLabel
    baseType
    filterInputType
    availableOperators
    options {
      lookup
      label
      graphqlType
      isList
    }
  }
}
```

```graphql
query ProductNameFilter {
  fieldFilterSchema(app: "inventory", model: "Product", field: "name") {
    fieldName
    fieldLabel
    options {
      lookup
      label
    }
  }
}
```

## customMutation and customMutations

`customMutation` returns one custom model mutation. `customMutations` returns
every custom mutation exposed for the model. Both fields read from the same
metadata source as `modelSchema.mutations`, but they filter the result to
custom operations only.

Use `customMutation` when you already know the target method and need one
payload. Use `customMutations` when you want to build an action menu or inspect
all available custom operations for a record.

### Arguments

Both APIs accept:

- `app`: Django app label.
- `model`: Django model class name.
- `objectId`: Optional record identifier for instance-aware permissions.

`customMutation` also requires:

- `functionName`: The decorated mutation method name or its generated GraphQL
  name. Matching is flexible across snake case and camel case names.

### Return type

Both APIs return `MutationSchemaType` data. Common fields include:

- `name`: GraphQL mutation field name.
- `operation`: Mutation category. For these APIs, the value is always
  `custom`.
- `methodName`: Python method name on the model.
- `description`: Mutation description.
- `inputFields`: Input field definitions.
- `allowed`: Whether the current user can execute the mutation.
- `requiredPermissions`: Explicit permission codes attached to the mutation.
- `reason`: Server-provided denial reason when the mutation is unavailable.
- `mutationType`: Compatibility alias for clients that branch on mutation kind.

### Query one custom mutation

```graphql
query ProductAction {
  customMutation(
    app: "inventory"
    model: "Product"
    functionName: "mark_featured"
    objectId: "42"
  ) {
    name
    operation
    methodName
    description
    allowed
    reason
    inputFields {
      fieldName
      graphqlType
      required
    }
  }
}
```

### Query all custom mutations for a model

```graphql
query ProductActions {
  customMutations(app: "inventory", model: "Product", objectId: "42") {
    name
    methodName
    description
    allowed
    reason
  }
}
```

### Typical usage

- Use `customMutation` to lazily fetch one action definition before rendering a
  modal or submit form.
- Use `customMutations` to render all record-level actions in a toolbar or
  context menu.
- Pass `objectId` whenever action availability depends on the selected record.

## modelTemplate and modelTemplates

`modelTemplate` returns one registered model template. `modelTemplates` returns
every registered template for the model. These fields read from the same
metadata source as `modelSchema.templates`.

Templates can come from the PDF templating extension or from Excel export
registrations. The metadata payload already includes endpoint URLs and access
evaluation results for the current user.

### Arguments

Both APIs accept:

- `app`: Django app label.
- `model`: Django model class name.
- `objectId`: Optional record identifier for instance-aware access checks.

`modelTemplate` also requires:

- `functionName`: The template method name, generated key, or URL path suffix.
  Matching is flexible across snake case and camel case forms.

### Return type

Both APIs return `TemplateInfoType` data. Common fields include:

- `key`: Stable metadata key for the template entry.
- `templateType`: Template family, such as `pdf` or `excel`.
- `title`: Human-readable template title.
- `description`: Optional description.
- `endpoint`: Relative API endpoint for rendering or downloading.
- `urlPath`: Registered template path.
- `guard`: Access guard used by the template.
- `allowed`: Whether the current user can use the template.
- `denialReason`: Server-provided access denial reason.
- `requireAuthentication`: Whether authentication is required.
- `roles` and `permissions`: Declared access requirements.
- `allowClientData`, `clientDataFields`, and `clientDataSchema`: Client payload
  contract for template rendering.

### Query one model template

```graphql
query ProductSummaryTemplate {
  modelTemplate(
    app: "inventory"
    model: "Product"
    functionName: "print_summary"
    objectId: "42"
  ) {
    key
    templateType
    title
    endpoint
    urlPath
    allowed
    denialReason
  }
}
```

### Query all templates for a model

```graphql
query ProductTemplates {
  modelTemplates(app: "inventory", model: "Product", objectId: "42") {
    key
    templateType
    title
    endpoint
    allowed
  }
}
```

### Typical usage

- Use `modelTemplate` when the UI links to one known template by method name.
- Use `modelTemplates` to build a print or export menu dynamically.
- Use `objectId` when access to the template depends on the selected record.

## modelDetailContract

`modelDetailContract` resolves a metadata-driven detail page contract. This is
the best entry point when you want the server to define layout nodes, actions,
and relation data sources for a detail screen.

```graphql
query ProductDetailContract {
  modelDetailContract(
    input: {app: "inventory", model: "Product", objectId: "42"}
  ) {
    ok
    reason
    contract {
      modelName
      queryRoot
      layoutNodes {
        id
        type
        title
      }
      actions {
        key
        label
        mutationName
        allowed
      }
    }
  }
}
```

## metadataDeployVersion and frontendRouteAccess

`metadataDeployVersion` exposes the deployment-level version token used for
metadata cache invalidation. `frontendRouteAccess` returns resolved route
visibility rules for the current user.

```graphql
query MetadataVersion {
  metadataDeployVersion
}
```

```graphql
query RouteAccess {
  frontendRouteAccess {
    version
    rules {
      targetType
      target
      allowed
      denialReason
    }
  }
}
```

## GraphQLMeta customization

Use `GraphQLMeta` to add frontend-oriented metadata to your models.

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig


class Product(models.Model):
    name = models.CharField("Name", max_length=200)
    sku = models.CharField("SKU", max_length=50, unique=True)

    class GraphQLMeta(GraphQLMetaConfig):
        field_metadata = {
            "name": {
                "placeholder": "Enter product name",
                "help_text": "Full product display name",
            }
        }

        custom_metadata = {
            "ui": {
                "icon": "package",
            }
        }
```

## Cache invalidation

Metadata responses are cached. Invalidate one model's cached metadata when
schema behavior changes outside a normal deploy flow.

```python
from rail_django.extensions.metadata.utils import invalidate_metadata_cache

invalidate_metadata_cache(app="inventory", model="Product")
```

## Next steps

- Read [GraphQLMeta reference](../reference/meta.md) to customize model
  metadata.
- Read [templating](./templating.md) if you want to register PDF templates.
- Read [importing](./importing.md) if you want to expose import templates and
  import workflows.

# Form contract API reference

This reference covers the Form API GraphQL schema exposed by the `form` extension.

## Queries

### `modelFormContract`

Fetch generated contract data for a single model. Enabled by default for all
models unless excluded/disabled.

```graphql
query ModelFormContract($appLabel: String!, $modelName: String!) {
  modelFormContract(appLabel: $appLabel, modelName: $modelName, mode: CREATE) {
    id
    appLabel
    modelName
    mode
    version
    configVersion
    fields {
      path
      label
      kind
      required
      readOnly
      constraints
      validators {
        type
        message
        params
      }
    }
    sections {
      id
      title
      fieldPaths
      visible
    }
    mutationBindings {
      createOperation
      updateOperation
      bulkCreateOperation
      bulkUpdateOperation
      updateTargetPolicy
      bulkCommitPolicy
      conflictPolicy
    }
    errorPolicy {
      canonicalFormErrorKey
      fieldPathNotation
      bulkRowPrefixPattern
    }
  }
}
```

### `modelFormContractPages`

Fetch paginated generated contracts. Pagination is applied before contract
extraction, so extraction work scales with the requested page size.

```graphql
query ModelFormContractPages($page: Int!, $perPage: Int!, $models: [ModelRefInput!]) {
  modelFormContractPages(page: $page, perPage: $perPage, models: $models, mode: CREATE) {
    page
    perPage
    total
    results {
      id
      appLabel
      modelName
      mode
      version
    }
  }
}
```

### `modelFormInitialData`

Fetch initial values for generated forms. This query enforces `view` access for
the target object and returns a GraphQL error when access is denied.

```graphql
query ModelFormInitialData($appLabel: String!, $modelName: String!, $id: ID!) {
  modelFormInitialData(
    appLabel: $appLabel
    modelName: $modelName
    objectId: $id
    includeNested: true
  ) {
    appLabel
    modelName
    objectId
    values
    readonlyValues
    loadedAt
  }
}
```

### `formConfig`

Fetch configuration only (ideal for CREATE mode).

```graphql
query FormConfig($app: String!, $model: String!) {
  formConfig(app: $app, model: $model, mode: CREATE) {
    app
    model
    fields {
      name
      label
      inputType
      required
    }
    relations {
      name
      relationType
      isToMany
      operations {
        canConnect
        canCreate
        canUpdate
        canDisconnect
        canSet
        canDelete
        canClear
      }
    }
    configVersion
  }
}
```

### `formData`

Fetch configuration and initial values in a single call (UPDATE mode).

```graphql
query FormData($app: String!, $model: String!, $id: ID!) {
  formData(app: $app, model: $model, objectId: $id, mode: UPDATE) {
    config {
      app
      model
      configVersion
    }
    initialValues
  }
}
```

### `formConfigs`

Bulk config fetch for nested forms.

```graphql
query FormConfigs($models: [ModelRef!]!) {
  formConfigs(models: $models) {
    app
    model
    configVersion
  }
}
```

### `formTypeDefinitions`

Generate TypeScript definitions.

```graphql
query FormTypes($models: [ModelRef!]!) {
  formTypeDefinitions(models: $models) {
    typescript
    generatedAt
    models
  }
}
```

## Generated Contract Enable/Disable Rules

Generated contract queries are enabled by default for all models.

Disable via settings:

```python
RAIL_DJANGO_FORM = {
    "enable_cache": True,
    "cache_ttl_seconds": 3600,
    "initial_data_relation_limit": 200,
    "generated_form_excluded_models": ["store.Product"],
    "generated_form_metadata_key": "generated_form",
}
```

Configuration notes:

- `enable_cache` and `cache_ttl_seconds` control generated form config cache
  reads and writes.
- `initial_data_relation_limit` caps emitted to-many relation items per relation
  in `modelFormInitialData` (`0` disables the cap).
- Generated contracts and initial-data payloads both honor `GraphQLMeta` input
  exposure, including `exclude` and `read_only` rules.

Disable/enable per model via metadata:

```python
class Product(models.Model):
    class GraphQLMeta(RailGraphQLMeta):
        custom_metadata = {
            "generated_form": {
                "enabled": False,
            }
        }
```

When `custom_metadata.generated_form.enabled` is present, it overrides
`generated_form_excluded_models`.

If you exclude a model globally but set `enabled: True` in
`custom_metadata.generated_form`, the model is included again.

When a model is disabled/excluded, generated queries return:
`Generated form contract is not enabled for '<app>.<Model>'.`

## Inputs

### `RelationInput`

```graphql
input RelationInput {
  connect: [ID!]
  create: [JSON!]
  update: [RelationUpdateInput!]
  disconnect: [ID!]
  delete: [ID!]
  set: [ID!]
  clear: Boolean
}

input RelationUpdateInput {
  id: ID!
  values: JSON!
}
```

## Example Mutation Payload

```graphql
mutation UpdateOrder($input: JSONString) {
  updateOrder(input: $input) {
    id
  }
}
```

```json
{
  "input": {
    "id": "ord_123",
    "customer": {
      "connect": ["cus_1"]
    },
    "items": {
      "create": [
        { "product": "prod_1", "quantity": 2 }
      ],
      "update": [
        { "id": "item_1", "values": { "quantity": 3 } }
      ],
      "disconnect": ["item_2"],
      "delete": ["item_3"],
      "set": ["item_4"],
      "clear": false
    }
  }
}
```

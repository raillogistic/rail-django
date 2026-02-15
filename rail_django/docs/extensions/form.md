# Form API extension

The Form API provides first-class, model-backed form configuration and data loading for dynamic frontends. It replaces the legacy form2 metadata flow with a single, form-focused contract.

## Activation

Enabled by default. You can disable it per schema:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "show_form": True,
    },
}
```

## Generated ModelForm Contract

The generated ModelForm contract queries are enabled for all models by default.

Queries:

- `modelFormContract`
- `modelFormContractPages`
- `modelFormInitialData`

The generated endpoints now enforce consistent exposure and authorization
behavior for both contracts and initial values.

### Authorization and exposure behavior

Generated form queries align with `GraphQLMeta` input exposure and permission
checks so contracts and initial payloads stay consistent.

- `modelFormInitialData` enforces `view` access for the target object and
  returns a GraphQL error when access is denied.
- Scalar field exposure now follows `GraphQLMeta.should_expose_field(...,
  for_input=True)` the same way relation exposure already does.
- Nested initial-data serialization uses the same exposure gate, so read-only
  and excluded input fields are not emitted accidentally.
- `modelFormContractPages` paginates model references before contract
  extraction, so page size controls extraction cost.

### Exclude models via settings

```python
RAIL_DJANGO_FORM = {
    "enable_cache": True,
    "cache_ttl_seconds": 3600,
    "initial_data_relation_limit": 200,
    "generated_form_excluded_models": [
        "store.Product",
        "store.Order",
    ],
    "generated_form_metadata_key": "generated_form",
}
```

Setting notes:

- `enable_cache`: enables generated form config cache reads and writes.
- `cache_ttl_seconds`: cache TTL used for generated form config payloads.
- `initial_data_relation_limit`: caps to-many relation items emitted by
  `modelFormInitialData` per relation (`0` disables the cap).
- `generated_form_excluded_models`: excludes models by default.
- `generated_form_metadata_key`: custom metadata key on
  `GraphQLMeta.custom_metadata`.

### Override per model via metadata

```python
class Product(models.Model):
    class GraphQLMeta(RailGraphQLMeta):
        custom_metadata = {
            "generated_form": {
                "enabled": False,  # explicit opt-out for this model
            }
        }
```

`custom_metadata.generated_form.enabled` is evaluated first and overrides the
settings exclusion list when present.

If you exclude a model globally but need one exception, set
`custom_metadata.generated_form.enabled = True` on that model.

### Exclude unsafe reverse relations from generated contracts

When a reverse relation points to a non-nullable FK (for example
`Product.orderItems` -> `OrderItem.product`), using relation actions like `set`
or `disconnect` can fail because the backend must temporarily null the FK.

If that relation should be managed elsewhere (for example through `Order`),
exclude it from Product input exposure:

```python
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta

class Product(models.Model):
    class GraphQLMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(
            read_only=["order_items"],  # or exclude=["order_items"]
        )
        relations = {
            "order_items": RailGraphQLMeta.FieldRelation(
                connect=RailGraphQLMeta.RelationOperation(enabled=False),
                create=RailGraphQLMeta.RelationOperation(enabled=False),
                update=RailGraphQLMeta.RelationOperation(enabled=False),
                disconnect=RailGraphQLMeta.RelationOperation(enabled=False),
                set=RailGraphQLMeta.RelationOperation(enabled=False),
            )
        }
```

Note: this exclusion is explicit (metadata-driven), not automatic. The generated
ModelForm contract mirrors what your `GraphQLMeta` exposes for mutation input.

Generated ModelForm contracts follow GraphQLMeta input exposure. After changing
GraphQLMeta, refresh/restart the backend so cached form configs are rebuilt.

### Generated contract query example

```graphql
query ProductContract {
  modelFormContract(appLabel: "store", modelName: "Product", mode: CREATE) {
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
    }
    sections {
      id
      fieldPaths
      visible
    }
    mutationBindings {
      createOperation
      updateOperation
      bulkCreateOperation
      bulkUpdateOperation
    }
    errorPolicy {
      canonicalFormErrorKey
      fieldPathNotation
      bulkRowPrefixPattern
    }
  }
}
```

### Initial data query with runtime overrides

```graphql
query ProductInitialData($id: ID!, $runtimeOverrides: [ModelFormRuntimeOverrideInput!]) {
  modelFormInitialData(
    appLabel: "store"
    modelName: "Product"
    objectId: $id
    includeNested: true
    runtimeOverrides: $runtimeOverrides
  ) {
    objectId
    values
    readonlyValues
    loadedAt
  }
}
```

If a model is excluded or disabled, the generated queries return:
`Generated form contract is not enabled for '<app>.<Model>'.`

After changing `RAIL_DJANGO_FORM`, restart your Django processes so cached form
settings are reloaded.

## Core Queries

### formConfig

Fetch the form configuration only (use for CREATE mode).

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
    }
    configVersion
  }
}
```

### formData

Fetch configuration and initial values in one request (required for UPDATE mode).

```graphql
query FormData($app: String!, $model: String!, $id: ID!) {
  formData(app: $app, model: $model, objectId: $id, mode: UPDATE) {
    config {
      app
      model
      configVersion
      fields {
        name
        label
        inputType
      }
    }
    initialValues
  }
}
```

### formConfigs

Bulk fetch multiple form configs (used for nested form relationships).

```graphql
query FormConfigs($models: [ModelRef!]!) {
  formConfigs(models: $models) {
    app
    model
    configVersion
  }
}
```

### formTypeDefinitions

Generate TypeScript type definitions from form configs.

```graphql
query FormTypes($models: [ModelRef!]!) {
  formTypeDefinitions(models: $models) {
    typescript
    generatedAt
    models
  }
}
```

## Relation Input Contract

Nested relationship updates follow a GraphQL-native contract:

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

### Relation Mutation Payload Example

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

## File Upload Strategy

`FieldConfig.uploadConfig` indicates the upload mode:

- `GRAPHQL_UPLOAD`: standard multipart GraphQL uploads.
- `DIRECT_UPLOAD`: pre-signed URL flow.

Example:

```graphql
uploadConfig {
  strategy
  maxFileSize
  allowedExtensions
  directUploadUrl
}
```

## Caching

Generated form configs include a stable `configVersion` hash for client cache
invalidation and an internal version token for server cache key rotation.

If you update model metadata or exposure rules and need immediate backend cache
rotation, call `invalidate_form_cache(app_label, model_name)` from
`rail_django.extensions.form.utils`.

## Error Contract

GraphQL errors should include standard extensions for reliable field mapping:

```json
{
  "extensions": {
    "code": "VALIDATION_ERROR",
    "fieldErrors": { "name": ["Required"] },
    "nonFieldErrors": ["Cannot submit form"]
  }
}
```

## Management Commands

Generate TypeScript types:

```bash
python manage.py generate_form_types --app store --model Product --out form-types.ts
```

Export form schema:

```bash
python manage.py export_form_schema --app store --model Product --out form-schema.json
```

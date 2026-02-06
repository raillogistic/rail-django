# Form API

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

Each form config includes a stable `configVersion` hash. Use it to invalidate client caches.

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

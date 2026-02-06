# Form API Reference

This reference covers the Form API GraphQL schema exposed by the `form` extension.

## Queries

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

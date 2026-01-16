# GraphQL Mutations

## Overview

Rail Django automatically generates CRUD mutations for each Django model. This guide covers auto-generated mutations, bulk operations, custom mutations, and nested relationships.

---

## Table of Contents

1. [Auto-Generated Mutations](#auto-generated-mutations)
2. [Create](#create)
3. [Update](#update)
4. [Delete](#delete)
5. [Bulk Operations](#bulk-operations)
6. [Nested Relationships](#nested-relationships)
7. [Method Mutations](#method-mutations)
8. [Configuration](#configuration)

---

## Auto-Generated Mutations

For each model, Rail Django generates:

| Mutation    | Format                | Description                   |
| ----------- | --------------------- | ----------------------------- |
| Create      | `create_<model>`      | Creates a new instance        |
| Update      | `update_<model>`      | Modifies an existing instance |
| Delete      | `delete_<model>`      | Deletes an instance           |
| Bulk Create | `bulk_create_<model>` | Creates multiple instances    |
| Bulk Update | `bulk_update_<model>` | Modifies multiple instances   |
| Bulk Delete | `bulk_delete_<model>` | Deletes multiple instances    |

**Example for the `Product` model:**

```graphql
type Mutation {
  create_product(input: ProductCreateInput!): ProductMutationPayload
  update_product(id: ID!, input: ProductUpdateInput!): ProductMutationPayload
  delete_product(id: ID!): DeletePayload
  bulk_create_product(inputs: [ProductCreateInput!]!): BulkProductPayload
  bulk_update_product(inputs: [ProductUpdateWithIdInput!]!): BulkProductPayload
  bulk_delete_product(ids: [ID!]!): BulkDeletePayload
}
```

---

## Create

### Basic Mutation

```graphql
mutation CreateProduct($input: ProductCreateInput!) {
  create_product(input: $input) {
    ok
    object {
      id
      name
      sku
      price
    }
    errors {
      field
      message
    }
  }
}
```

**Variables:**

```json
{
  "input": {
    "name": "New Product",
    "sku": "PRD-001",
    "price": "99.99",
    "category_id": "1",
    "is_active": true
  }
}
```

### Success Response

```json
{
  "data": {
    "create_product": {
      "ok": true,
      "object": {
        "id": "42",
        "name": "New Product",
        "sku": "PRD-001",
        "price": "99.99"
      },
      "errors": null
    }
  }
}
```

### Error Response (Validation)

```json
{
  "data": {
    "create_product": {
      "ok": false,
      "object": null,
      "errors": [
        {
          "field": "sku",
          "message": "A product with this SKU already exists."
        },
        {
          "field": "price",
          "message": "Price must be positive."
        }
      ]
    }
  }
}
```

---

## Update

### Basic Mutation

```graphql
mutation UpdateProduct($id: ID!, $input: ProductUpdateInput!) {
  update_product(id: $id, input: $input) {
    ok
    object {
      id
      name
      price
    }
    errors {
      field
      message
    }
  }
}
```

**Variables:**

```json
{
  "id": "42",
  "input": {
    "price": "89.99",
    "is_active": false
  }
}
```

### Partial Update

Only provided fields are modified:

```json
{
  "id": "42",
  "input": {
    "price": "79.99"
  }
}
```

### Read-Only Fields

Fields marked `read_only` in `GraphQLMeta` are ignored:

```python
class Product(models.Model):
    sku = models.CharField(max_length=50)

    class GraphQLMeta:
        fields = GraphQLMeta.Fields(
            read_only=["sku"],  # Not modifiable via update
        )
```

---

## Delete

### Basic Mutation

```graphql
mutation DeleteProduct($id: ID!) {
  delete_product(id: $id) {
    ok
    errors {
      message
    }
  }
}
```

**Variables:**

```json
{
  "id": "42"
}
```

### Success Response

```json
{
  "data": {
    "delete_product": {
      "ok": true,
      "errors": null
    }
  }
}
```

### Constraint Handling

If deletion fails (FK constraint):

```json
{
  "data": {
    "delete_product": {
      "ok": false,
      "errors": [
        {
          "message": "Cannot delete: this item is referenced by other records."
        }
      ]
    }
  }
}
```

---

## Bulk Operations

### Activation

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "generate_bulk": True,
        "enable_bulk_operations": True,
        "bulk_batch_size": 100,
    },
}
```

### Bulk Create

```graphql
mutation BulkCreateProducts($inputs: [ProductCreateInput!]!) {
  bulk_create_product(inputs: $inputs) {
    ok
    count
    objects {
      id
      name
    }
    errors {
      index
      field
      message
    }
  }
}
```

**Variables:**

```json
{
  "inputs": [
    {
      "name": "Product A",
      "sku": "A-001",
      "price": "10.00",
      "category_id": "1"
    },
    {
      "name": "Product B",
      "sku": "B-001",
      "price": "20.00",
      "category_id": "1"
    },
    {
      "name": "Product C",
      "sku": "C-001",
      "price": "30.00",
      "category_id": "2"
    }
  ]
}
```

### Bulk Update

```graphql
mutation BulkUpdateProducts($inputs: [ProductUpdateWithIdInput!]!) {
  bulk_update_product(inputs: $inputs) {
    ok
    count
    objects {
      id
      price
    }
  }
}
```

**Variables:**

```json
{
  "inputs": [
    { "id": "1", "price": "15.00" },
    { "id": "2", "price": "25.00" },
    { "id": "3", "is_active": false }
  ]
}
```

### Bulk Delete

```graphql
mutation BulkDeleteProducts($ids: [ID!]!) {
  bulk_delete_product(ids: $ids) {
    ok
    count
  }
}
```

**Variables:**

```json
{
  "ids": ["1", "2", "3"]
}
```

---

## Nested Relationships

### Activation

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "enable_nested_relations": True,
        "nested_relations_config": {},
    },
}
```

### Create with Relationship

Create the parent object and children in a single mutation:

```graphql
mutation CreateOrder($input: OrderCreateInput!) {
  create_order(input: $input) {
    ok
    object {
      id
      reference
      items {
        id
        product {
          name
        }
        quantity
      }
    }
  }
}
```

**Variables:**

```json
{
  "input": {
    "customer_id": "1",
    "items": [
      { "product_id": "10", "quantity": 2, "price": "99.99" },
      { "product_id": "15", "quantity": 1, "price": "49.99" }
    ]
  }
}
```

### Update with Relationship

```graphql
mutation UpdateOrder($id: ID!, $input: OrderUpdateInput!) {
  update_order(id: $id, input: $input) {
    ok
    object {
      id
      items {
        id
        quantity
      }
    }
  }
}
```

**Variables:**

```json
{
  "id": "42",
  "input": {
    "items": [
      { "id": "100", "quantity": 5 },
      { "product_id": "20", "quantity": 1, "price": "29.99" }
    ]
  }
}
```

Behavior:

- Element with `id`: update
- Element without `id`: creation
- Absent elements: deletion (if configured)

### Nested Relationship Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "nested_relations_config": {
            "store.Order": {
                "items": {
                    "create": True,
                    "update": True,
                    "delete": True,  # Delete absent ones
                    "max_items": 50,
                },
            },
        },
    },
}
```

---

## Method Mutations

Expose model methods as GraphQL mutations.

### Declaration

```python
from django.db import models

class Order(models.Model):
    status = models.CharField(max_length=20, default="draft")

    def confirm(self, confirmed_by=None):
        """
        Confirms the order.

        Args:
            confirmed_by: User who confirms.

        Returns:
            The updated instance.
        """
        self.status = "confirmed"
        self.confirmed_at = timezone.now()
        self.confirmed_by = confirmed_by
        self.save()
        return self

    def cancel(self, reason):
        """
        Cancels the order.

        Args:
            reason: Cancellation reason.
        """
        self.status = "cancelled"
        self.cancellation_reason = reason
        self.save()
        return self

    class GraphQLMeta:
        # Expose these methods as mutations
        method_mutations = ["confirm", "cancel"]
```

### Usage

```graphql
mutation ConfirmOrder($id: ID!) {
  confirm_order(id: $id) {
    ok
    object {
      id
      status
      confirmed_at
    }
  }
}

mutation CancelOrder($id: ID!, $reason: String!) {
  cancel_order(id: $id, reason: $reason) {
    ok
    object {
      id
      status
      cancellation_reason
    }
  }
}
```

### Method Configuration

```python
class Order(models.Model):
    class GraphQLMeta:
        method_mutations = {
            "confirm": {
                "permissions": ["store.confirm_order"],
                "description": "Confirms a pending order",
            },
            "cancel": {
                "permissions": ["store.cancel_order"],
                "required_args": ["reason"],
            },
        }
```

---

## Configuration

### Global Settings

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        # ─── Generation ───
        "generate_create": True,
        "generate_update": True,
        "generate_delete": True,
        "generate_bulk": False,

        # ─── Execution ───
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_bulk_operations": False,

        # ─── Methods ───
        "enable_method_mutations": True,

        # ─── Permissions ───
        "require_model_permissions": True,
        "model_permission_codenames": {
            "create": "add",
            "update": "change",
            "delete": "delete",
        },

        # ─── Bulk ───
        "bulk_batch_size": 100,

        # ─── Relationships ───
        "enable_nested_relations": True,
        "nested_relations_config": {},

        # ─── Required Fields ───
        "required_update_fields": {},
    },
}
```

### Disable by Model

```python
class ReadOnlyModel(models.Model):
    class GraphQLMeta:
        # Disable all mutations
        mutations = False

        # Or selectively
        # mutations = {
        #     "create": True,
        #     "update": False,
        #     "delete": False,
        # }
```

### Required Fields for Update

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "required_update_fields": {
            "store.Order": ["id"],  # Always required
        },
    },
}
```

---

## See Also

- [Queries](./queries.md) - Data reading
- [Configuration](./configuration.md) - All settings
- [Permissions](../security/permissions.md) - Mutation access control

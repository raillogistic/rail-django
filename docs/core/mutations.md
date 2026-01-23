# Mutations

Mutations in Rail Django automate the creation of Create, Update, and Delete (CUD) operations for your models.

## Standard Mutations

For a model `Product`, the following mutations are generated:

### 1. Create (`createProduct`)

```graphql
mutation {
  createProduct(input: { 
    sku: "NEW-SKU-001",
    name: "Wireless Mouse",
    price: 25.00,
    costPrice: 10.00,
    categoryId: "1",
    inventoryCount: 50
  }) {
    product { id, name }
    errors { field, messages }
  }
}
```

### 2. Update (`updateProduct`)

```graphql
mutation {
  updateProduct(id: "1", input: { price: 29.99 }) {
    product { price }
  }
}
```

### 3. Delete (`deleteProduct`)

```graphql
mutation {
  deleteProduct(id: "1") {
    success
    deletedId
  }
}
```

## Nested Relations (Unified Input)

Rail Django uses a "Unified Input" format for handling relationships (Foreign Keys, Many-to-Many, Reverse Relations). This provides a structured and explicit way to manage connections.

Each relation field accepts an object with operation keys: `connect`, `create`, `update`, `disconnect`, `set`.

### 1. One-to-Many / Foreign Key

```graphql
mutation {
  createPost(input: {
    title: "My Post",
    # Link to existing Category
    category: { connect: "1" } 
    # OR Create new Category
    # category: { create: { name: "New Category" } }
  }) { ... }
}
```

### 2. Many-to-Many / Reverse Relations

For list-based relations (like `tags` on `Post`), you can combine operations.

```graphql
mutation {
  updatePost(id: "1", input: {
    tags: {
      # Add existing tags
      connect: ["1", "2"],
      # Create and add new tags
      create: [{ name: "GraphQL" }],
      # Remove specific tags
      disconnect: ["3"]
    }
  }) { ... }
}
```

To replace the entire collection, use `set`:

```graphql
mutation {
  updatePost(id: "1", input: {
    tags: {
      # Replaces all existing tags with just these two
      set: ["1", "2"]
    }
  }) { ... }
}
```

## Bulk Operations

When enabled in `mutation_settings`, bulk operations are generated.

Configuration logic:
1. `enable_bulk_operations` (default: `True`) must be enabled as a master switch.
2. `generate_bulk` (default: `False`) controls "auto-discovery" (generating for all models).
3. Use `bulk_include_models` to strictly opt-in specific models (e.g., `["Product", "Order"]`).
4. Use `bulk_exclude_models` to opt-out specific models.

```graphql
mutation {
  # Update multiple products at once
  bulkUpdateProduct(inputs: [
    { id: "1", input: { inventoryCount: 100 } },
    { id: "2", input: { inventoryCount: 150 } }
  ]) {
    successCount
    errors { index, messages }
  }
}
```

## Mutation Pipeline

Customize the execution logic via `GraphQLMeta.Pipeline`.

```python
class Order(models.Model):
    class GraphQLMeta:
        pipeline_config = GraphQLMeta.Pipeline(
            # Add steps to run after saving
            extra_steps=[NotifyFulfillmentStep, LogStockChangeStep]
        )
```

## Custom Mutations

Define standard Graphene mutations for custom business logic.

```python
from rail_django.core.registry import register_mutation

class MarkOrderPaid(graphene.Mutation):
    class Arguments:
        order_id = graphene.ID(required=True)
    
    success = graphene.Boolean()

    def mutate(root, info, order_id):
        order = Order.objects.get(pk=order_id)
        order.status = OrderStatus.PAID
        order.save()
        return MarkOrderPaid(success=True)

register_mutation(MarkOrderPaid)
```
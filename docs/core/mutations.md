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

## Nested Relations

You can create or link related objects in a single mutation.

```graphql
mutation {
  createCustomer(input: {
    firstName: "John",
    lastName: "Doe",
    email: "john@example.com",
    # Create addresses along with the customer
    addresses: [
      { 
        label: "Home", 
        line1: "123 Main St", 
        city: "New York", 
        postalCode: "10001", 
        isPrimary: true 
      }
    ]
  }) {
    customer {
      firstName
      addresses { city }
    }
  }
}
```

## Bulk Operations

When enabled in `mutation_settings`, bulk operations are generated.

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
# Mutations

Rail Django automates the creation of Create, Update, and Delete (CUD) operations for your models, providing a robust and consistent API for data modification.

## Auto-Generated Mutations

For every model registered in the schema, Rail Django can generate a standard set of mutations:

| Mutation | Name Format | Description |
|----------|-------------|-------------|
| **Create** | `create<Model>` | Creates a new instance. |
| **Update** | `update<Model>` | Modifies an existing instance. |
| **Delete** | `delete<Model>` | Deletes an instance by ID. |
| **Bulk Create** | `bulkCreate<Model>` | Creates multiple instances at once. |
| **Bulk Update** | `bulkUpdate<Model>` | Modifies multiple instances in one request. |
| **Bulk Delete** | `bulkDelete<Model>` | Deletes multiple instances by ID. |

### Standard CRUD Example

Using an E-commerce scenario where we manage `Products`:

```graphql
mutation CreateProduct {
  createProduct(input: {
    name: "Wireless Gaming Mouse",
    sku: "WGM-001",
    price: 59.99,
    inventoryCount: 150,
    isActive: true
  }) {
    ok
    object {
      id
      name
      sku
    }
    errors {
      field
      message
    }
  }
}

mutation UpdateProduct($id: ID!) {
  updateProduct(id: $id, input: {
    price: 49.99,
    inventoryCount: 145
  }) {
    ok
    object {
      id
      price
    }
  }
}
```

## Nested Operations (Unified Input)

Rail Django uses a "Unified Input" format for managing relationships (Foreign Keys, Many-to-Many, etc.). This allows you to perform complex related-data operations, such as creating an Order and all its Items, in a single atomic request.

Each relation field accepts an object with the following operators:

- **`connect`**: Link to an existing object by ID (or list of IDs for Many-to-Many).
- **`create`**: Create a new related object and link it.
- **`update`**: Modify an existing related object (requires `id` inside the update block).
- **`disconnect`**: Remove the link to a related object.
- **`set`**: Replace the entire collection with a new set of IDs (for many-to-many).

### Example: One-to-Many (Order with Items)

In this example, we create an `Order` and simultaneously create several `OrderItems` and connect them to existing `Products`.

```graphql
mutation CreateOrderWithItems {
  createOrder(input: {
    customerEmail: "customer@example.com",
    shippingAddress: "123 Rail Way, Django City",
    items: {
      create: [
        {
          quantity: 2,
          product: { connect: "UHJvZHVjdDox" } # Connect to Product ID 1
        },
        {
          quantity: 1,
          product: { connect: "UHJvZHVjdDoy" } # Connect to Product ID 2
        }
      ]
    }
  }) {
    ok
    object {
      id
      totalAmount
      items {
        id
        product { name }
        quantity
      }
    }
  }
}
```

### Example: Many-to-Many (Product Tags)

Updating a product's tags using a mix of operators:

```graphql
mutation UpdateProductTags($productId: ID!) {
  updateProduct(id: $productId, input: {
    tags: {
      connect: ["VGFnOjE=", "VGFnOjI="],  # Add existing tags
      create: [{ name: "Limited Edition" }], # Create and add a new tag
      disconnect: ["VGFnOjU="]              # Remove a specific tag
    }
  }) {
    ok
    object {
      id
      tags { name }
    }
  }
}
```

## Bulk Operations

Bulk operations are optimized for high-throughput updates and creations, typically using Django's `bulk_create` and `bulk_update` under the hood.

### Bulk Create

```graphql
mutation BulkCreateProducts {
  bulkCreateProduct(inputs: [
    { name: "USB-C Cable", price: 15.00, sku: "CABLE-01" },
    { name: "HDMI Cable", price: 25.00, sku: "CABLE-02" }
  ]) {
    ok
    count
    objects {
      id
      name
    }
    errors {
      index
      message
    }
  }
}
```

### Bulk Update

Bulk updates require the `id` of the record and the `input` containing fields to change.

```graphql
mutation UpdateInventory {
  bulkUpdateProduct(inputs: [
    { id: "UHJvZHVjdDox", input: { inventoryCount: 10 } },
    { id: "UHJvZHVjdDoy", input: { inventoryCount: 5 } }
  ]) {
    ok
    count
    errors {
      index
      message
    }
  }
}
```

## Custom Mutations & Business Logic

While auto-generated mutations handle data persistence, business logic often belongs in custom mutations or model methods.

### Method Mutations

You can expose model methods directly as mutations. This is ideal for state transitions or simple actions.

```python
# models.py
class Order(models.Model):
    status = models.CharField(max_length=20, default="pending")

    def mark_as_shipped(self, tracking_number):
        self.status = "shipped"
        self.tracking_number = tracking_number
        self.save()
        # You can trigger emails or webhooks here
        return self

    class GraphQLMeta:
        method_mutations = ["mark_as_shipped"]
```

Called via GraphQL:
```graphql
mutation ShipOrder($id: ID!) {
  orderMarkAsShipped(id: $id, trackingNumber: "XYZ-123") {
    ok
    object {
      id
      status
    }
  }
}
```

### Custom Graphene Mutations

For complex operations that span multiple models or external services (like processing a payment), define a standard Graphene mutation and register it.

```python
import graphene
from rail_django.core.registry import register_mutation

class ProcessOrderPayment(graphene.Mutation):
    class Arguments:
        order_id = graphene.ID(required=True)
        payment_token = graphene.String(required=True)

    ok = graphene.Boolean()
    transaction_id = graphene.String()

    def mutate(self, info, order_id, payment_token):
        # 1. Fetch Order
        # 2. Call Payment Gateway (Stripe/PayPal)
        # 3. Update Order Status
        # 4. Return result
        return ProcessOrderPayment(ok=True, transaction_id="txn_456")

register_mutation(ProcessOrderPayment)
```

## Error Handling

Rail Django provides a standardized error format for mutations, making it easy for clients to display validation errors.

### Error Format

The `errors` field in a mutation response is a list of objects containing:
- `field`: The name of the field that caused the error (or `__all__` for non-field errors).
- `message`: A human-readable error message.
- `code`: (Optional) A machine-readable error code.

```json
{
  "data": {
    "createProduct": {
      "ok": false,
      "object": null,
      "errors": [
        {
          "field": "sku",
          "message": "Product with this SKU already exists.",
          "code": "unique"
        }
      ]
    }
  }
}
```

### Parsing Errors on the Client

A common pattern for React/Vue clients:

```javascript
const handleSubmit = async (values) => {
  const { data } = await createProduct({ variables: { input: values } });

  if (!data.createProduct.ok) {
    // Map errors to form fields
    const formErrors = {};
    data.createProduct.errors.forEach(err => {
      formErrors[err.field] = err.message;
    });
    setErrors(formErrors);
  } else {
    // Handle success
    navigate(`/products/${data.createProduct.object.id}`);
  }
};
```

## See Also

- [Queries Reference](./queries.md)
- [Filtering & Search](./filtering.md)
- [Permissions & RBAC](../security/permissions.md)
- [Validation & Guards](../security/validation.md)

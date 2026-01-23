# Mutations Deep Dive

This tutorial covers everything about creating, updating, and deleting data in Rail Django, including validation, error handling, and nested operations.

## Mutation Types

Rail Django generates these mutations for each model:

| Mutation | Example | Purpose |
|----------|---------|---------|
| Create | `createProduct` | Create new object |
| Update | `updateProduct` | Update existing object |
| Delete | `deleteProduct` | Delete object |
| Bulk Create | `bulkCreateProduct` | Create multiple objects |
| Bulk Update | `bulkUpdateProduct` | Update multiple objects |
| Bulk Delete | `bulkDeleteProduct` | Delete multiple objects |

---

## Create Mutation

### Basic Create

```graphql
mutation {
  createProduct(input: {
    name: "New Product"
    price: 99.99
    sku: "NP-001"
    status: "draft"
  }) {
    ok
    product {
      id
      name
      price
      sku
      status
      createdAt
    }
    errors {
      field
      message
      code
    }
  }
}
```

**Success Response:**
```json
{
  "data": {
    "createProduct": {
      "ok": true,
      "product": {
        "id": "123",
        "name": "New Product",
        "price": "99.99",
        "sku": "NP-001",
        "status": "draft",
        "createdAt": "2024-01-15T10:30:00Z"
      },
      "errors": []
    }
  }
}
```

**Error Response:**
```json
{
  "data": {
    "createProduct": {
      "ok": false,
      "product": null,
      "errors": [
        {
          "field": "sku",
          "message": "Product with this SKU already exists.",
          "code": "DUPLICATE"
        }
      ]
    }
  }
}
```

### With Relations

Create with related objects:

```graphql
mutation {
  createProduct(input: {
    name: "Laptop"
    price: 999.99
    sku: "LP-001"
    categoryId: "1"           # FK by ID
    tagIds: ["1", "2", "3"]   # M2M by IDs
  }) {
    ok
    product {
      id
      name
      category {
        id
        name
      }
      tags {
        id
        name
      }
    }
  }
}
```

---

## Update Mutation

### Basic Update

```graphql
mutation {
  updateProduct(id: "123", input: {
    price: 89.99
    status: "active"
  }) {
    ok
    product {
      id
      price
      status
      updatedAt
    }
    errors {
      field
      message
    }
  }
}
```

### Partial Updates

Only specified fields are updated:

```graphql
mutation {
  # Only updates price, everything else unchanged
  updateProduct(id: "123", input: {
    price: 79.99
  }) {
    ok
    product {
      id
      name      # Unchanged
      price     # Updated
      status    # Unchanged
    }
  }
}
```

### Update Relations

```graphql
mutation {
  updateProduct(id: "123", input: {
    categoryId: "5"           # Change category
    tagIds: ["10", "20"]      # Replace all tags
  }) {
    ok
    product {
      category {
        name
      }
      tags {
        name
      }
    }
  }
}
```

---

## Delete Mutation

### Basic Delete

```graphql
mutation {
  deleteProduct(id: "123") {
    ok
    errors {
      message
    }
  }
}
```

### Handling Protected Relations

If delete fails due to related objects:

```json
{
  "data": {
    "deleteProduct": {
      "ok": false,
      "errors": [
        {
          "field": null,
          "message": "Cannot delete product: It is referenced by 5 order items.",
          "code": "PROTECTED"
        }
      ]
    }
  }
}
```

---

## Bulk Mutations

### Bulk Create

Create multiple objects at once:

```graphql
mutation {
  bulkCreateProduct(inputs: [
    { name: "Product A", price: 10.00, sku: "PA-001" }
    { name: "Product B", price: 20.00, sku: "PB-001" }
    { name: "Product C", price: 30.00, sku: "PC-001" }
  ]) {
    ok
    created
    products {
      id
      name
      sku
    }
    errors {
      index
      field
      message
    }
  }
}
```

**Partial Success Response:**
```json
{
  "data": {
    "bulkCreateProduct": {
      "ok": false,
      "created": 2,
      "products": [
        { "id": "1", "name": "Product A", "sku": "PA-001" },
        { "id": "2", "name": "Product B", "sku": "PB-001" }
      ],
      "errors": [
        {
          "index": 2,
          "field": "sku",
          "message": "Product with this SKU already exists."
        }
      ]
    }
  }
}
```

### Bulk Update

```graphql
mutation {
  bulkUpdateProduct(inputs: [
    { id: "1", price: 15.00 }
    { id: "2", price: 25.00 }
    { id: "3", status: "archived" }
  ]) {
    ok
    updated
    products {
      id
      price
      status
    }
    errors {
      index
      message
    }
  }
}
```

### Bulk Delete

```graphql
mutation {
  bulkDeleteProduct(ids: ["10", "11", "12"]) {
    ok
    deleted
    errors {
      index
      message
    }
  }
}
```

---

## Nested Mutations

Create or modify related objects in a single mutation.

### Unified Input Syntax

Rail Django uses operation semantics for nested data:

```graphql
input OrderItemsInput {
  set: [ID]                    # Replace all with these IDs
  add: [ID]                    # Add to existing
  remove: [ID]                 # Remove specific IDs
  create: [CreateOrderItemInput]   # Create new objects
  update: [UpdateOrderItemInput]   # Update existing
  delete: [ID]                 # Delete by ID
}
```

### Create with Nested Objects

Create parent and children together:

```graphql
mutation {
  createOrder(input: {
    reference: "ORD-001"
    customerId: "1"
    items: {
      create: [
        { productId: "10", quantity: 2, unitPrice: 99.99 }
        { productId: "20", quantity: 1, unitPrice: 49.99 }
      ]
    }
  }) {
    ok
    order {
      id
      reference
      items {
        id
        product { name }
        quantity
        unitPrice
      }
      totalAmount
    }
  }
}
```

### Update with Nested Operations

Combine multiple operations:

```graphql
mutation {
  updateOrder(id: "1", input: {
    status: "confirmed"
    items: {
      # Add existing items
      add: ["existing-item-5"]

      # Update existing items
      update: [
        { id: "item-1", quantity: 5 }
        { id: "item-2", unitPrice: 79.99 }
      ]

      # Create new items
      create: [
        { productId: "30", quantity: 1, unitPrice: 149.99 }
      ]

      # Remove items (doesn't delete, just unlinks if applicable)
      remove: ["item-3"]

      # Delete items permanently
      delete: ["item-4"]
    }
  }) {
    ok
    order {
      id
      items {
        id
        quantity
        unitPrice
      }
    }
  }
}
```

### Replace All Related

Replace all children with new set:

```graphql
mutation {
  updateProduct(id: "1", input: {
    tags: {
      set: ["tag-1", "tag-2", "tag-3"]
    }
  }) {
    ok
    product {
      tags { id name }
    }
  }
}
```

### Deep Nesting

Create deeply nested structures:

```graphql
mutation {
  createOrder(input: {
    reference: "ORD-002"
    # Create customer inline
    customer: {
      create: {
        userId: "5"
        phone: "555-1234"
        address: "123 Main St"
      }
    }
    # Create items with product creation
    items: {
      create: [
        {
          quantity: 1
          unitPrice: 199.99
          # Create product inline
          product: {
            create: {
              name: "Custom Widget"
              sku: "CW-001"
              price: 199.99
            }
          }
        }
      ]
    }
  }) {
    ok
    order {
      customer {
        id
        phone
      }
      items {
        product {
          id
          name
        }
      }
    }
  }
}
```

---

## Error Handling

### Error Types

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Input validation failed |
| `NOT_FOUND` | Object doesn't exist |
| `PERMISSION_DENIED` | User lacks permission |
| `DUPLICATE` | Unique constraint violation |
| `REQUIRED` | Required field missing |
| `INTEGRITY_ERROR` | Database constraint |
| `PROTECTED` | Can't delete due to relations |

### Field-Level Errors

```json
{
  "errors": [
    {
      "field": "email",
      "message": "Enter a valid email address.",
      "code": "VALIDATION_ERROR"
    },
    {
      "field": "price",
      "message": "Ensure this value is greater than 0.",
      "code": "VALIDATION_ERROR"
    }
  ]
}
```

### Non-Field Errors

```json
{
  "errors": [
    {
      "field": null,
      "message": "You don't have permission to perform this action.",
      "code": "PERMISSION_DENIED"
    }
  ]
}
```

### Handling in Frontend

```typescript
interface MutationResult<T> {
  ok: boolean;
  data?: T;
  errors?: Array<{
    field: string | null;
    message: string;
    code: string;
  }>;
}

function handleMutationResult<T>(result: MutationResult<T>) {
  if (result.ok) {
    return { success: true, data: result.data };
  }

  // Group errors by field
  const fieldErrors: Record<string, string[]> = {};
  const generalErrors: string[] = [];

  for (const error of result.errors || []) {
    if (error.field) {
      fieldErrors[error.field] = fieldErrors[error.field] || [];
      fieldErrors[error.field].push(error.message);
    } else {
      generalErrors.push(error.message);
    }
  }

  return { success: false, fieldErrors, generalErrors };
}
```

---

## Input Validation

### Built-in Validation

Rail Django validates inputs automatically:

- Required fields
- Field types (string, number, etc.)
- Max length
- Unique constraints
- Foreign key existence
- Custom model validators

### Custom Validation in Model

```python
from django.core.exceptions import ValidationError

class Product(models.Model):
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)

    def clean(self):
        if self.price and self.cost_price:
            if self.price < self.cost_price:
                raise ValidationError({
                    'price': 'Price must be greater than cost price.'
                })

    def save(self, *args, **kwargs):
        self.full_clean()  # Run validation
        super().save(*args, **kwargs)
```

### Input Sanitization

XSS and SQL injection prevention is automatic:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_input_validation": True,
        "enable_xss_protection": True,
        "enable_sql_injection_protection": True
    }
}
```

---

## Method Mutations

Expose model methods as mutations:

### Define the Method

```python
class Order(models.Model):
    status = models.CharField(max_length=20)

    def confirm(self, send_notification=True):
        """Confirm this order and optionally notify customer."""
        if self.status != 'pending':
            raise ValidationError("Can only confirm pending orders")

        self.status = 'confirmed'
        self.save()

        if send_notification:
            self.send_confirmation_email()

        return self
```

### Call the Mutation

```graphql
mutation {
  orderConfirm(id: "123", sendNotification: true) {
    ok
    order {
      id
      status
    }
    errors {
      message
    }
  }
}
```

---

## Transaction Handling

Mutations are wrapped in database transactions:

```python
# Automatic rollback on error
# If any part fails, entire mutation is rolled back
```

### Explicit Transactions

For complex operations:

```python
from django.db import transaction

class Order(models.Model):
    def complete_order(self):
        with transaction.atomic():
            # All or nothing
            self.status = 'completed'
            self.save()

            for item in self.items.all():
                item.product.stock_quantity -= item.quantity
                item.product.save()

            self.create_invoice()
```

---

## Practical Examples

### User Registration

```graphql
mutation Register($input: RegisterInput!) {
  register(input: $input) {
    ok
    user {
      id
      username
      email
    }
    errors {
      field
      message
    }
  }
}

# Variables
{
  "input": {
    "username": "newuser",
    "email": "user@example.com",
    "password": "securepassword123",
    "firstName": "John",
    "lastName": "Doe"
  }
}
```

### Shopping Cart Checkout

```graphql
mutation Checkout(
  $customerId: ID!
  $items: [OrderItemCreateInput!]!
  $shippingAddress: String!
) {
  createOrder(input: {
    reference: "AUTO-GENERATED"
    customerId: $customerId
    status: "pending"
    shippingAddress: $shippingAddress
    items: {
      create: $items
    }
  }) {
    ok
    order {
      id
      reference
      totalAmount
      items {
        product { name }
        quantity
        lineTotal
      }
    }
    errors {
      field
      message
    }
  }
}
```

### Batch Price Update

```graphql
mutation UpdatePrices($updates: [ProductPriceUpdate!]!) {
  bulkUpdateProduct(inputs: $updates) {
    ok
    updated
    products {
      id
      name
      price
    }
    errors {
      index
      field
      message
    }
  }
}

# Variables
{
  "updates": [
    { "id": "1", "price": 99.99 },
    { "id": "2", "price": 149.99 },
    { "id": "3", "price": 199.99 }
  ]
}
```

### Archive Old Products

```graphql
mutation ArchiveProducts($ids: [ID!]!) {
  bulkUpdateProduct(inputs: $ids.map(id => ({
    id: id,
    status: "archived"
  }))) {
    ok
    updated
  }
}
```

---

## Configuration

### Enable/Disable Mutations

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "generate_create": True,
        "generate_update": True,
        "generate_delete": True,
        "generate_bulk": False,       # Disabled by default
        "enable_nested_relations": True
    }
}
```

### Per-Model Configuration

```python
class Product(models.Model):
    class GraphQLMeta:
        mutations = GraphQLMetaConfig.Mutations(
            enable_create=True,
            enable_update=True,
            enable_delete=False  # Disable delete for this model
        )
```

---

## Next Steps

- [Nested Mutations](./nested-mutations.md) - Complex nested operations
- [Permissions](./permissions.md) - Secure your mutations
- [Validation](./validation.md) - Custom validation rules

# Mutation Generator

> **Module Path:** `rail_django.generators.mutations.generator`

The MutationGenerator creates GraphQL mutations for Django models, including CRUD operations, bulk mutations, nested operations, and custom method-based mutations.

## Architecture Overview

```
                        MutationGenerator
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   CRUD Mutations        Bulk Mutations      Method Mutations
   create/update/delete  bulkCreate/etc      customAction
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ Pipeline System │
                     │  - Auth Step    │
                     │  - Validation   │
                     │  - Tenant       │
                     │  - Execution    │
                     │  - Audit        │
                     └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ NestedOperation │
                     │    Handler      │
                     └─────────────────┘
```

## Class Reference

### MutationGenerator

```python
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.types import TypeGenerator

type_gen = TypeGenerator(schema_name="default")
mutation_gen = MutationGenerator(type_gen, schema_name="default")

# Generate CRUD mutations
CreateProduct = mutation_gen.generate_create_mutation(Product)
UpdateProduct = mutation_gen.generate_update_mutation(Product)
DeleteProduct = mutation_gen.generate_delete_mutation(Product)

# Generate bulk mutations
BulkCreateProduct = mutation_gen.generate_bulk_create_mutation(Product)
BulkUpdateProduct = mutation_gen.generate_bulk_update_mutation(Product)
BulkDeleteProduct = mutation_gen.generate_bulk_delete_mutation(Product)

# Generate all mutations for a model
all_mutations = mutation_gen.generate_all_mutations(Product)
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type_generator` | `TypeGenerator` | Required | Type generator instance |
| `settings` | `MutationGeneratorSettings` | `None` | Mutation settings |
| `schema_name` | `str` | `"default"` | Schema identifier |

#### Key Properties

| Property | Type | Description |
|----------|------|-------------|
| `type_generator` | `TypeGenerator` | Associated type generator |
| `settings` | `MutationGeneratorSettings` | Mutation settings |
| `nested_handler` | `NestedOperationHandler` | Handles nested ops |
| `authentication_manager` | `AuthManager` | Auth checks |
| `authorization_manager` | `AuthzManager` | Permission checks |
| `input_validator` | `InputValidator` | Input validation |
| `error_handler` | `ErrorHandler` | Error formatting |

## CRUD Mutations

### Create Mutation

```python
CreateProduct = mutation_gen.generate_create_mutation(Product)
```

**Generated GraphQL:**
```graphql
type Mutation {
  createProduct(input: CreateProductInput!): CreateProductPayload
}

input CreateProductInput {
  name: String!
  price: Decimal!
  status: String
  categoryId: ID!
  tags: TagsInput  # Nested operations
}

type CreateProductPayload {
  ok: Boolean!
  product: Product
  errors: [MutationError]
}

type MutationError {
  field: String
  message: String!
  code: String
}
```

**Usage:**
```graphql
mutation {
  createProduct(input: {
    name: "New Product"
    price: 99.99
    categoryId: "1"
    status: "active"
  }) {
    ok
    product {
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

### Update Mutation

```python
UpdateProduct = mutation_gen.generate_update_mutation(Product)
```

**Generated GraphQL:**
```graphql
type Mutation {
  updateProduct(id: ID!, input: UpdateProductInput!): UpdateProductPayload
}

input UpdateProductInput {
  name: String
  price: Decimal
  status: String
  categoryId: ID
  tags: TagsInput  # Nested operations
}

type UpdateProductPayload {
  ok: Boolean!
  product: Product
  errors: [MutationError]
}
```

**Usage:**
```graphql
mutation {
  updateProduct(id: "123", input: {
    price: 89.99
    status: "sale"
  }) {
    ok
    product {
      id
      price
      status
    }
  }
}
```

### Delete Mutation

```python
DeleteProduct = mutation_gen.generate_delete_mutation(Product)
```

**Generated GraphQL:**
```graphql
type Mutation {
  deleteProduct(id: ID!): DeleteProductPayload
}

type DeleteProductPayload {
  ok: Boolean!
  errors: [MutationError]
}
```

**Usage:**
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

## Bulk Mutations

### Bulk Create

```python
BulkCreateProduct = mutation_gen.generate_bulk_create_mutation(Product)
```

**Generated GraphQL:**
```graphql
type Mutation {
  bulkCreateProduct(inputs: [CreateProductInput!]!): BulkCreateProductPayload
}

type BulkCreateProductPayload {
  ok: Boolean!
  products: [Product]
  created: Int!
  errors: [BulkMutationError]
}

type BulkMutationError {
  index: Int!
  field: String
  message: String!
}
```

**Usage:**
```graphql
mutation {
  bulkCreateProduct(inputs: [
    { name: "Product A", price: 10.00, categoryId: "1" }
    { name: "Product B", price: 20.00, categoryId: "1" }
    { name: "Product C", price: 30.00, categoryId: "2" }
  ]) {
    ok
    created
    products {
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

```python
BulkUpdateProduct = mutation_gen.generate_bulk_update_mutation(Product)
```

**Generated GraphQL:**
```graphql
type Mutation {
  bulkUpdateProduct(inputs: [BulkUpdateProductInput!]!): BulkUpdateProductPayload
}

input BulkUpdateProductInput {
  id: ID!
  name: String
  price: Decimal
  # ... other fields
}

type BulkUpdateProductPayload {
  ok: Boolean!
  products: [Product]
  updated: Int!
  errors: [BulkMutationError]
}
```

### Bulk Delete

```python
BulkDeleteProduct = mutation_gen.generate_bulk_delete_mutation(Product)
```

**Generated GraphQL:**
```graphql
type Mutation {
  bulkDeleteProduct(ids: [ID!]!): BulkDeleteProductPayload
}

type BulkDeleteProductPayload {
  ok: Boolean!
  deleted: Int!
  errors: [BulkMutationError]
}
```

## Nested Operations

### Unified Input Syntax

Rail Django uses a unified input syntax for nested operations:

```graphql
input OrderItemsInput {
  set: [ID]                    # Replace all with these IDs
  add: [ID]                    # Add these IDs to existing
  remove: [ID]                 # Remove these IDs
  create: [CreateOrderItemInput]  # Create new items
  update: [UpdateOrderItemInput]  # Update existing items
  delete: [ID]                 # Delete items by ID
}
```

**Usage Examples:**

```graphql
# Create order with new items
mutation {
  createOrder(input: {
    customerId: "1"
    items: {
      create: [
        { productId: "10", quantity: 2 }
        { productId: "20", quantity: 1 }
      ]
    }
  }) {
    ok
    order {
      id
      items { id productId quantity }
    }
  }
}

# Update order: add, update, and remove items
mutation {
  updateOrder(id: "1", input: {
    items: {
      add: ["existing-item-5"]
      update: [
        { id: "item-1", quantity: 5 }
      ]
      remove: ["item-2", "item-3"]
    }
  }) {
    ok
    order {
      items { id quantity }
    }
  }
}

# Replace all items
mutation {
  updateOrder(id: "1", input: {
    items: {
      set: ["item-10", "item-20", "item-30"]
    }
  }) {
    ok
  }
}
```

### Nested Configuration

Enable/disable nested relations:

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "enable_nested_relations": True,
        "nested_relations_config": {
            "Order": True,          # Enable for Order
            "Product": False        # Disable for Product
        },
        "nested_field_config": {
            "Order.items": True,
            "Order.payments": False
        }
    }
}
```

## Method Mutations

Expose model methods as mutations:

```python
class Order(models.Model):
    status = models.CharField(max_length=20)

    def confirm(self, notify_customer=True):
        """Confirm this order."""
        self.status = "confirmed"
        self.save()
        if notify_customer:
            self.send_confirmation_email()
        return self

    class GraphQLMeta:
        mutations = GraphQLMetaConfig.Mutations(
            methods=["confirm"]
        )
```

**Generated GraphQL:**
```graphql
type Mutation {
  confirmOrder(id: ID!, input: OrderConfirmInput): OrderConfirmPayload
}

type OrderConfirmPayload {
  ok: Boolean!
  result: Order
  errors: [MutationError]
}
```

**Usage:**
```graphql
mutation {
  confirmOrder(id: "123", input: { notifyCustomer: true }) {
    ok
    result {
      id
      status
    }
  }
}
```

### Method Detection

Methods are detected via introspection:

```python
from rail_django.generators.introspector import ModelIntrospector

introspector = ModelIntrospector.for_model(Order)
methods = introspector.get_model_methods()

for name, method_info in methods.items():
    if method_info.is_mutation:
        print(f"Mutation method: {name}")
        print(f"  Parameters: {method_info.parameters}")
        print(f"  Return type: {method_info.return_type}")
```

## Pipeline System

Mutations use a pipeline architecture for processing:

```
┌──────────────────────────────────────────────────────────┐
│                    Mutation Pipeline                      │
│                                                          │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │
│  │ AuthStep    │ → │ Validation  │ → │ Tenant      │   │
│  │             │   │ Step        │   │ Step        │   │
│  └─────────────┘   └─────────────┘   └─────────────┘   │
│         │                 │                 │           │
│         ▼                 ▼                 ▼           │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │
│  │ Lookup      │ → │ Execution   │ → │ Audit       │   │
│  │ Step        │   │ Step        │   │ Step        │   │
│  └─────────────┘   └─────────────┘   └─────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### Pipeline Steps

| Step | Description |
|------|-------------|
| `AuthenticationStep` | Verify user is authenticated |
| `PermissionsStep` | Check operation permissions |
| `SanitizationStep` | Sanitize input data |
| `TenantStep` | Apply tenant context |
| `LookupStep` | Find existing object (update/delete) |
| `ValidationStep` | Validate input data |
| `ExecutionStep` | Perform the mutation |
| `AuditStep` | Log the mutation |

### Custom Pipeline

```python
from rail_django.generators.pipeline import PipelineBuilder

builder = PipelineBuilder(settings)
builder.add_step(CustomAuthStep())
builder.add_step(CustomValidationStep())
builder.require_model_permissions(True)

pipeline = builder.build("create")
result = pipeline.execute(context)
```

## Error Handling

### MutationError Type

```graphql
type MutationError {
  field: String       # Field that caused error (null for non-field errors)
  message: String!    # Human-readable message
  code: String        # Machine-readable error code
}
```

### Error Generation

```python
from rail_django.generators.mutations.errors import (
    build_validation_errors,
    build_integrity_errors,
    build_mutation_error
)

# From Django ValidationError
errors = build_validation_errors(validation_error)

# From IntegrityError
errors = build_integrity_errors(integrity_error, model)

# Custom error
error = build_mutation_error("email", "Email already exists", "DUPLICATE")
```

### Common Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Input validation failed |
| `NOT_FOUND` | Object not found |
| `PERMISSION_DENIED` | User lacks permission |
| `INTEGRITY_ERROR` | Database constraint violation |
| `DUPLICATE` | Unique constraint violation |
| `REQUIRED` | Required field missing |

## Permission Enforcement

### Model Permissions

```python
# Settings
"mutation_settings": {
    "require_model_permissions": True,
    "model_permission_codenames": {
        "create": "add",
        "update": "change",
        "delete": "delete"
    }
}
```

Requires Django permissions:
- Create: `app.add_model`
- Update: `app.change_model`
- Delete: `app.delete_model`

### Operation Guards

Via GraphQLMeta:
```python
class Product(models.Model):
    class GraphQLMeta:
        access = GraphQLMetaConfig.Access(
            operations={
                "create": GraphQLMetaConfig.OperationAccess(
                    roles=["product_manager"],
                    guard="myapp.guards.can_create_product"
                )
            }
        )
```

## Tenant Scoping

Mutations automatically apply tenant context:

```python
# Create: Tenant ID is added to input
input_data = self._apply_tenant_input(input_data, info, model, operation="create")

# Update/Delete: Queryset is scoped to tenant
queryset = self._apply_tenant_scope(queryset, info, model, operation="update")
```

## Settings Reference

### MutationGeneratorSettings

```python
@dataclass
class MutationGeneratorSettings:
    # CRUD generation toggles
    generate_create: bool = True
    generate_update: bool = True
    generate_delete: bool = True
    generate_bulk: bool = False

    # CRUD execution toggles
    enable_create: bool = True
    enable_update: bool = True
    enable_delete: bool = True
    enable_bulk_operations: bool = True
    enable_method_mutations: bool = True

    # Permission settings
    require_model_permissions: bool = True
    model_permission_codenames: dict = field(default_factory=lambda: {
        "create": "add",
        "update": "change",
        "delete": "delete"
    })

    # Bulk settings
    bulk_batch_size: int = 100
    bulk_include_models: list[str] = field(default_factory=list)
    bulk_exclude_models: list[str] = field(default_factory=list)

    # Required fields for update
    required_update_fields: dict[str, list[str]] = field(default_factory=dict)

    # Nested relation settings
    enable_nested_relations: bool = True
    nested_relations_config: dict = field(default_factory=dict)
    nested_field_config: dict = field(default_factory=dict)
```

## Usage Examples

### Generate All Mutations

```python
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.types import TypeGenerator

type_gen = TypeGenerator()
mutation_gen = MutationGenerator(type_gen)

# Generate all mutations for a model
mutations = mutation_gen.generate_all_mutations(Product)

# mutations = {
#   "createProduct": CreateProductMutation.Field(),
#   "updateProduct": UpdateProductMutation.Field(),
#   "deleteProduct": DeleteProductMutation.Field(),
#   "bulkCreateProduct": BulkCreateProductMutation.Field(),
#   "bulkUpdateProduct": BulkUpdateProductMutation.Field(),
#   "bulkDeleteProduct": BulkDeleteProductMutation.Field(),
#   "confirmProduct": ProductConfirmMutation.Field(),  # Method mutation
# }

# Create Mutation class
Mutation = type("Mutation", (graphene.ObjectType,), mutations)
```

### Custom Method Mutation

```python
# Define custom input/output types
class DiscountInput(graphene.InputObjectType):
    percentage = graphene.Float(required=True)
    reason = graphene.String()

class DiscountResult(graphene.ObjectType):
    original_price = graphene.Decimal()
    new_price = graphene.Decimal()
    discount_applied = graphene.Float()

# Generate mutation with custom types
ApplyDiscount = mutation_gen.convert_method_to_mutation(
    model=Product,
    method_name="apply_discount",
    custom_input_type=DiscountInput,
    custom_output_type=DiscountResult
)
```

### Disable Specific Mutations

```python
# Via settings
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "enable_delete": False,  # Disable all deletes
        "bulk_exclude_models": ["Product"]  # No bulk for Product
    }
}

# Via GraphQLMeta
class Product(models.Model):
    class GraphQLMeta:
        mutations = GraphQLMetaConfig.Mutations(
            enable_delete=False
        )
```

## Related Modules

- [Schema Builder](../core/schema-builder.md) - Uses MutationGenerator
- [Type Generator](./type-generator.md) - Provides input types
- [Pipeline System](./pipeline.md) - Mutation execution flow
- [Nested Handler](./nested-handler.md) - Nested operation handling
- [Input Validation](../security/validation.md) - Input sanitization
- [RBAC System](../security/rbac.md) - Permission checks

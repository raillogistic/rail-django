# Mutations Reference

Rail Django automates Create, Update, and Delete (CUD) operations, bulk operations, and method mutations.

## Auto-Generated Mutations
For a model `Product`, the following mutations are typically generated:
- `createProduct(input: CreateProductInput!)`
- `updateProduct(id: ID!, input: UpdateProductInput!)`
- `deleteProduct(id: ID!)`
- `bulkCreateProduct(inputs: [CreateProductInput!]!)`
- `bulkUpdateProduct(inputs: [BulkUpdateProductInput!]!)`
- `bulkDeleteProduct(ids: [ID!]!)`

## Nested Operations (Unified Input)
Rail Django manages relationships (Foreign Keys, M2M, Reverse) using a "Unified Input" object format. This allows atomic, complex related-data operations.

Each relation field accepts an object with these operators:
- **`connect`**: Link to an existing object by ID (or list of IDs). Additive.
- **`create`**: Create a new related object and link it.
- **`update`**: Modify an existing related object (requires `id` inside).
- **`disconnect`**: Remove the link to a related object by ID. Subtractive.
- **`set`**: Replace the entire collection with a new set of IDs (for many-to-many/reverse relations). Existing links not in the list are removed.

### Example: Nested Mutations
```graphql
mutation CreateOrderWithItems {
  createOrder(input: {
    customerEmail: "customer@example.com",
    items: {
      create: [
        { quantity: 2, product: { connect: "1" } },
        { quantity: 1, product: { connect: "2" } }
      ]
    }
  }) {
    ok
    object { id }
  }
}

mutation UpdateProductTags {
  updateProduct(id: "1", input: {
    tags: {
      connect: ["1", "2"],
      create: [{ name: "Limited Edition" }],
      disconnect: ["5"]
    }
  }) { ok }
}
```

### Reverse FK Caution
For reverse one-to-many relations, `set` and `disconnect` clear existing links by setting the child FK to `null`. If the child FK is `null=False`, the mutation will fail.
**Best Practice**: Hide the reverse field from mutation input in `GraphQLMeta` if it cannot be safely nulled, and manage the relationship from the owning side.

```python
class Product(models.Model):
    class GraphQLMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(read_only=["order_items"])
        relations = {
            "order_items": RailGraphQLMeta.FieldRelation(
                connect=RailGraphQLMeta.RelationOperation(enabled=False),
                # ... disable others
            )
        }
```

## Method Mutations & Decorators (`rail_django.core.decorators`)
Expose model methods directly as mutations or fine-tune their behavior.

### `@mutation`
Marks a model method as a GraphQL mutation. Supports specific access controls.

```python
from rail_django.core.decorators import mutation

class Order(models.Model):
    status = models.CharField(max_length=20, default="pending")

    @mutation(
        description="Cancel the order",
        permissions=["store.change_order"], # Django permissions
        roles=["order_manager"],            # RBAC or Django group roles
        access_resolver=lambda user, instance, **kwargs: instance.status == "pending", # Custom callable
        match="all",                        # "all" or "any" for access checks
        button_title="Cancel Order"
    )
    def cancel(self, reason: str):
        self.status = "cancelled"
        self.cancellation_reason = reason
        self.save()
        return True
```
Called via GraphQL: `orderCancel(id: "42", reason: "Customer requested")`

### `@confirm_action`
Exposes a **confirmation-only** model method as a GraphQL mutation. Generates metadata for UIs to render a confirmation dialog.

```python
from rail_django.core.decorators import confirm_action

@confirm_action(
    title="Validate Order",
    message="Are you sure you want to validate?",
    confirm_label="Validate",
    severity="destructive",
    roles=["admin"]
)
def validate(self):
    self.status = "validated"
    self.save()
    return True
```

### `@action_form`
Exposes a **form-based** model method as a GraphQL mutation. Method signature drives generated input fields; UI hints are added.

```python
from rail_django.core.decorators import action_form
from datetime import date

@action_form(title="Schedule", submit_label="Plan")
def schedule(self, planned_start: date, planned_end: date | None = None):
    self.start = planned_start
    self.end = planned_end
    self.save()
    return True
```

### `@business_logic`
Marks a method as custom business logic to be exposed as a mutation.

```python
from rail_django.core.decorators import business_logic

@business_logic(category="approval", requires_permission="can_approve")
def approve(self):
    pass
```

### `@custom_mutation_name` and `@private_method`
- `@custom_mutation_name("myCustomName")`: Specify a custom name for the generated mutation.
- `@private_method`: Mark a method as private (should not be exposed as a mutation).

## Error Handling
The `errors` field in a mutation response returns objects containing `field` and `message` to easily map validation errors to UI forms.
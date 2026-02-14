# Mutations Deep Dive

This tutorial covers advanced mutation patterns, including bulk operations and nested relationships.

## Nested Mutations (Unified Input)

Rail Django lets you create and update related objects in a single request using the `connect`, `create`, and `set` operators.

### `connect`, `disconnect`, `set` behavior

- `connect` adds links.
- `disconnect` removes specific links.
- `set` replaces the whole linked collection.

For this mutation:

```graphql
mutation {
  updateProduct(
    id: "9"
    input: { orderItems: { set: ["5", "8", "17", "19", "29"] } }
  ) {
    ok
    errors { field message }
  }
}
```

`set` means Product `9` must end with exactly those `orderItems` IDs.
Any previous linked item not in that list is removed.

### Client-side defaults you can rely on

Generated clients can infer unified nested operators from direct form values:

- singular scalar -> `connect`
- update-mode to-many scalar list -> `set`
- singular `null` -> `clear`
- to-many object list -> `update` when `id`/`pk`/`objectId`/`object_id` is present, otherwise `create`

Blocked inferred or explicit actions should fail fast with relation-scoped validation errors.

### Creating with Relationships
Create a Post and its Tags at the same time:

```graphql
mutation {
  createPost(input: {
    title: "The Power of Rail Django",
    tags: {
      create: [{ name: "Python" }, { name: "GraphQL" }]
    }
  }) {
    ok
    object {
      title
      tags { name }
    }
  }
}
```

### Updating Relationships
Add new tags and remove old ones from an existing post:

```graphql
mutation {
  updatePost(id: "5", input: {
    tags: {
      connect: ["10", "11"], # IDs of existing tags
      disconnect: ["2"]      # ID of tag to remove
    }
  }) {
    ok
  }
}
```

### Reverse relation caveat

For reverse one-to-many relations, `set` and `disconnect` may attempt to set the
child FK to `null`. If that FK is non-nullable, mutation fails.

If a relation is operationally owned by another model (for example `OrderItem`
managed via `Order`, not via `Product`), hide that reverse field from Product
mutation input using GraphQLMeta `fields.read_only` (or `fields.exclude`) and
disable relation operations for that path.

```python
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta

class Product(models.Model):
    # ...
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

## Bulk Operations

Perform actions on multiple items in one go.

### Bulk Create
```graphql
mutation {
  bulkCreateProduct(inputs: [
    { name: "Product A", price: 10.00, sku: "A-01" },
    { name: "Product B", price: 20.00, sku: "B-01" }
  ]) {
    ok
    count
    errors { index, message }
  }
}
```

## Exposing Model Methods

You can call Django model methods as GraphQL mutations. This is great for encapsulated business logic.

```python
class Order(models.Model):
    # ...
    def cancel(self, reason):
        self.status = "cancelled"
        self.cancellation_reason = reason
        self.save()
        return self

    class GraphQLMeta:
        method_mutations = ["cancel"]
```

GraphQL call:
```graphql
mutation {
  orderCancel(id: "42", reason: "Customer requested") {
    ok
    object { status }
  }
}
```

## Custom Validation

Add custom logic to the mutation flow using `clean()` on your models or custom pipeline steps.

```python
class Product(models.Model):
    # ...
    def clean(self):
        if self.price < 0:
            raise ValidationError("Price cannot be negative.")
```

## Next Steps

- [Mutations Reference](../core/mutations.md)
- [Permissions Tutorial](./permissions.md)
- [Background Tasks](../extensions/tasks.md)

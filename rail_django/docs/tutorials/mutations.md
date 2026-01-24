# Mutations Deep Dive

This tutorial covers advanced mutation patterns, including bulk operations and nested relationships.

## Nested Mutations (Unified Input)

Rail Django allows you to create and update related objects in a single request using the `connect`, `create`, and `set` operators.

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

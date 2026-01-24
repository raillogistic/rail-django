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

### Example Usage

```graphql
mutation CreateNewProduct {
  createProduct(input: {
    name: "Mechanical Keyboard",
    sku: "KB-900",
    price: 120.00,
    categoryId: "5"
  }) {
    ok
    object { id, name }
    errors { field, message }
  }
}
```

## Nested Relations (Unified Input)

Rail Django uses a "Unified Input" format for managing relationships (Foreign Keys, Many-to-Many, etc.). This allows you to perform complex related-data operations in a single request.

Each relation field accepts an object with the following operators:

- **`connect`**: Link to an existing object by ID.
- **`create`**: Create a new related object and link it.
- **`update`**: Modify an existing related object.
- **`disconnect`**: Remove the link to a related object.
- **`set`**: Replace the entire collection with a new set of IDs (for many-to-many).

### Example: One-to-Many (Foreign Key)
```graphql
mutation {
  createPost(input: {
    title: "Learning GraphQL",
    category: { connect: "10" } # Link to category ID 10
  }) { ... }
}
```

### Example: Many-to-Many
```graphql
mutation {
  updatePost(id: "1", input: {
    tags: {
      connect: ["1", "2"], # Add existing tags
      create: [{ name: "NewTag" }], # Create and add new tag
      disconnect: ["5"] # Remove tag ID 5
    }
  }) { ... }
}
```

## Bulk Operations

Bulk operations allow you to perform multiple CUD actions efficiently.

```graphql
mutation {
  bulkUpdateProduct(inputs: [
    { id: "1", input: { inventoryCount: 50 } },
    { id: "2", input: { inventoryCount: 100 } }
  ]) {
    ok
    count # Number of successfully updated items
    errors { index, message }
  }
}
```

Enable bulk operations in your settings:
```python
"mutation_settings": {
    "enable_bulk_operations": True,
    "bulk_batch_size": 100,
}
```

## Method Mutations

You can expose existing model methods as GraphQL mutations using `GraphQLMeta`.

```python
class Order(models.Model):
    # ...
    def mark_as_shipped(self, tracking_number):
        self.status = "shipped"
        self.tracking_number = tracking_number
        self.save()
        return self

    class GraphQLMeta:
        method_mutations = ["mark_as_shipped"]
```

## Custom Mutations

For complex business logic that doesn't map directly to a model, you can define custom Graphene mutations and register them:

```python
import graphene
from rail_django.core.registry import register_mutation

class ProcessPayment(graphene.Mutation):
    # ... definition ...

register_mutation(ProcessPayment)
```

## Pipeline & Hooks

Customize mutation execution using the pipeline system in `GraphQLMeta`. You can add custom validation steps or post-save triggers.

```python
class Product(models.Model):
    class GraphQLMeta:
        pipeline_config = {
            "extra_steps": [MyCustomValidationStep],
        }
```

## See Also

- [Queries Reference](./queries.md)
- [Filtering & Search](./filtering.md)
- [Permissions & RBAC](../security/permissions.md)

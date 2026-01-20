# Tutorial 4: Mutations & Pipelines

While queries fetch data, **mutations** modify it. Rail Django automates the creation of robust CRUD (Create, Read, Update, Delete) mutations and allows deep customization via its Pipeline architecture.

## 1. Auto-Generated Mutations

For every model with `GraphQLMeta`, the following mutations are generated (unless disabled):

*   `create_<model_name>`
*   `update_<model_name>`
*   `delete_<model_name>`

### Create

```graphql
mutation {
  create_product(input: {
    name: "Widget",
    price: 19.99,
    category: 1  # ID of the relation
  }) {
    object { id name }
    errors { field message }
  }
}
```

### Update

Updates require the `id` of the object to modify. Partial updates are supported (send only changed fields).

```graphql
mutation {
  update_product(id: 1, input: {
    price: 24.99
  }) {
    object { price }
  }
}
```

### Delete

```graphql
mutation {
  delete_product(id: 1) {
    ok
  }
}
```

### Disabling Mutations

You can disable specific operations in `GraphQLMeta`.

```python
class Product(models.Model):
    # ...
    class GraphQLMeta(GraphQLMetaConfig):
        # Only allow creating, not updating or deleting
        mutations = GraphQLMetaConfig.Mutations(
            create=True,
            update=False,
            delete=False
        )
```

## 2. Nested Mutations

Rail Django supports writing to related models in a single operation.

### Nested Create

Create a user and their profile simultaneously.

```graphql
mutation {
  create_user(input: {
    username: "jdoe",
    profile: {
      create: { bio: "Hello World" }
    }
  }) {
    object { id }
  }
}
```

### Nested Update / Connect

Update a book and change its author to an existing one (`connect`).

```graphql
mutation {
  update_book(id: 1, input: {
    title: "New Title",
    author: {
      connect: 5  # Connects to Author with ID 5
    }
  }) {
    object { id }
  }
}
```

## 3. Bulk Operations

Enable bulk operations to create, update, or delete multiple records at once.

**Settings:**
```python
"mutation_settings": {
    "enable_bulk_operations": True,
}
```

**Usage:**

```graphql
mutation {
  bulk_create_product(inputs: [
    { name: "A", price: 10 },
    { name: "B", price: 20 }
  ]) {
    objects { id }
  }
}
```

## 4. Mutation Pipelines (Advanced)

Rail Django uses a **Pipeline** pattern for mutations. This breaks down the mutation logic (Validation -> Permission -> Execution -> Audit) into discrete steps. You can inject your own logic.

### Creating a Custom Step

Let's add a step to send an email after a user is created.

```python
from rail_django.generators.pipeline.base import MutationStep

class SendWelcomeEmailStep(MutationStep):
    name = "send_welcome_email"
    order = 85  # Runs after execution (80)

    def should_run(self, ctx):
        # Only for User creation
        return ctx.model_name == "User" and ctx.operation == "create"

    def execute(self, ctx):
        user = ctx.result # The created object
        # send_email(user.email, ...)
        return ctx
```

### Registering the Pipeline

Register it in your model's `GraphQLMeta`.

```python
class User(models.Model):
    # ...
    class GraphQLMeta(GraphQLMetaConfig):
        pipeline = GraphQLMetaConfig.Pipeline(
            create_steps=[SendWelcomeEmailStep]
        )
```

## Next Steps

Mutations are powerful, but they need protection. Learn how to secure your API in [Tutorial 5: Security & Permissions](./05_security_and_permissions.md).

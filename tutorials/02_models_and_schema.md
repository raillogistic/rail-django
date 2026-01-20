# Tutorial 2: Models & Schema

In this tutorial, you will learn how to customize how your Django models are exposed in the GraphQL schema using the `GraphQLMeta` configuration class.

## The `GraphQLMeta` Class

The core of Rail Django is the `GraphQLMeta` inner class. It acts as the bridge between your Django models and the GraphQL schema.

```python
from rail_django.models import GraphQLMetaConfig

class MyModel(models.Model):
    # ... fields ...

    class GraphQLMeta(GraphQLMetaConfig):
        # Configuration goes here
        pass
```

## 1. Controlling Field Visibility

By default, Rail Django exposes all non-sensitive fields. You can control this explicitly.

### Including & Excluding Fields

```python
class Employee(models.Model):
    name = models.CharField(max_length=100)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    ssn = models.CharField(max_length=11)
    
    class GraphQLMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            # Only these fields will be in the API
            include=["id", "name", "salary"], 
            # OR use exclude to hide specific fields
            # exclude=["ssn"], 
        )
```

### Read-Only and Write-Only Fields

*   **Read-Only**: Visible in queries but cannot be set via mutations (e.g., status flags controlled by logic).
*   **Write-Only**: Can be set via mutations but not queried (e.g., passwords, secret tokens).

```python
class Project(models.Model):
    name = models.CharField(max_length=100)
    api_key = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default="draft")

    class GraphQLMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            read_only=["status"], 
            write_only=["api_key"]
        )
```

## 2. Relationships

Rail Django automatically handles Foreign Keys and Many-to-Many relationships.

### Forward Relations (ForeignKey)

If a `Book` has a `Publisher`, the `publisher` field is automatically available in the `Book` type.

```graphql
query {
  books {
    title
    publisher {  # Auto-generated relation field
      name
    }
  }
}
```

### Reverse Relations

Reverse relationships (e.g., accessing `books` from a `Publisher`) are also generated automatically.

```graphql
query {
  publishers {
    name
    books {      # Auto-generated reverse relation
      title
    }
  }
}
```

### Nested Creates/Updates

You can create related objects in a single mutation!

```graphql
mutation {
  createBook(input: {
    title: "New Novel",
    # Create the publisher inline
    publisher: {
      create: { name: "New Age Books" }
    }
  }) {
    object { id }
  }
}
```

To disable this feature, check `mutation_settings.enable_nested_relations` in your settings.

## 3. Renaming Fields

You may want to expose a field with a different name in the API.

**(Note: This feature is handled via custom resolvers or property fields, not directly in `GraphQLMeta` mapping currently. For simple renaming, Python properties are recommended.)**

```python
class User(models.Model):
    first_name = models.CharField(max_length=50)

    @property
    def display_name(self):
        return self.first_name

    class GraphQLMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(include=["display_name"])
```

## 4. Multi-Tenancy

If your application serves multiple tenants (e.g., Organizations) and data must be strictly scoped, use `tenant_field`.

```python
class Order(models.Model):
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE)
    amount = models.DecimalField(...)

    class GraphQLMeta(GraphQLMetaConfig):
        # Automatically filters queries to the current tenant
        # Automatically validates mutations belong to the tenant
        tenant_field = "organization"
```

Requires `multitenancy_settings` to be configured in `RAIL_DJANGO_GRAPHQL`.

## Next Steps

Now that you've defined your schema, learn how to query it effectively in [Tutorial 3: Queries & Filtering](./03_queries_and_filtering.md).

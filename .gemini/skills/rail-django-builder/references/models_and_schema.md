# Models and Schema Reference

Rail Django uses a "Model-First" approach. You define standard Django models, and the framework automatically generates the corresponding GraphQL schema (Types, Queries, and Mutations) using the `TypeGenerator`.

## Automatic Enhancements

The generator adds helper fields based on model definitions:
1. **Display Labels**: For fields with `choices`, it adds a `*Desc` field (e.g., `statusDesc` for `status`).
2. **Counts**: For `ManyToMany` and reverse relationships, it adds a `*Count` field (e.g., `ordersCount`).
3. **Polymorphism**: Adds `polymorphicType` for inherited models.
4. **Custom Output Fields**: Decorated model methods can expose explicit GraphQL fields.

**Naming Convention**: Rail Django converts all python `snake_case` field names to **`camelCase`** in the GraphQL schema by default.

## `GraphQLMeta` Configuration

Customize how a model is exposed by defining a `GraphQLMeta` class within the model.

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta

class Product(models.Model):
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    internal_notes = models.TextField(blank=True)

    class GraphQLMeta(RailGraphQLMeta):
        # 1. Field Exposure
        fields = RailGraphQLMeta.Fields(
            include=["sku", "name", "price"],
            read_only=["sku"],
            exclude=["internal_notes"]
        )

        # 2. Filtering
        filtering = RailGraphQLMeta.Filtering(
            quick=["sku", "name"],
            fields={"price": ["gt", "lt", "between"]}
        )

        # 3. Ordering
        ordering = RailGraphQLMeta.Ordering(
            allowed=["name", "price"],
            default=["name"]
        )
```

## Custom Output Fields (`@field`)

Use the `@field` decorator from `rail_django.core.decorators` to define custom computed fields on your model with explicit Graphene types.

```python
import graphene
from rail_django.core.decorators import field

class Employee(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    @field(type=graphene.String, title="Summary")
    def summary(self) -> str:
        return f"{self.first_name} {self.last_name}"

    class GraphQLMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(include=["first_name", "last_name", "summary"])
```

## Relationships & N+1 Prevention

Rail Django automatically handles relationships (`ForeignKey`, `ManyToManyField`):
- **Forward Relations**: Nested types (`product.category`).
- **Reverse Relations**: List fields (`category.products`).

The framework analyzes the GraphQL selection set and automatically applies `select_related` and `prefetch_related` to the Django QuerySet to solve N+1 query problems out of the box.

## Enums
Django `TextChoices` and `IntegerChoices` are automatically converted to GraphQL Enums.

## Registering Schemas (`@register_schema`)
You can use the `@register_schema` decorator from `rail_django.core.decorators` to register GraphQL schemas with the central schema registry. It can be applied to schema classes or schema factory functions.

```python
import graphene
from rail_django.core.decorators import register_schema

@register_schema(
    name="blog_schema",
    description="Blog management GraphQL schema",
    version="2.0.0",
    apps=["blog", "comments"],
    settings={"enable_graphiql": True, "authentication_required": False}
)
class BlogSchema(graphene.Schema):
    query = BlogQuery
    mutation = BlogMutation
```

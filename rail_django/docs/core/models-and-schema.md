# Models & Schema

Rail Django uses a "Model-First" approach. You define your standard Django models, and the framework automatically generates the corresponding GraphQL schema (Types, Queries, and Mutations).

## The Type Generator

At the heart of this process is the `TypeGenerator`. It inspects your Django models and constructs Graphene types with intelligent defaults.

### Automatic Enhancements

The generator adds helper fields automatically based on your model definitions:

1.  **Display Labels**: For fields with `choices`, it adds a `*Desc` field.
    *   Model: `status = models.CharField(choices=OrderStatus.choices)`
    *   GraphQL: `status` (value, for example, "PAID"), `statusDesc` (label, for example, "Paid").
2.  **Counts**: For `ManyToMany` and reverse relationships, it adds a `*Count` field.
    *   Model: `Customer` has `orders`.
    *   GraphQL: `orders` (list), `ordersCount` (int).
3.  **Polymorphism**: For inherited models, it adds `polymorphicType` to indicate the concrete class name.
4.  **Properties**: Python `@property` methods on models can be exposed if included in `GraphQLMeta`.

### Naming Conventions

By default, Rail Django converts all field names to **camelCase** to match GraphQL conventions.

- Python: `first_name`
- GraphQL: `firstName`

## Customizing Types with `GraphQLMeta`

To customize how a model is exposed, define a `GraphQLMeta` class within your model.

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta

class Product(models.Model):
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    inventory_count = models.PositiveIntegerField(default=0)
    internal_notes = models.TextField(blank=True)

    @property
    def order_items_count(self) -> int:
        return self.order_items.count()

    class GraphQLMeta:
        # Expose specific fields + the property
        fields = GraphQLMeta.Fields(
            include=["sku", "name", "price", "inventory_count", "order_items_count"],
            read_only=["order_items_count"],
            exclude=["internal_notes"]
        )
```

## Relationships

Rail Django automatically handles relationships (`ForeignKey`, `ManyToManyField`).

- **Forward Relations**: Exposed as nested types (for example, `product.category`).
- **Reverse Relations**: Exposed as list fields (for example, `category.products`).

### Filtering on Relations

Nested lists support an embedded `filters` (or `where`) argument.

```graphql
query {
  customer(id: "1") {
    # Fetch only paid orders for this customer
    orders(where: { status: { exact: "paid" } }) {
      orderNumber
      totalAmount
    }
    ordersCount
  }
}
```

### Optimization (N+1 Problem)

The framework automatically detects accessed fields in the GraphQL query and applies `select_related` and `prefetch_related`. For example, querying `order { customer { firstName } }` will automatically trigger a `select_related('customer')`.

## Enums

Django `TextChoices` and `IntegerChoices` are automatically converted to GraphQL Enums.

```python
class OrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PLACED = "placed", "Placed"
    PAID = "paid", "Paid"

class Order(models.Model):
    status = models.CharField(choices=OrderStatus.choices, ...)
```

Resulting GraphQL Enum: `Order_status_Enum`.

```graphql
query {
  orderList {
    status      # Returns "PAID"
    statusDesc  # Returns "Paid"
  }
}
```

## Historical Models

If you use `django-simple-history`, Rail Django automatically detects it and adds:
- `instanceId`: ID of the original object.
- `historyChanges`: JSON object detailing what changed in that revision.

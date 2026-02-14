# Filtering

Rail Django provides a powerful, type-safe filtering system inspired by Prisma. It uses a structured `where` argument to handle complex logic, nested relationships, and advanced database features.

## The `where` Argument

All list queries accept a `where` argument (typed as `<Model>WhereInput`).

```graphql
query {
  productList(where: { price: { lte: 50 } }) {
    name
    price
  }
}
```

## Basic Field Filters

Each field type has specific operators.

### String Filters
- `exact`, `icontains` (case-insensitive contains), `istartswith`, `in`, `isNull`.

```graphql
where: {
  sku: { istartswith: "PROD-" },
  name: { icontains: "phone" }
}
```

### Number Filters
- `exact`, `gt`, `gte`, `lt`, `lte`, `in`, `range`.

```graphql
where: {
  inventoryCount: { lt: 5 },
  price: { range: [10, 100] }
}
```

### Boolean Filters
- `exact`, `isNull`.

```graphql
where: {
  isActive: { exact: true }
}
```

## Logical Operators

Combine conditions using `AND`, `OR`, and `NOT`.

```graphql
where: {
  OR: [
    { inventoryCount: { lt: 5 } },
    { isActive: { exact: false } }
  ]
}
```

## Relationship Filters

### To-One Relations (ForeignKey)
Filter by parent fields using the `_rel` suffix for nested input.

```graphql
# Products where Category slug is 'electronics'
where: {
  category_rel: {
    slug: { exact: "electronics" }
  }
}
```

### To-Many Relations (Reverse/ManyToMany)
- `_some`: At least one related record matches.
- `_every`: All related records match.
- `_none`: No related records match.
- `_count`: Filter by the number of related records.

```graphql
# Customers who have at least one 'paid' order
where: {
  orders_some: {
    status: { exact: "paid" }
  }
}

# Products with more than 3 tags
where: {
  tags_count: { gt: 3 }
}
```

## Quick Search (`quick`)

The `quick` argument performs a search across fields defined in `GraphQLMeta.filtering.quick`.

```python
class Product(models.Model):
    class GraphQLMeta:
        filtering = GraphQLMeta.Filtering(
            quick=["sku", "name", "description"]
        )
```

```graphql
query {
  # Searches SKU, Name, and Description for "premium"
  productList(quick: "premium") {
    name
  }
}
```

## Computed Filters

You can define complex filters using Django expressions in `GraphQLMeta`.

```python
class Product(models.Model):
    class GraphQLMeta:
        computed_filters = {
            "profit_margin": {
                "expression": ExpressionWrapper(
                    F("price") - F("cost_price"),
                    output_field=FloatField()
                ),
                "filter_type": "float",
            }
        }
```

```graphql
query {
  # Find products with a profit margin > 20
  productList(where: { profit_margin: { gt: 20 } }) {
    name
  }
}
```

## Presets & Saved Filters

### Presets
Pre-defined filter sets in `GraphQLMeta`.

```python
class Product(models.Model):
    class GraphQLMeta:
        filtering = GraphQLMeta.Filtering(
            presets={
                "low_stock": {"inventory_count": {"lt": 10}}
            }
        )
```

```graphql
query {
  productList(presets: ["low_stock"]) {
    name
    inventoryCount
  }
}
```

### Saved Filters
User-defined filters stored in the database.

```graphql
query {
  # Apply a filter saved by the user
  orderList(savedFilter: "high-value-pending") {
    orderNumber
  }
}
```

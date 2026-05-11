# Queries and Filtering Reference

Rail Django automatically generates high-performance GraphQL queries for registered models.

## Auto-Generated Queries
For a model `Product`:
- **Single Object**: `product(id: ID!)`
- **List**: `productList(limit: Int, offset: Int, where: ProductWhereInput, orderBy: [String!])`
- **Paginated**: `productPage(page: Int, perPage: Int, where: ProductWhereInput)` - Includes `pageInfo` metadata.
- **Grouped**: `productGroup(groupBy: String!)` - Aggregated data counts.

If custom managers are exposed, they receive suffixes (e.g., `productListByPublished`).

## Filtering (The `where` Argument)
Rail Django uses a Prisma-inspired nested filtering syntax.

### Basic & Relational Filters
```graphql
query {
  productList(where: {
    isActive: { exact: true },
    price: { gte: 50.00 },
    # Traverse relationships naturally
    category: { slug: { exact: "electronics" } }
  }) {
    name
  }
}
```

### To-Many Relations
- `_some`: At least one matches.
- `_every`: All match.
- `_none`: None match.
- `_count`: Filter by count of related items.

```graphql
where: {
  orders_some: { status: { exact: "paid" } }
}
```

### Logic Operators
Combine using `AND`, `OR`, `NOT` arrays.

```graphql
where: {
  OR: [
    { price: { lt: 10.00 } },
    { isActive: { exact: false } }
  ]
}
```

### Quick Search (`quick`)
Performs a search across fields defined in `GraphQLMeta.filtering.quick`.

```graphql
productList(quick: "premium") { ... }
```

## Custom & Computed Filters
Defined in `GraphQLMeta` or via the `@filter` decorator on model methods.

```python
from django.db.models import F, FloatField, ExpressionWrapper
from rail_django.core.decorators import filter

class Product(models.Model):
    # Method-based custom filter
    @filter(name="is_active_product")
    def filter_active(queryset, value):
        return queryset.filter(active=bool(value))

    class GraphQLMeta:
        computed_filters = {
            "profit_margin": {
                "expression": ExpressionWrapper(F("price") - F("cost_price"), output_field=FloatField()),
                "filter_type": "float",
            }
        }
```

## Ordering
Use the `orderBy` argument (array of strings). Prefix with `-` for descending.
```graphql
productList(orderBy: ["-price", "name"]) { ... }
```

## Pagination
1. **Offset Pagination**: Best for simple internal tools (`limit`, `offset`).
2. **Page-Based**: Best for traditional UI (`productPage(page: 1, perPage: 10)`).
3. **Cursor-Based (Relay)**: Supported if `use_relay=True` in settings.

## Grouping
Server-side grouping via `...Group` queries.
```graphql
orderGroup(groupBy: "status") {
  key
  label
  count
}
```
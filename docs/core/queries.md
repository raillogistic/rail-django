# Queries

Rail Django automatically generates high-performance GraphQL queries for your Django models, including advanced filtering, pagination, and sorting capabilities.

## Auto-Generated Queries

For every model registered in your schema, Rail Django generates a set of root queries:

| Query Name | Format | Description |
|------------|--------|-------------|
| **Single Object** | `<model>` | Fetch a single instance by ID (or other lookup fields). |
| **List** | `<model>s` | Fetch a list of instances with filtering, sorting, and pagination. |
| **Paginated** | `<model>sPages` | Fetch a list with detailed page metadata (total count, page count). |
| **Grouped** | `<model>sGroups` | Aggregated data (e.g., counts grouped by a specific field). |

### Example: Basic List Query
```graphql
query ListAllProducts {
  products {
    id
    name
    price
    sku
  }
}
```

## Advanced Filtering

Rail Django features a powerful nested filter syntax (inspired by Prisma and Hasura) that is completely type-safe.

### Basic Filters
Use the `where` argument to apply filters to fields:

```graphql
query FilteredProducts {
  products(where: {
    isActive: { eq: true },
    price: { gte: 50.00 },
    name: { icontains: "premium" }
  }) {
    name
    price
  }
}
```

### Relationship Filtering
You can filter by related objects as deep as needed:

```graphql
query ProductsByCategory {
  products(where: {
    category: { slug: { eq: "electronics" } },
    supplier: { country: { in: ["US", "CA"] } }
  }) {
    name
  }
}
```

### Logic Operators (AND, OR, NOT)
Combine filters with boolean logic:

```graphql
query ComplexFilter {
  products(where: {
    OR: [
      { price: { lt: 10 } },
      { category: { isPromoted: { eq: true } } }
    ],
    NOT: { inventoryCount: { eq: 0 } }
  }) {
    name
  }
}
```

## Pagination

### Offset Pagination (Default)
Most queries support `limit` and `offset` for simple pagination:

```graphql
query PaginatedOrders {
  orders(limit: 20, offset: 40) {
    orderNumber
    totalAmount
  }
}
```

### Page-Based Pagination
Use the `...Pages` query for traditional page numbers:

```graphql
query OrdersByPage {
  ordersPages(page: 3, perPage: 10) {
    items { id, orderNumber }
    pageInfo {
      totalCount
      pageCount
      hasNextPage
    }
  }
}
```

### Relay Connections
If enabled in `query_settings`, Rail Django supports standard Relay cursor pagination.

## Sorting (Ordering)

Use the `orderBy` argument (an array of strings). Prefix a field name with `-` for descending order.

```graphql
query SortedProducts {
  # Sort by price descending, then name ascending
  products(orderBy: ["-price", "name"]) {
    name
    price
  }
}
```

## Grouping and Aggregation

Use the `...Groups` query to perform server-side grouping:

```graphql
query OrderCountsByStatus {
  ordersGroups(groupBy: "status") {
    key # The group value (e.g. "SHIPPED")
    label # A display-friendly label
    count # Number of items in this group
  }
}
```

## Customization (GraphQLMeta)

You can customize query generation for each model:

```python
class Product(models.Model):
    # ...
    class GraphQLMeta:
        # Define allowed fields for filtering and sorting
        filtering = GraphQLMeta.Filtering(
            quick=["name", "sku"], # Fields used for 'quick' search
            fields={"price": ["gt", "lt", "between"]}
        )
        ordering = ["name", "price", "-created_at"]

        # Override default resolvers
        resolvers = {
            "list": "resolve_product_list"
        }

    @staticmethod
    def resolve_product_list(queryset, info, **kwargs):
        # Add custom logic to the default queryset
        return queryset.filter(is_visible=True)
```

## See Also

- [Filtering Deep Dive](./filtering.md)
- [Performance Optimization](./performance.md)
- [Mutations Reference](./mutations.md)

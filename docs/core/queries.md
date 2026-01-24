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
Combine filters with boolean logic to create complex queries. These operators map directly to Django's `Q` objects, allowing for efficient database execution.

*   **AND**: Implicitly applied between fields in a `where` block, but can be used explicitly for nesting.
*   **OR**: Matches if *any* of the provided conditions are true.
*   **NOT**: Inverts the condition (useful for "is not" or "excluding" logic).

```graphql
query AdvancedSearch {
  products(where: {
    # Match products that are either cheap OR promoted
    OR: [
      { price: { lt: 10.00 } },
      { category: { isPromoted: { eq: true } } }
    ],
    # AND must NOT be out of stock
    NOT: { inventoryCount: { eq: 0 } },
    # AND must be active (implicit AND)
    isActive: { eq: true }
  }) {
    name
    price
  }
}
```

## Sorting (Ordering)

Use the `orderBy` argument (an array of strings) to control the order of results. Prefix a field name with `-` for descending order.

### Why use multiple fields?
Sorting by multiple fields is essential for "tie-breaking." For example, if many products have the same price, sorting secondarily by `name` or `id` ensures a consistent, predictable order across different requests or pages.

```graphql
query SortedProducts {
  # 1. Sort by price (most expensive first)
  # 2. Then by name (alphabetical) for products with same price
  products(orderBy: ["-price", "name"]) {
    name
    price
  }
}
```

## Pagination

Rail Django provides three distinct ways to handle large datasets, depending on your UI requirements.

### Offset Pagination (Simple)
Best for small datasets or internal tools where you need to skip a specific number of items.
*   **Pros**: Simple to implement.
*   **Cons**: Performance degrades on very large offsets; results can "shift" if items are added/deleted while paging.

```graphql
query PaginatedOrders {
  orders(limit: 20, offset: 40) {
    orderNumber
    totalAmount
  }
}
```

### Page-Based Pagination (Traditional)
Best for search results where users expect "Page 1, 2, 3" navigation. Use the `...Pages` query.

```graphql
query OrdersByPage {
  ordersPages(page: 3, perPage: 10) {
    items {
      id
      orderNumber
    }
    pageInfo {
      totalCount # Total items matching filters
      pageCount  # Total number of pages available
      hasNextPage
      hasPreviousPage
    }
  }
}
```

### Cursor-Based Pagination (Relay)
Best for "Infinite Scroll" or very large datasets. Instead of an offset, it uses an opaque "cursor" to point to a specific record.
*   **Pros**: High performance; consistent results even if data changes between requests.
*   **Cons**: Cannot jump to a specific page number.

```graphql
query InfiniteScrollProducts($after: String) {
  productsConnection(first: 10, after: $after) {
    edges {
      cursor
      node {
        id
        name
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

## Field Selection and Optimization

One of the greatest strengths of Rail Django is its "Query Intelligence."

### Automatic Join Optimization
When you select fields from related models, Rail Django automatically analyzes your GraphQL AST (Abstract Syntax Tree) and applies `select_related` or `prefetch_related` to your Django QuerySet.

**This prevents the "N+1 Problem" without you having to write any extra code.**

### Efficient Field Selection
Because Rail Django only fetches what you ask for, you can significantly reduce database load and network payload by being specific:

```graphql
query OptimizedProduct {
  products {
    # ONLY these columns will be fetched from the DB
    id
    name

    # This triggers an optimized JOIN or PREFETCH automatically
    category {
      title
    }
  }
}
```

**Pro-Tip:** Avoid selecting large text fields or complex computed properties unless they are actually displayed in your UI. This keeps your API responses fast and your database happy.

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

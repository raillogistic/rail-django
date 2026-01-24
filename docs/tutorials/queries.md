# Queries Deep Dive

This tutorial covers advanced querying, including complex filtering, relationship traversal, and pagination info.

## Nested Filtering

Rail Django's `where` argument allows for powerful, recursive filters.

### Traversing Relationships
Find all orders from customers in the USA:

```graphql
query {
  orders(where: {
    customer: {
      country: { eq: "USA" }
    }
  }) {
    reference
    totalAmount
  }
}
```

### Complex Logic (OR/NOT)
Find products that are either on sale OR in the "Clearance" category:

```graphql
query {
  products(where: {
    OR: [
      { status: { eq: "sale" } },
      { category: { slug: { eq: "clearance" } } }
    ]
  }) {
    name
    price
  }
}
```

## Pagination & Metadata

### Offset Pagination
The standard `products` query returns a list. Use `limit` and `offset`:

```graphql
query {
  products(limit: 10, offset: 20) {
    name
  }
}
```

### Page-Based Metadata
Use the `...Pages` query to get total counts and total pages for UI pagination:

```graphql
query {
  productsPages(page: 1, perPage: 12) {
    items {
      id
      name
    }
    pageInfo {
      totalCount
      pageCount
      hasNextPage
    }
  }
}
```

## Aggregation & Grouping

Get aggregated counts directly from your GraphQL query:

```graphql
query {
  productsGroups(groupBy: "status") {
    key # e.g. "ACTIVE"
    label
    count
  }
}
```

## Sorting
Sort by multiple fields, including related fields:

```graphql
query {
  products(orderBy: ["category__name", "-price"]) {
    name
    price
    category { name }
  }
}
```

## Next Steps

- [Queries Reference](../core/queries.md)
- [Filtering Guide](../core/filtering.md)
- [Performance Tutorial](../core/performance.md)

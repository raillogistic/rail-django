# GraphQL Queries

## Overview

Rail Django automatically generates GraphQL queries for each Django model. This guide covers the different types of queries, advanced filtering, pagination, and sorting.

---

## Table of Contents

1. [Query Types](#query-types)
2. [Single Query](#single-query)
3. [List Query](#list-query)
4. [Advanced Filtering](#advanced-filtering)
5. [Pagination](#pagination)
6. [Sorting (Ordering)](#sorting-ordering)
7. [Grouping (Aggregation)](#grouping-aggregation)
8. [GraphQLMeta - Configuration](#graphqlmeta---configuration)

---

## Query Types

For each model, Rail Django generates:

| Field     | Format            | Description         |
| --------- | ----------------- | ------------------- |
| Single    | `<model>`         | Single object by ID |
| List      | `<model>s`        | List with filters   |
| Paginated | `<model>s_pages`  | Paginated list      |
| Grouped   | `<model>s_groups` | Aggregation         |

**Example for the `Product` model:**

```graphql
type Query {
  product(id: ID!): ProductType
  products(
    where: ProductWhereInput
    orderBy: [String]
    limit: Int
    offset: Int
  ): [ProductType]
  productsPages(
    page: Int
    perPage: Int
    where: ProductWhereInput
  ): ProductPageType
  productsGroups(groupBy: String!, limit: Int): [GroupBucketType]
}
```

---

## Single Query

### By ID

```graphql
query GetProduct($id: ID!) {
  product(id: $id) {
    id
    name
    sku
    price
    category {
      id
      name
    }
  }
}
```

### By Other Field

If configured via `additional_lookup_fields`:

```graphql
query GetProductBySku($sku: String!) {
  product(sku: $sku) {
    id
    name
  }
}
```

Configuration:

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "additional_lookup_fields": {
            "store.Product": ["sku", "slug"],
        },
    },
}
```

---

## List Query

### Basic

```graphql
query ListProducts {
  products {
    id
    name
    price
  }
}
```

### With Limit

```graphql
query ListProducts {
  products(limit: 20, offset: 0) {
    id
    name
  }
}
```

### With Relationships

```graphql
query ListProducts {
  products {
    id
    name
    category {
      name
    }
    supplier {
      companyName
      contactEmail
    }
  }
}
```

---

## Advanced Filtering

Rail Django uses a nested filter syntax (Prisma/Hasura style) with typed per-field inputs.

### Basic Filters

```graphql
query FilteredProducts {
  products(
    where: {
      isActive: { eq: true }
      price: { gte: 100 }
      name: { icontains: "premium" }
    }
  ) {
    id
    name
    price
  }
}
```

### Available Operators

| Field Type   | Operators                                                                |
| ------------ | ------------------------------------------------------------------------ |
| String       | `eq`, `neq`, `contains`, `icontains`, `startsWith`, `endsWith`, `in`, `notIn`, `isNull`, `regex` |
| Integer/Float| `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `notIn`, `between`, `isNull` |
| Boolean      | `eq`, `isNull`                                                          |
| Date/DateTime| `eq`, `gt`, `gte`, `lt`, `lte`, `between`, `isNull`, `year`, `month`, `day`, `today`, `thisWeek`, `thisMonth` |
| ID/UUID      | `eq`, `neq`, `in`, `notIn`, `isNull`                                  |

### Complex Filters (AND/OR/NOT)

```graphql
query ComplexFilter {
  products(
    where: {
      AND: [
        { isActive: { eq: true } }
        { price: { gte: 50 } }
      ]
      OR: [
        { categoryRel: { name: { icontains: "electronics" } } }
        { categoryRel: { name: { icontains: "accessories" } } }
      ]
      NOT: { status: { eq: "discontinued" } }
    }
  ) {
    id
    name
  }
}
```

### Relationship Filters

```graphql
query ProductsByCategory {
  products(
    where: {
      categoryRel: { name: { icontains: "Electronics" } }
      supplierRel: { country: { eq: "US" } }
    }
  ) {
    id
    name
    category {
      name
    }
    supplier {
      country
    }
  }
}
```

### Temporal Filters

```graphql
query RecentProducts {
  products(
    where: {
      createdAt: { today: true }
      # Or: { thisWeek: true }
      # Or: { pastMonth: true }
    }
  ) {
    id
    name
    createdAt
  }
}
```

#### Relation Quantifiers

For M2M and reverse relations:

```graphql
query ProductsWithTags {
  products(
    where: {
      # At least one tag matches
      tagsSome: { name: { eq: "featured" } }

      # Count-based filter
      reviewsCount: { gte: 5 }

      # None match (exclusion)
      tagsNone: { name: { eq: "discontinued" } }
    }
  ) {
    id
    name
  }
}
```

---

## Pagination

### Offset Pagination (Default)

```graphql
query PaginatedProducts($offset: Int!, $limit: Int!) {
  products(offset: $offset, limit: $limit) {
    id
    name
  }
}
```

Variables: `{ "offset": 0, "limit": 20 }`

### Page-Based Pagination

```graphql
query PagedProducts($page: Int!, $perPage: Int!) {
  productsPages(page: $page, perPage: $perPage) {
    items {
      id
      name
    }
    pageInfo {
      totalCount
      pageCount
      currentPage
      perPage
      hasNextPage
      hasPreviousPage
    }
  }
}
```

### Pagination Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "generate_pagination": True,
        "enable_pagination": True,
        "default_page_size": 20,
        "max_page_size": 100,
    },
}
```

### Relay-Style (Optional)

```python
"query_settings": {
    "use_relay": True,
}
```

```graphql
query RelayProducts($first: Int!, $after: String) {
  products(first: $first, after: $after) {
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

---

## Sorting (Ordering)

### Simple Sort

```graphql
query OrderedProducts {
  products(orderBy: ["name"]) {
    id
    name
  }
}
```

### Descending Sort

Prefix with `-`:

```graphql
query OrderedProducts {
  products(orderBy: ["-price"]) {
    id
    name
    price
  }
}
```

### Multiple Sort

```graphql
query OrderedProducts {
  products(orderBy: ["-price", "name"]) {
    id
    name
    price
  }
}
```

### Relationship Sort

```graphql
query OrderedProducts {
  products(orderBy: ["category__name", "-createdAt"]) {
    id
    name
    category {
      name
    }
  }
}
```

### Sort Configuration

```python
class Product(models.Model):
    class GraphQLMeta:
        ordering = GraphQLMeta.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"],
        )
```

---

## Grouping (Aggregation)

### Count by Group

```graphql
query ProductsByCategory {
  productsGroups(groupBy: "category__name", orderBy: "-count", limit: 10) {
    key # Group value
    label # Display label
    count # Number of items
  }
}
```

**Result:**

```json
{
  "data": {
    "products_groups": [
      { "key": "Electronics", "label": "Electronics", "count": 150 },
      { "key": "Accessories", "label": "Accessories", "count": 85 },
      { "key": "Software", "label": "Software", "count": 42 }
    ]
  }
}
```

### With Filters

```graphql
query ActiveProductsByCategory {
  productsGroups(
    groupBy: "category__name"
    where: { isActive: { eq: true } }
    limit: 5
  ) {
    key
    count
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "max_grouping_buckets": 200,
    },
}
```

---

## GraphQLMeta - Configuration

### Complete Structure

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    """
    Product Model with complete GraphQL configuration.

    Attributes:
        name: Product name.
        sku: Unique article code.
        price: Unit price (excluding tax).
        category: Product category.
        is_active: Activation status.
    """
    name = models.CharField("Name", max_length=200)
    sku = models.CharField("SKU", max_length=50, unique=True)
    price = models.DecimalField("Price", max_digits=10, decimal_places=2)
    category = models.ForeignKey("Category", on_delete=models.CASCADE)
    is_active = models.BooleanField("Active", default=True)
    internal_notes = models.TextField("Internal Notes", blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        # ─── Field Exposure ───
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes"],  # Never exposed
            read_only=["sku"],           # Not modifiable via mutation
        )

        # ─── Filtering ───
        filtering = GraphQLMetaConfig.Filtering(
            # Fields for quick search
            quick=["name", "sku"],
            # Detailed configuration by field
            fields={
                "name": GraphQLMetaConfig.FilterField(
                    lookups=["eq", "icontains", "istartsWith"],
                ),
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["eq", "gt", "lt", "between"],
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["eq"],
                ),
                "category__name": GraphQLMetaConfig.FilterField(
                    lookups=["icontains"],
                ),
            },
        )

        # ─── Sorting ───
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"],
        )
```

### Quick Filtering

The `quick` configuration enables fast text search:

```graphql
query QuickSearch {
  products(quick: "iPhone") {
    id
    name
  }
}
```

Searches all `quick` fields with `icontains`.

---

## See Also

- [Mutations](./mutations.md) - CRUD operations
- [Configuration](./configuration.md) - query_settings parameters
- [Permissions](../security/permissions.md) - Query access control

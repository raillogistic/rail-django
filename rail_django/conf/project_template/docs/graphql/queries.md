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
    filters: ProductFilter
    order_by: [String]
    limit: Int
    offset: Int
  ): [ProductType]
  products_pages(
    page: Int
    per_page: Int
    filters: ProductFilter
  ): ProductPageType
  products_groups(group_by: String!, limit: Int): [GroupBucketType]
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
      company_name
      contact_email
    }
  }
}
```

---

## Advanced Filtering

### Simple Filters

```graphql
query FilteredProducts {
  products(
    filters: {
      is_active__exact: true
      price__gte: 100
      name__icontains: "premium"
    }
  ) {
    id
    name
    price
  }
}
```

### Available Operators

| Operator     | Description                 | Example                             |
| ------------ | --------------------------- | ----------------------------------- |
| `exact`      | Exact equality              | `status__exact: "active"`           |
| `iexact`     | Case-insensitive equality   | `name__iexact: "product"`           |
| `contains`   | Contains (case-sensitive)   | `name__contains: "Pro"`             |
| `icontains`  | Contains (case-insensitive) | `name__icontains: "pro"`            |
| `startswith` | Starts with                 | `sku__startswith: "PRD"`            |
| `endswith`   | Ends with                   | `email__endswith: ".com"`           |
| `in`         | In a list                   | `status__in: ["active", "pending"]` |
| `gt`, `gte`  | Greater than (or equal)     | `price__gt: 100`                    |
| `lt`, `lte`  | Less than (or equal)        | `price__lt: 500`                    |
| `range`      | Between two values          | `price__range: [100, 500]`          |
| `isnull`     | Is null                     | `deleted_at__isnull: true`          |
| `date`       | Date part                   | `created_at__date: "2026-01-16"`    |

### Complex Filters (AND/OR/NOT)

```graphql
query ComplexFilter {
  products(
    filters: {
      AND: [{ is_active__exact: true }, { price__gte: 50 }]
      OR: [
        { category__name__icontains: "electronics" }
        { category__name__icontains: "accessories" }
      ]
      NOT: { status__exact: "discontinued" }
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
    filters: {
      category__name__icontains: "Electronics"
      supplier__country__exact: "US"
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

### Predefined Temporal Filters

```graphql
query RecentProducts {
  products(
    filters: {
      created_at_today: true
      # Or: created_at_this_week: true
      # Or: created_at_past_month: true
    }
  ) {
    id
    name
    created_at
  }
}
```

### Nested Filter Style (Prisma/Hasura)

Rail Django also supports a nested filter syntax with typed per-field inputs:

```graphql
query NestedFilters {
  products(
    where: {
      name: { icontains: "premium" }
      price: { gte: 100, lte: 500 }
      category_rel: { name: { eq: "Electronics" } }
      AND: [
        { is_active: { eq: true } }
        { stock: { gt: 0 } }
      ]
    }
  ) {
    id
    name
    price
  }
}
```

Enable nested filters in settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "filter_input_style": "nested",  # Use nested style
        # Or enable both:
        "enable_dual_filter_styles": True,
    },
}
```

#### Relation Quantifiers

For M2M and reverse relations:

```graphql
query ProductsWithTags {
  products(
    where: {
      # At least one tag matches
      tags_some: { name: { eq: "featured" } }

      # Count-based filter
      reviews_count: { gte: 5 }

      # None match (exclusion)
      tags_none: { name: { eq: "discontinued" } }
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
query PagedProducts($page: Int!, $per_page: Int!) {
  products_pages(page: $page, per_page: $per_page) {
    items {
      id
      name
    }
    page_info {
      total_count
      page_count
      current_page
      per_page
      has_next_page
      has_previous_page
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
  products(order_by: ["name"]) {
    id
    name
  }
}
```

### Descending Sort

Prefix with `-`:

```graphql
query OrderedProducts {
  products(order_by: ["-price"]) {
    id
    name
    price
  }
}
```

### Multiple Sort

```graphql
query OrderedProducts {
  products(order_by: ["-price", "name"]) {
    id
    name
    price
  }
}
```

### Relationship Sort

```graphql
query OrderedProducts {
  products(order_by: ["category__name", "-created_at"]) {
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
  products_groups(group_by: "category__name", order_by: "-count", limit: 10) {
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
  products_groups(
    group_by: "category__name"
    filters: { is_active__exact: true }
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
                    lookups=["exact", "icontains", "istartswith"],
                ),
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "gt", "lt", "range"],
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
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

# Queries Deep Dive

This tutorial covers everything about querying data in Rail Django, including filtering, pagination, ordering, and optimization.

## Query Types

Rail Django generates three types of queries for each model:

| Query Type | Example | Purpose |
|------------|---------|---------|
| Single | `product(id: "1")` | Get one object |
| List | `products(...)` | Get multiple objects |
| Paginated | `productsPaginated(...)` | Get with pagination info |

---

## Single Object Queries

Retrieve a single object by ID or alternate lookup:

```graphql
# By ID
query {
  product(id: "123") {
    id
    name
    price
  }
}

# By slug (if configured)
query {
  product(slug: "wireless-headphones") {
    id
    name
    price
  }
}
```

### Configure Alternate Lookups

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "additional_lookup_fields": {
            "Product": ["slug", "sku"],
            "Category": ["slug"]
        }
    }
}
```

---

## List Queries

Retrieve multiple objects with optional filtering:

```graphql
query {
  products {
    id
    name
    price
  }
}
```

### With All Options

```graphql
query {
  products(
    where: { status: { eq: "active" } }
    orderBy: ["-price", "name"]
    limit: 20
    offset: 0
  ) {
    id
    name
    price
    status
  }
}
```

---

## Filtering

### Basic Filters

```graphql
# Exact match
query {
  products(where: { status: { eq: "active" } }) { ... }
}

# In list
query {
  products(where: { status: { in: ["active", "featured"] } }) { ... }
}

# Null check
query {
  products(where: { category: { isNull: false } }) { ... }
}
```

### Comparison Filters

```graphql
# Greater than
query {
  products(where: { price: { gt: 100 } }) { ... }
}

# Less than or equal
query {
  products(where: { price: { lte: 500 } }) { ... }
}

# Range (between)
query {
  products(where: { price: { between: [100, 500] } }) { ... }
}
```

### Text Filters

```graphql
# Contains (case-sensitive)
query {
  products(where: { name: { contains: "Phone" } }) { ... }
}

# Contains (case-insensitive) - Most common
query {
  products(where: { name: { icontains: "phone" } }) { ... }
}

# Starts with
query {
  products(where: { sku: { startsWith: "SKU-" } }) { ... }
}

# Ends with
query {
  products(where: { email: { iEndsWith: "@company.com" } }) { ... }
}
```

### Date Filters

```graphql
# After date
query {
  orders(where: {
    createdAt: { gte: "2024-01-01T00:00:00Z" }
  }) { ... }
}

# Before date
query {
  orders(where: {
    createdAt: { lt: "2024-12-31T23:59:59Z" }
  }) { ... }
}

# By year
query {
  orders(where: { createdAt: { year: 2024 } }) { ... }
}

# By month
query {
  orders(where: { createdAt: { month: 12 } }) { ... }
}

# Date range
query {
  orders(where: {
    createdAt: {
      gte: "2024-01-01"
      lte: "2024-12-31"
    }
  }) { ... }
}
```

### Relation Filters

Filter by related object fields:

```graphql
# Filter products by category name
query {
  products(where: {
    category: { name: { icontains: "electronics" } }
  }) {
    id
    name
    category {
      name
    }
  }
}

# Deep nesting
query {
  orderItems(where: {
    order: {
      customer: {
        country: { eq: "USA" }
      }
    }
  }) { ... }
}
```

### Logical Operators

#### AND (implicit)

Multiple conditions are ANDed by default:

```graphql
query {
  products(where: {
    status: { eq: "active" }
    price: { gte: 50 }
    featured: { eq: true }
  }) { ... }
}
# Finds: status = active AND price >= 50 AND featured = true
```

#### OR

Use `OR` for alternatives:

```graphql
query {
  products(where: {
    OR: [
      { status: { eq: "sale" } }
      { featured: { eq: true } }
    ]
  }) { ... }
}
# Finds: status = sale OR featured = true
```

#### NOT

Exclude matches:

```graphql
query {
  products(where: {
    NOT: { status: { eq: "archived" } }
  }) { ... }
}
# Finds: everything EXCEPT status = archived
```

#### Complex Combinations

```graphql
query {
  products(where: {
    AND: [
      { status: { eq: "active" } }
      { OR: [
        { price: { lt: 100 } }
        { featured: { eq: true } }
      ]}
      { NOT: { category: { name: { eq: "Clearance" } } } }
    ]
  }) { ... }
}
# Finds: active AND (cheap OR featured) AND NOT clearance
```

---

## Filter Reference

### String Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Exact match | `{ name: { eq: "iPhone" } }` |
| `in` | In list | `{ status: { in: ["a", "b"] } }` |
| `isNull` | Null check | `{ email: { isNull: false } }` |
| `contains` | Case-sensitive contains | `{ name: { contains: "Pro" } }` |
| `icontains` | Case-insensitive contains | `{ name: { icontains: "pro" } }` |
| `startsWith` | Starts with | `{ sku: { startsWith: "SKU-" } }` |
| `iStartsWith` | Case-insensitive starts with | `{ sku: { iStartsWith: "sku-" } }` |
| `endsWith` | Ends with | `{ email: { endsWith: ".com" } }` |
| `iEndsWith` | Case-insensitive ends with | `{ email: { iEndsWith: ".COM" } }` |

### Numeric Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equals | `{ price: { eq: 99.99 } }` |
| `in` | In list | `{ quantity: { in: [1, 2, 3] } }` |
| `gt` | Greater than | `{ price: { gt: 100 } }` |
| `gte` | Greater than or equal | `{ price: { gte: 100 } }` |
| `lt` | Less than | `{ price: { lt: 500 } }` |
| `lte` | Less than or equal | `{ price: { lte: 500 } }` |
| `between` | Range (inclusive) | `{ price: { between: [100, 500] } }` |

### Date Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Exact date | `{ date: { eq: "2024-01-15" } }` |
| `gt` | After | `{ date: { gt: "2024-01-01" } }` |
| `gte` | On or after | `{ date: { gte: "2024-01-01" } }` |
| `lt` | Before | `{ date: { lt: "2024-12-31" } }` |
| `lte` | On or before | `{ date: { lte: "2024-12-31" } }` |
| `year` | By year | `{ date: { year: 2024 } }` |
| `month` | By month | `{ date: { month: 6 } }` |
| `day` | By day | `{ date: { day: 15 } }` |

---

## Ordering

### Basic Ordering

```graphql
# Ascending (A-Z, low to high)
query {
  products(orderBy: ["name"]) { ... }
}

# Descending (Z-A, high to low)
query {
  products(orderBy: ["-price"]) { ... }
}

# Multiple fields
query {
  products(orderBy: ["-featured", "price", "name"]) { ... }
}
# First by featured (desc), then by price (asc), then by name (asc)
```

### Order by Related Fields

```graphql
query {
  products(orderBy: ["category__name", "name"]) {
    name
    category {
      name
    }
  }
}
```

### Configure Allowed Ordering

```python
class Product(models.Model):
    class GraphQLMeta:
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"]
        )
```

---

## Pagination

### Offset Pagination

Simple offset-based pagination:

```graphql
# First page
query {
  products(limit: 20, offset: 0) { ... }
}

# Second page
query {
  products(limit: 20, offset: 20) { ... }
}

# Third page
query {
  products(limit: 20, offset: 40) { ... }
}
```

### Page-Based Pagination

With full pagination info:

```graphql
query {
  productsPaginated(page: 1, pageSize: 20) {
    items {
      id
      name
      price
    }
    pagination {
      totalCount
      totalPages
      currentPage
      pageSize
      hasNextPage
      hasPreviousPage
    }
  }
}
```

**Response:**
```json
{
  "data": {
    "productsPaginated": {
      "items": [...],
      "pagination": {
        "totalCount": 156,
        "totalPages": 8,
        "currentPage": 1,
        "pageSize": 20,
        "hasNextPage": true,
        "hasPreviousPage": false
      }
    }
  }
}
```

### Pagination Settings

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "default_page_size": 20,
        "max_page_size": 100,
        "enable_pagination": True
    }
}
```

---

## Grouping Queries

Aggregate data by groups:

```graphql
query {
  productsGrouped(
    groupBy: ["status", "category__name"]
    aggregations: [
      { field: "price", function: SUM, alias: "totalValue" }
      { field: "price", function: AVG, alias: "avgPrice" }
      { field: "id", function: COUNT, alias: "productCount" }
    ]
  ) {
    keys
    count
    aggregations
  }
}
```

**Response:**
```json
{
  "data": {
    "productsGrouped": [
      {
        "keys": { "status": "active", "category__name": "Electronics" },
        "count": 45,
        "aggregations": {
          "totalValue": 12500.00,
          "avgPrice": 277.78,
          "productCount": 45
        }
      },
      ...
    ]
  }
}
```

### Available Aggregations

| Function | Description |
|----------|-------------|
| `COUNT` | Count records |
| `SUM` | Sum values |
| `AVG` | Average |
| `MIN` | Minimum value |
| `MAX` | Maximum value |

---

## Filter Schema Introspection

Discover available filters for a model:

```graphql
query {
  filterSchema(model: "store.Product", depth: 2) {
    fields {
      name
      type
      operators
      nested {
        name
        operators
      }
    }
  }
}
```

---

## Performance Optimization

### Automatic Optimization

Rail Django automatically optimizes queries:

```graphql
# This query...
query {
  products {
    name
    category {
      name
    }
    tags {
      name
    }
  }
}

# ...generates this SQL:
# SELECT product.*, category.*
# FROM product
# LEFT JOIN category ON product.category_id = category.id
# PREFETCH tags via separate query
```

### Request Only Needed Fields

Only request fields you need:

```graphql
# ❌ Bad - fetches everything
query {
  products {
    id
    name
    description
    price
    cost
    category { ... }
    tags { ... }
    reviews { ... }
    variants { ... }
  }
}

# ✅ Good - only needed fields
query {
  products {
    id
    name
    price
  }
}
```

### Use Pagination

Always paginate large result sets:

```graphql
# ❌ Bad - could return thousands
query {
  products {
    id
    name
  }
}

# ✅ Good - limited results
query {
  products(limit: 50) {
    id
    name
  }
}
```

---

## Practical Examples

### Product Catalog

```graphql
query ProductCatalog(
  $category: String
  $minPrice: Decimal
  $maxPrice: Decimal
  $search: String
  $page: Int
) {
  productsPaginated(
    where: {
      status: { eq: "active" }
      category: { slug: { eq: $category } }
      price: { gte: $minPrice, lte: $maxPrice }
      OR: [
        { name: { icontains: $search } }
        { description: { icontains: $search } }
      ]
    }
    orderBy: ["-featured", "price"]
    page: $page
    pageSize: 24
  ) {
    items {
      id
      name
      slug
      price
      featured
      inStock
      category {
        name
        slug
      }
    }
    pagination {
      totalCount
      totalPages
      hasNextPage
    }
  }
}
```

### Order History

```graphql
query OrderHistory($customerId: ID!, $status: [String]) {
  orders(
    where: {
      customer: { id: { eq: $customerId } }
      status: { in: $status }
    }
    orderBy: ["-createdAt"]
    limit: 10
  ) {
    id
    reference
    status
    totalAmount
    createdAt
    items {
      product {
        name
      }
      quantity
      unitPrice
    }
  }
}
```

### Dashboard Stats

```graphql
query DashboardStats {
  # Orders by status
  ordersByStatus: ordersGrouped(
    groupBy: ["status"]
  ) {
    keys
    count
  }

  # Revenue by month
  revenueByMonth: ordersGrouped(
    groupBy: ["createdAt__month"]
    aggregations: [
      { field: "totalAmount", function: SUM, alias: "revenue" }
    ]
    where: {
      createdAt: { year: 2024 }
      status: { in: ["delivered", "shipped"] }
    }
  ) {
    keys
    aggregations
  }

  # Top categories
  topCategories: productsGrouped(
    groupBy: ["category__name"]
    aggregations: [
      { field: "id", function: COUNT, alias: "productCount" }
    ]
  ) {
    keys
    aggregations
  }
}
```

---

## Next Steps

- [Mutations Deep Dive](./mutations.md) - Create, update, delete operations
- [Nested Mutations](./nested-mutations.md) - Complex data operations
- [Performance](./performance.md) - Optimization techniques

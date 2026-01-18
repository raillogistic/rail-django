# Filtering Guide

Rail Django provides two filter input styles for GraphQL queries: the **nested** style (Prisma/Hasura-style typed inputs, default) and the optional **flat** style (Django-style `__lookup` syntax).

## Filter Styles

### Nested Style (Default)

The nested filter style provides typed per-field filter inputs with better IDE support and schema introspection:

```graphql
query {
  users(where: {
    username: { icontains: "john" }
    age: { gte: 18 }
    is_active: { eq: true }
  }) {
    id
    username
  }
}
```

Filter input type: `UserWhereInput`

### Flat Style (Django-style)

The flat filter style uses Django's familiar double-underscore lookup syntax:

```graphql
query {
  users(filters: {
    username__icontains: "john"
    age__gte: 18
    is_active__exact: true
  }) {
    id
    username
  }
}
```

Filter input type: `UserComplexFilter`

## Configuration

Configure filter style in your Django settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        # Choose one: "nested" (default) or "flat"
        "filter_input_style": "flat",  # Switch to flat style

        # Or enable both styles simultaneously
        "enable_dual_filter_styles": True,
    }
}
```

### Style Comparison

| Feature | Nested Style (Default) | Flat Style |
|---------|------------------------|-----------|
| Argument name | `where` | `filters` |
| Type name | `{Model}WhereInput` | `{Model}ComplexFilter` |
| Syntax | `field: { lookup: value }` | `field__lookup: value` |
| IDE support | Excellent (typed inputs) | Limited |
| Schema introspection | Per-field operators visible | Generic |

## Boolean Operators

Both styles support AND, OR, and NOT operators for complex queries.

### Flat Style Boolean Operators

```graphql
query {
  posts(filters: {
    AND: [
      { title__icontains: "python" }
      { category__name: "Programming" }
    ]
    OR: [
      { status: "published" }
      { status: "featured" }
    ]
    NOT: { is_draft: true }
  }) {
    id
    title
  }
}
```

### Nested Style Boolean Operators

```graphql
query {
  posts(where: {
    AND: [
      { title: { icontains: "python" } }
      { category: { name: { eq: "Programming" } } }
    ]
    OR: [
      { status: { eq: "published" } }
      { status: { eq: "featured" } }
    ]
    NOT: { is_draft: { eq: true } }
  }) {
    id
    title
  }
}
```

## Filter Operators by Type

### String Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Exact match | `{ name: { eq: "John" } }` |
| `neq` | Not equal | `{ name: { neq: "Admin" } }` |
| `contains` | Contains (case-sensitive) | `{ name: { contains: "doe" } }` |
| `icontains` | Contains (case-insensitive) | `{ name: { icontains: "doe" } }` |
| `starts_with` | Starts with (case-sensitive) | `{ name: { starts_with: "J" } }` |
| `istarts_with` | Starts with (case-insensitive) | `{ name: { istarts_with: "j" } }` |
| `ends_with` | Ends with (case-sensitive) | `{ name: { ends_with: "son" } }` |
| `iends_with` | Ends with (case-insensitive) | `{ name: { iends_with: "SON" } }` |
| `in` | In list | `{ status: { in: ["A", "B"] } }` |
| `not_in` | Not in list | `{ status: { not_in: ["X"] } }` |
| `is_null` | Is null | `{ bio: { is_null: true } }` |
| `regex` | Regex match (case-sensitive) | `{ email: { regex: ".*@example\\.com" } }` |
| `iregex` | Regex match (case-insensitive) | `{ email: { iregex: ".*@EXAMPLE\\.com" } }` |

### Numeric Filters (Int, Float, Decimal)

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal to | `{ price: { eq: 100 } }` |
| `neq` | Not equal to | `{ price: { neq: 0 } }` |
| `gt` | Greater than | `{ price: { gt: 50 } }` |
| `gte` | Greater than or equal | `{ price: { gte: 50 } }` |
| `lt` | Less than | `{ price: { lt: 100 } }` |
| `lte` | Less than or equal | `{ price: { lte: 100 } }` |
| `in` | In list | `{ quantity: { in: [1, 5, 10] } }` |
| `not_in` | Not in list | `{ quantity: { not_in: [0] } }` |
| `between` | Between range (inclusive) | `{ price: { between: [10, 50] } }` |
| `is_null` | Is null | `{ discount: { is_null: true } }` |

### Boolean Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal to | `{ is_active: { eq: true } }` |
| `is_null` | Is null | `{ verified: { is_null: false } }` |

### Date Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal to | `{ birth_date: { eq: "1990-01-15" } }` |
| `neq` | Not equal to | `{ birth_date: { neq: "2000-01-01" } }` |
| `gt` | After date | `{ created: { gt: "2024-01-01" } }` |
| `gte` | On or after date | `{ created: { gte: "2024-01-01" } }` |
| `lt` | Before date | `{ created: { lt: "2025-01-01" } }` |
| `lte` | On or before date | `{ created: { lte: "2025-01-01" } }` |
| `between` | Between dates (inclusive) | `{ created: { between: ["2024-01-01", "2024-12-31"] } }` |
| `is_null` | Is null | `{ deleted_at: { is_null: true } }` |
| `year` | Filter by year | `{ created: { year: 2024 } }` |
| `month` | Filter by month (1-12) | `{ created: { month: 12 } }` |
| `day` | Filter by day of month | `{ created: { day: 25 } }` |
| `week_day` | Filter by day of week | `{ created: { week_day: 1 } }` |
| `today` | Is today | `{ created: { today: true } }` |
| `yesterday` | Is yesterday | `{ created: { yesterday: true } }` |
| `this_week` | Is this week | `{ created: { this_week: true } }` |
| `past_week` | Is past week | `{ created: { past_week: true } }` |
| `this_month` | Is this month | `{ created: { this_month: true } }` |
| `past_month` | Is past month | `{ created: { past_month: true } }` |
| `this_year` | Is this year | `{ created: { this_year: true } }` |
| `past_year` | Is past year | `{ created: { past_year: true } }` |

### DateTime Filters

DateTime filters include all Date operators plus:

| Operator | Description | Example |
|----------|-------------|---------|
| `hour` | Filter by hour (0-23) | `{ timestamp: { hour: 14 } }` |
| `minute` | Filter by minute (0-59) | `{ timestamp: { minute: 30 } }` |
| `date` | Filter by date part | `{ timestamp: { date: "2024-01-15" } }` |

### ID Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal to | `{ id: { eq: "123" } }` |
| `neq` | Not equal to | `{ id: { neq: "456" } }` |
| `in` | In list | `{ id: { in: ["1", "2", "3"] } }` |
| `not_in` | Not in list | `{ id: { not_in: ["999"] } }` |
| `is_null` | Is null | `{ parent_id: { is_null: true } }` |

### UUID Filters

Same operators as ID filters, but accepts UUID strings.

### JSON Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal to (entire JSON) | `{ meta: { eq: "{}" } }` |
| `is_null` | Is null | `{ meta: { is_null: true } }` |
| `has_key` | Has key | `{ meta: { has_key: "version" } }` |
| `has_keys` | Has all keys | `{ meta: { has_keys: ["a", "b"] } }` |
| `has_any_keys` | Has any key | `{ meta: { has_any_keys: ["x", "y"] } }` |

## Relation Filters

The nested filter style provides powerful relation filtering.

### Foreign Key Filters

Filter by relation ID or by nested fields:

```graphql
query {
  posts(where: {
    # Filter by category ID
    category: { eq: "5" }

    # OR filter by nested category fields
    category_rel: {
      name: { eq: "Technology" }
      is_active: { eq: true }
    }
  }) {
    id
    title
  }
}
```

### Many-to-Many Filters

Use quantifier suffixes for M2M and reverse relations:

| Suffix | Description | Example |
|--------|-------------|---------|
| `_some` | At least one related object matches | `tags_some: { name: { eq: "python" } }` |
| `_every` | All related objects match | `tags_every: { is_approved: { eq: true } }` |
| `_none` | No related objects match | `tags_none: { name: { eq: "deprecated" } }` |
| `_count` | Count of related objects | `tags_count: { gte: 3 }` |

Example:

```graphql
query {
  posts(where: {
    # Posts with at least one "python" tag
    tags_some: { name: { icontains: "python" } }

    # Posts with at least 2 comments
    comments_count: { gte: 2 }

    # Posts with no "deprecated" tags
    tags_none: { name: { eq: "deprecated" } }
  }) {
    id
    title
  }
}
```

### Count Filters

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Exactly N related | `{ comments_count: { eq: 5 } }` |
| `neq` | Not N related | `{ comments_count: { neq: 0 } }` |
| `gt` | More than N | `{ comments_count: { gt: 10 } }` |
| `gte` | N or more | `{ comments_count: { gte: 1 } }` |
| `lt` | Fewer than N | `{ comments_count: { lt: 100 } }` |
| `lte` | N or fewer | `{ comments_count: { lte: 50 } }` |

## Complex Query Examples

### Multi-condition Filter

```graphql
query {
  products(where: {
    AND: [
      { name: { icontains: "phone" } }
      { price: { between: [100, 500] } }
      { is_available: { eq: true } }
    ]
  }) {
    id
    name
    price
  }
}
```

### Either/Or Filter

```graphql
query {
  users(where: {
    OR: [
      { role: { eq: "admin" } }
      { is_superuser: { eq: true } }
    ]
  }) {
    id
    username
  }
}
```

### Exclude Pattern

```graphql
query {
  posts(where: {
    NOT: {
      OR: [
        { status: { eq: "draft" } }
        { is_deleted: { eq: true } }
      ]
    }
  }) {
    id
    title
  }
}
```

### Nested Relation with Boolean Logic

```graphql
query {
  orders(where: {
    AND: [
      { customer_rel: { country: { eq: "US" } } }
      {
        OR: [
          { total: { gte: 1000 } }
          { items_count: { gte: 10 } }
        ]
      }
    ]
    NOT: { status: { eq: "cancelled" } }
  }) {
    id
    total
  }
}
```

## Dual Filter Mode

When `enable_dual_filter_styles` is enabled, both `filters` and `where` arguments are available. They apply with AND logic:

```graphql
query {
  posts(
    filters: { status: "published" }
    where: { category_rel: { name: { eq: "Tech" } } }
  ) {
    id
    title
  }
}
```

This returns posts where `status = "published"` AND `category.name = "Tech"`.

## Quick Search

Both styles support the `quick` argument for simple text search across configured fields:

```graphql
query {
  users(quick: "john", where: { is_active: { eq: true } }) {
    id
    username
    email
  }
}
```

Configure quick search fields in GraphQLMeta:

```python
class User(models.Model):
    class GraphQLMeta(GraphQLMetaConfig):
        filtering = GraphQLMetaConfig.Filtering(
            quick=["username", "email", "first_name", "last_name"]
        )
```

## Performance Considerations

1. **Indexed fields**: Filter on indexed database fields for best performance
2. **Count filters**: `_count` filters use SQL COUNT subqueries; consider indexing foreign keys
3. **Nested depth**: Deep relation filtering (`a_rel.b_rel.c_rel`) may result in complex JOINs
4. **Large `in` lists**: Very large `in` lists may hit database limits

## See Also

- [GraphQL API Guide](./graphql.md) - General API documentation
- [GraphQLMeta Reference](../reference/meta.md) - Per-model filter configuration
- [Configuration Reference](../reference/configuration.md) - Settings reference

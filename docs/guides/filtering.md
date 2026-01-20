# Filtering Guide

Rail Django provides a nested filter style (Prisma/Hasura-style typed inputs) for GraphQL queries with typed per-field filter inputs, excellent IDE support, and schema introspection.

## Basic Usage

```graphql
query {
  users(
    where: {
      username: { icontains: "john" }
      age: { gte: 18 }
      is_active: { eq: true }
    }
  ) {
    id
    username
  }
}
```

Filter input type: `UserWhereInput`

## Boolean Operators

Use AND, OR, and NOT operators for complex queries:

```graphql
query {
  posts(
    where: {
      AND: [
        { title: { icontains: "python" } }
        { category_rel: { name: { eq: "Programming" } } }
      ]
      OR: [{ status: { eq: "published" } }, { status: { eq: "featured" } }]
      NOT: { is_draft: { eq: true } }
    }
  ) {
    id
    title
  }
}
```

## Filter Operators by Type

### String Filters

| Operator       | Description                    | Example                                     |
| -------------- | ------------------------------ | ------------------------------------------- |
| `eq`           | Exact match                    | `{ name: { eq: "John" } }`                  |
| `neq`          | Not equal                      | `{ name: { neq: "Admin" } }`                |
| `contains`     | Contains (case-sensitive)      | `{ name: { contains: "doe" } }`             |
| `icontains`    | Contains (case-insensitive)    | `{ name: { icontains: "doe" } }`            |
| `starts_with`  | Starts with (case-sensitive)   | `{ name: { starts_with: "J" } }`            |
| `istarts_with` | Starts with (case-insensitive) | `{ name: { istarts_with: "j" } }`           |
| `ends_with`    | Ends with (case-sensitive)     | `{ name: { ends_with: "son" } }`            |
| `iends_with`   | Ends with (case-insensitive)   | `{ name: { iends_with: "SON" } }`           |
| `in`           | In list                        | `{ status: { in: ["A", "B"] } }`            |
| `not_in`       | Not in list                    | `{ status: { not_in: ["X"] } }`             |
| `is_null`      | Is null                        | `{ bio: { is_null: true } }`                |
| `regex`        | Regex match (case-sensitive)   | `{ email: { regex: ".*@example\\.com" } }`  |
| `iregex`       | Regex match (case-insensitive) | `{ email: { iregex: ".*@EXAMPLE\\.com" } }` |

### Numeric Filters (Int, Float, Decimal)

| Operator  | Description               | Example                            |
| --------- | ------------------------- | ---------------------------------- |
| `eq`      | Equal to                  | `{ price: { eq: 100 } }`           |
| `neq`     | Not equal to              | `{ price: { neq: 0 } }`            |
| `gt`      | Greater than              | `{ price: { gt: 50 } }`            |
| `gte`     | Greater than or equal     | `{ price: { gte: 50 } }`           |
| `lt`      | Less than                 | `{ price: { lt: 100 } }`           |
| `lte`     | Less than or equal        | `{ price: { lte: 100 } }`          |
| `in`      | In list                   | `{ quantity: { in: [1, 5, 10] } }` |
| `not_in`  | Not in list               | `{ quantity: { not_in: [0] } }`    |
| `between` | Between range (inclusive) | `{ price: { between: [10, 50] } }` |
| `is_null` | Is null                   | `{ discount: { is_null: true } }`  |

### Boolean Filters

| Operator  | Description | Example                            |
| --------- | ----------- | ---------------------------------- |
| `eq`      | Equal to    | `{ is_active: { eq: true } }`      |
| `is_null` | Is null     | `{ verified: { is_null: false } }` |

### Date Filters

| Operator     | Description               | Example                                                  |
| ------------ | ------------------------- | -------------------------------------------------------- |
| `eq`         | Equal to                  | `{ birth_date: { eq: "1990-01-15" } }`                   |
| `neq`        | Not equal to              | `{ birth_date: { neq: "2000-01-01" } }`                  |
| `gt`         | After date                | `{ created: { gt: "2024-01-01" } }`                      |
| `gte`        | On or after date          | `{ created: { gte: "2024-01-01" } }`                     |
| `lt`         | Before date               | `{ created: { lt: "2025-01-01" } }`                      |
| `lte`        | On or before date         | `{ created: { lte: "2025-01-01" } }`                     |
| `between`    | Between dates (inclusive) | `{ created: { between: ["2024-01-01", "2024-12-31"] } }` |
| `is_null`    | Is null                   | `{ deleted_at: { is_null: true } }`                      |
| `year`       | Filter by year            | `{ created: { year: 2024 } }`                            |
| `month`      | Filter by month (1-12)    | `{ created: { month: 12 } }`                             |
| `day`        | Filter by day of month    | `{ created: { day: 25 } }`                               |
| `week_day`   | Filter by day of week     | `{ created: { week_day: 1 } }`                           |
| `today`      | Is today                  | `{ created: { today: true } }`                           |
| `yesterday`  | Is yesterday              | `{ created: { yesterday: true } }`                       |
| `this_week`  | Is this week              | `{ created: { this_week: true } }`                       |
| `past_week`  | Is past week              | `{ created: { past_week: true } }`                       |
| `this_month` | Is this month             | `{ created: { this_month: true } }`                      |
| `past_month` | Is past month             | `{ created: { past_month: true } }`                      |
| `this_year`  | Is this year              | `{ created: { this_year: true } }`                       |
| `past_year`  | Is past year              | `{ created: { past_year: true } }`                       |

### DateTime Filters

DateTime filters include all Date operators plus:

| Operator | Description             | Example                                 |
| -------- | ----------------------- | --------------------------------------- |
| `hour`   | Filter by hour (0-23)   | `{ timestamp: { hour: 14 } }`           |
| `minute` | Filter by minute (0-59) | `{ timestamp: { minute: 30 } }`         |
| `date`   | Filter by date part     | `{ timestamp: { date: "2024-01-15" } }` |

### ID Filters

| Operator  | Description  | Example                            |
| --------- | ------------ | ---------------------------------- |
| `eq`      | Equal to     | `{ id: { eq: "123" } }`            |
| `neq`     | Not equal to | `{ id: { neq: "456" } }`           |
| `in`      | In list      | `{ id: { in: ["1", "2", "3"] } }`  |
| `not_in`  | Not in list  | `{ id: { not_in: ["999"] } }`      |
| `is_null` | Is null      | `{ parent_id: { is_null: true } }` |

### UUID Filters

Same operators as ID filters, but accepts UUID strings.

### JSON Filters

| Operator       | Description            | Example                                  |
| -------------- | ---------------------- | ---------------------------------------- |
| `eq`           | Equal to (entire JSON) | `{ meta: { eq: "{}" } }`                 |
| `is_null`      | Is null                | `{ meta: { is_null: true } }`            |
| `has_key`      | Has key                | `{ meta: { has_key: "version" } }`       |
| `has_keys`     | Has all keys           | `{ meta: { has_keys: ["a", "b"] } }`     |
| `has_any_keys` | Has any key            | `{ meta: { has_any_keys: ["x", "y"] } }` |

## Relation Filters

### Foreign Key Filters

Filter by relation ID or by nested fields:

```graphql
query {
  posts(
    where: {
      # Filter by category ID
      category: { eq: "5" }
      # OR filter by nested category fields
      category_rel: { name: { eq: "Technology" }, is_active: { eq: true } }
    }
  ) {
    id
    title
  }
}
```

### Many-to-Many Filters

Use quantifier suffixes for M2M and reverse relations:

| Suffix   | Description                         | Example                                     |
| -------- | ----------------------------------- | ------------------------------------------- |
| `_some`  | At least one related object matches | `tags_some: { name: { eq: "python" } }`     |
| `_every` | All related objects match           | `tags_every: { is_approved: { eq: true } }` |
| `_none`  | No related objects match            | `tags_none: { name: { eq: "deprecated" } }` |
| `_count` | Count of related objects            | `tags_count: { gte: 3 }`                    |

Example:

```graphql
query {
  posts(
    where: {
      # Posts with at least one "python" tag
      tags_some: { name: { icontains: "python" } }
      # Posts with at least 2 comments
      comments_count: { gte: 2 }
      # Posts with no "deprecated" tags
      tags_none: { name: { eq: "deprecated" } }
    }
  ) {
    id
    title
  }
}
```

### Count Filters

| Operator | Description       | Example                           |
| -------- | ----------------- | --------------------------------- |
| `eq`     | Exactly N related | `{ comments_count: { eq: 5 } }`   |
| `neq`    | Not N related     | `{ comments_count: { neq: 0 } }`  |
| `gt`     | More than N       | `{ comments_count: { gt: 10 } }`  |
| `gte`    | N or more         | `{ comments_count: { gte: 1 } }`  |
| `lt`     | Fewer than N      | `{ comments_count: { lt: 100 } }` |
| `lte`    | N or fewer        | `{ comments_count: { lte: 50 } }` |

## Aggregation Filters

Use `{relation}_agg` to filter by aggregated values on related objects. Provide the
field to aggregate and one or more aggregate filters (`sum`, `avg`, `min`, `max`,
`count`).

```graphql
query {
  products(
    where: { order_items_agg: { field: "unit_price", sum: { gte: 1000 } } }
  ) {
    id
    name
  }
}
```

```graphql
query {
  products(where: { order_items_agg: { field: "id", count: { gte: 2 } } }) {
    id
    name
  }
}
```

## Filter Presets

Presets allow you to define reusable filter configurations in your model's
`GraphQLMeta` class. They can be combined with other presets and custom
filters.

### Defining Presets

Define presets in your model's `GraphQLMeta`:

```python
class Order(models.Model):
    # ...

    class GraphQLMeta:
        filter_presets = {
            "recent": {
                "created_at": {"this_month": True}
            },
            "high_value": {
                "total": {"gte": 1000}
            },
            "pending": {
                "status": {"in_": ["pending", "processing"]}
            }
        }
```

### Using Presets in Queries

Use the `presets` argument to apply one or more presets:

```graphql
query {
  # Apply a single preset
  orders(presets: ["recent"]) {
    id
    created_at
  }
}
```

Combine multiple presets (AND logic):

```graphql
query {
  orders(presets: ["recent", "high_value"]) {
    id
    total_amount
    created_at
  }
}
```

Mix presets with custom filters:

```graphql
query {
  orders(
    presets: ["high_value"]
    where: { customer_rel: { country: { eq: "US" } } }
  ) {
    id
    total_amount
    customer {
      name
    }
  }
}
```

## Saved Filters

Saved filters allow users to persist query configurations in the database for later
reuse. They can be private (visible only to the creator) or shared.

### Creating Saved Filters

Use the `create_savedfilter` mutation to save a filter configuration:

```graphql
mutation {
  create_savedfilter(
    input: {
      name: "High Value Pending"
      model_name: "Order"
      filter_json: { total_amount: { gte: 1000 }, status: { eq: "pending" } }
      is_shared: true
    }
  ) {
    saved_filter {
      id
      name
    }
  }
}
```

### Applying Saved Filters

Use the `saved_filter` argument in your query to apply a stored filter by name or ID:

```graphql
query {
  orders(saved_filter: "High Value Pending") {
    id
    total_amount
    status
  }
}
```

You can also combine saved filters with ad-hoc filters (ad-hoc filters take precedence):

```graphql
query {
  orders(
    saved_filter: "High Value Pending"
    where: { created_at: { this_month: true } }
  ) {
    id
    total_amount
  }
}
```

## Complex Query Examples

### Multi-condition Filter

```graphql
query {
  products(
    where: {
      AND: [
        { name: { icontains: "phone" } }
        { price: { between: [100, 500] } }
        { is_available: { eq: true } }
      ]
    }
  ) {
    id
    name
    price
  }
}
```

### Either/Or Filter

```graphql
query {
  users(
    where: { OR: [{ role: { eq: "admin" } }, { is_superuser: { eq: true } }] }
  ) {
    id
    username
  }
}
```

### Exclude Pattern

```graphql
query {
  posts(
    where: {
      NOT: { OR: [{ status: { eq: "draft" } }, { is_deleted: { eq: true } }] }
    }
  ) {
    id
    title
  }
}
```

### Nested Relation with Boolean Logic

```graphql
query {
  orders(
    where: {
      AND: [
        { customer_rel: { country: { eq: "US" } } }
        { OR: [{ total: { gte: 1000 } }, { items_count: { gte: 10 } }] }
      ]
      NOT: { status: { eq: "cancelled" } }
    }
  ) {
    id
    total
  }
}
```

## Distinct On

Deduplicate results by specific fields (Postgres `DISTINCT ON` equivalent). This is
useful for queries like "latest order per customer".

**Note:** On Postgres, the `distinct_on` fields must match the beginning of your `order_by` list.

```graphql
# Get the single latest product per brand
query {
  products(
    distinct_on: ["brand"]
    order_by: ["brand", "-created_at"]
  ) {
    id
    brand
    name
    created_at
  }
}
```

```graphql
# Get the most recent order for each customer
query {
  orders(
    distinct_on: ["customer_id"]
    order_by: ["customer_id", "-created_at"]
  ) {
    id
    customer { name }
    created_at
    total_amount
  }
}
```

    total
  }
}
```

## Computed / Expression Filters

Filter by database expressions and computed values without storing them in the database.
Define these in your model's `GraphQLMeta`.

```python
from django.db.models import F, ExpressionWrapper, FloatField
from django.db.models.functions import Now, Extract

class Product(models.Model):
    # ... fields ...

    class GraphQLMeta:
        computed_filters = {
            "profit_margin": {
                "expression": ExpressionWrapper(
                    F("price") - F("cost_price"),
                    output_field=FloatField()
                ),
                "filter_type": "float",
                "description": "Profit margin (price - cost)",
            },
            "age_days": {
                "expression": Extract(Now() - F("created_at"), "day"),
                "filter_type": "int",
                "description": "Days since creation",
            }
        }
```

Usage in GraphQL:

```graphql
query {
  products(where: {
    profit_margin: { gte: 50.0 }
    age_days: { lte: 30 }
  }) {
    id
    name
    price
  }
}
```

## Quick Search


The `quick` argument provides simple text search across configured fields:

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

## Full-Text Search

Full-text search is opt-in and uses Postgres `SearchVector`/`SearchQuery` when
available. Other databases fall back to `icontains` across the selected fields.

Enable it in schema settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_full_text_search": True,
        "fts_config": "english",
        "fts_search_type": "websearch",
        "fts_rank_threshold": None,
    }
}
```

Usage example:

```graphql
query {
  articles(
    where: {
      search: {
        query: "django graphql api"
        fields: ["title", "body"]
        search_type: WEBSEARCH
      }
    }
  ) {
    id
    title
  }
}
```

Optional rank threshold (Postgres only):

```graphql
query {
  products(
    where: {
      search: {
        query: "wireless headphones"
        fields: ["name", "description"]
        rank_threshold: 0.1
      }
    }
  ) {
    id
    name
  }
}
```

## Security

Rail Django includes built-in security features to protect against malicious or overly complex filters.

### Filter Depth Limiting

Filters are limited to a maximum nesting depth to prevent denial-of-service attacks via
deeply nested boolean operators. The default limit is 10 levels.

```python
# This would be rejected (too deep):
where = {"AND": [{"AND": [{"AND": [...]}]}]}  # 15+ levels deep
```

### Filter Complexity Limiting

The total number of filter clauses is limited to prevent excessively complex queries.
The default limit is 50 clauses.

```python
# This would be rejected (too many clauses):
where = {"AND": [{"field1": {"eq": 1}}, {"field2": {"eq": 2}}, ...]}  # 60+ clauses
```

### Regex Validation

Regex patterns (`regex` and `iregex` operators) are validated for:

1. **Length limits**: Patterns exceeding 500 characters are rejected
2. **Syntax validation**: Invalid regex syntax is rejected
3. **ReDoS protection**: Known dangerous patterns that could cause exponential backtracking
   are rejected by default

Dangerous patterns that are blocked include:
- `(.*)+` - Evil regex with nested quantifiers
- `(.+)+` - Variant of evil regex
- `(.*)*` - Nested quantifiers causing catastrophic backtracking

### Security Configuration

Configure security limits in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        # Filter complexity limits
        "max_filter_depth": 10,      # Maximum nesting depth
        "max_filter_clauses": 50,    # Maximum total filter clauses

        # Regex security
        "max_regex_length": 500,     # Maximum regex pattern length
        "reject_unsafe_regex": True, # Enable ReDoS pattern detection
    }
}
```

When a filter violates security constraints, the query returns an empty result set and
logs a warning. This prevents information leakage about the security limits.

## Performance Considerations

1. **Indexed fields**: Filter on indexed database fields for best performance
2. **Count filters**: `_count` filters use SQL COUNT subqueries; consider indexing foreign keys
3. **Nested depth**: Deep relation filtering (`a_rel.b_rel.c_rel`) may result in complex JOINs
4. **Large `in` lists**: Very large `in` lists may hit database limits

### Filter Generator Caching

Rail Django uses singleton instances for filter generators and applicators, ensuring:

- **Instance reuse**: The same filter generator/applicator instance is reused across all requests for a given schema
- **Bounded cache**: Generated filter input types are cached with automatic eviction when the cache exceeds its configured size (default: 100 entries)
- **Schema isolation**: Multi-schema setups have independent caches per schema

For testing or development, you can clear filter caches:

```python
from rail_django.generators.filter_inputs import clear_filter_caches

# Clear all caches
clear_filter_caches()

# Clear specific schema
clear_filter_caches("my_schema")
```

### Programmatic Access

If you need direct access to filter generators (e.g., for custom schema building):

```python
from rail_django.generators.filter_inputs import (
    get_nested_filter_generator,
    get_nested_filter_applicator,
)

# Get singleton instances
generator = get_nested_filter_generator("default")
applicator = get_nested_filter_applicator("default")

# Generate where input for a model
from myapp.models import Product
where_input = generator.generate_where_input(Product)

# Apply filters to queryset
from django.db.models import Q
filtered_qs = applicator.apply_where_filter(
    Product.objects.all(),
    {"price": {"gte": 100}},
    Product
)
```

## See Also

- [GraphQL API Guide](./graphql.md) - General API documentation
- [GraphQLMeta Reference](../reference/meta.md) - Per-model filter configuration
- [Configuration Reference](../reference/configuration.md) - Settings reference

## Advanced Filter Features

Rail Django supports advanced filtering capabilities that leverage Django ORM's powerful querying features. These are opt-in features that must be enabled in your settings.

### Enabling Advanced Filters

Configure advanced filters in your Django settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        # Window function filters (rank, row_number, etc.)
        "enable_window_filters": True,

        # Subquery and exists filters
        "enable_subquery_filters": True,

        # Conditional aggregation (count/sum with conditions)
        "enable_conditional_aggregation": True,

        # PostgreSQL array field filters
        "enable_array_filters": True,
    }
}
```

---

## Window Function Filters

Window functions allow you to filter records by their ranking, percentile, or row number within partitions. This is powerful for queries like "top N products per category" or "products in the top 10% by price."

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_window_filters": True,
    }
}
```

### Available Window Functions

| Function       | Description                                      |
| -------------- | ------------------------------------------------ |
| `RANK`         | Rank with gaps (ties get same rank)              |
| `DENSE_RANK`   | Rank without gaps (ties get same rank)           |
| `ROW_NUMBER`   | Unique sequential number (no ties)               |
| `PERCENT_RANK` | Relative rank as percentage (0.0 to 1.0)         |

### Basic Usage: Top N Overall

Get the top 3 most expensive products:

```graphql
query {
  products(
    where: {
      _window: {
        function: RANK
        order_by: ["-price"]
        rank: { lte: 3 }
      }
    }
    orderBy: ["-price"]
  ) {
    id
    name
    price
  }
}
```

### Partitioned Ranking: Top N Per Category

Get the most expensive product in each category:

```graphql
query {
  products(
    where: {
      _window: {
        function: ROW_NUMBER
        partition_by: ["category_id"]
        order_by: ["-price"]
        rank: { eq: 1 }
      }
    }
  ) {
    id
    name
    price
    category {
      name
    }
  }
}
```

### Percentile Filtering

Get products in the top 10% by sales:

```graphql
query {
  products(
    where: {
      _window: {
        function: PERCENT_RANK
        order_by: ["-total_sales"]
        percentile: { lte: 0.1 }
      }
    }
  ) {
    id
    name
    totalSales
  }
}
```

### Window Filter Input Reference

```graphql
input WindowFilterInput {
  # Required: Window function to use
  function: WindowFunctionEnum!  # RANK, DENSE_RANK, ROW_NUMBER, PERCENT_RANK

  # Optional: Fields to partition by (creates separate rankings per group)
  partition_by: [String!]

  # Required: Fields to order by within partition (prefix with '-' for descending)
  order_by: [String!]!

  # Filter by rank value (for RANK, DENSE_RANK, ROW_NUMBER)
  rank: IntFilterInput

  # Filter by percentile (for PERCENT_RANK, value between 0.0 and 1.0)
  percentile: FloatFilterInput
}
```

---

## Subquery Filters

Subquery filters allow you to filter parent records based on values from related records, such as "products whose highest-priced order exceeds $100" or "users whose latest login was this month."

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_subquery_filters": True,
    }
}
```

### Basic Usage: Filter by Related Record Value

Get products whose highest-priced order item exceeds $100:

```graphql
query {
  products(
    where: {
      _subquery: {
        relation: "order_items"
        order_by: ["-unit_price"]
        field: "unit_price"
        gt: 100
      }
    }
  ) {
    id
    name
  }
}
```

### Filter by Latest Related Record

Get users whose most recent order was placed this year:

```graphql
query {
  users(
    where: {
      _subquery: {
        relation: "orders"
        order_by: ["-created_at"]
        field: "created_at"
        gte: "2024-01-01"
      }
    }
  ) {
    id
    username
  }
}
```

### Subquery with Additional Filtering

Get products whose highest-priced *completed* order exceeds $50:

```graphql
query {
  products(
    where: {
      _subquery: {
        relation: "order_items"
        order_by: ["-unit_price"]
        filter: "{\"order\": {\"status\": {\"eq\": \"completed\"}}}"
        field: "unit_price"
        gt: 50
      }
    }
  ) {
    id
    name
  }
}
```

### Subquery Filter Input Reference

```graphql
input SubqueryFilterInput {
  # Required: Name of the related field/relation
  relation: String!

  # Order by fields to determine which related record to compare
  # (prefix with '-' for descending)
  order_by: [String!]

  # Additional filter on related records (JSON string)
  filter: JSONString

  # Required: Field from related record to compare
  field: String!

  # Comparison operators
  eq: JSONString      # Equals (value as JSON)
  neq: JSONString     # Not equals
  gt: Float           # Greater than
  gte: Float          # Greater than or equal
  lt: Float           # Less than
  lte: Float          # Less than or equal
  is_null: Boolean    # Is null
}
```

---

## Exists Filters

Exists filters provide a way to filter records based on the existence (or non-existence) of related records, optionally with conditions.

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_subquery_filters": True,  # Exists is part of subquery filters
    }
}
```

### Basic Existence Check

Get products that have at least one order:

```graphql
query {
  products(
    where: {
      _exists: {
        relation: "order_items"
        exists: true
      }
    }
  ) {
    id
    name
  }
}
```

### Non-Existence Check

Get products with no orders:

```graphql
query {
  products(
    where: {
      _exists: {
        relation: "order_items"
        exists: false
      }
    }
  ) {
    id
    name
  }
}
```

### Conditional Existence

Get products that have high-quantity orders (quantity >= 10):

```graphql
query {
  products(
    where: {
      _exists: {
        relation: "order_items"
        filter: "{\"quantity\": {\"gte\": 10}}"
        exists: true
      }
    }
  ) {
    id
    name
  }
}
```

### Exists vs Count Filters

| Use Case                              | Recommended Filter |
| ------------------------------------- | ------------------ |
| "Has any related records"             | `_exists`          |
| "Has no related records"              | `_exists: false`   |
| "Has exactly N related records"       | `_count: { eq: N }` |
| "Has at least N related records"      | `_count: { gte: N }` |
| "Has related records matching X"      | `_exists` with filter |

### Exists Filter Input Reference

```graphql
input ExistsFilterInput {
  # Required: Name of the related field/relation
  relation: String!

  # Additional filter on related records (JSON string)
  filter: JSONString

  # True to check existence, false to check non-existence
  exists: Boolean = true
}
```

---

## Conditional Aggregation Filters

Conditional aggregation filters allow you to filter by aggregates that only count/sum records meeting specific conditions. This is useful for queries like "products with at least 5 high-value orders" or "categories with more than 10 active products."

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_conditional_aggregation": True,
    }
}
```

### Basic Usage: Count with Condition

Get products with at least 2 high-value order items (unit_price >= $50):

```graphql
query {
  products(
    where: {
      order_items_cond_agg: {
        field: "id"
        filter: "{\"unit_price\": {\"gte\": 50}}"
        count: { gte: 2 }
      }
    }
  ) {
    id
    name
  }
}
```

### Sum with Condition

Get categories where the total price of active products exceeds $1000:

```graphql
query {
  categories(
    where: {
      products_cond_agg: {
        field: "price"
        filter: "{\"is_active\": {\"eq\": true}}"
        sum: { gte: 1000 }
      }
    }
  ) {
    id
    name
  }
}
```

### Average with Condition

Get stores where the average rating of verified reviews is at least 4.0:

```graphql
query {
  stores(
    where: {
      reviews_cond_agg: {
        field: "rating"
        filter: "{\"is_verified\": {\"eq\": true}}"
        avg: { gte: 4.0 }
      }
    }
  ) {
    id
    name
  }
}
```

### Conditional Aggregation vs Standard Aggregation

| Filter Type                        | Description                                    |
| ---------------------------------- | ---------------------------------------------- |
| `order_items_agg: { count: ... }` | Count ALL order items                          |
| `order_items_cond_agg: { filter: ..., count: ... }` | Count only order items matching filter |

### Conditional Aggregation Filter Input Reference

```graphql
input ConditionalAggregationFilterInput {
  # Required: Field to aggregate
  field: String!

  # Filter condition on related records (JSON string)
  filter: JSONString

  # Aggregate filters (at least one required)
  sum: FloatFilterInput     # Filter by conditional SUM
  avg: FloatFilterInput     # Filter by conditional AVG
  count: IntFilterInput     # Filter by conditional COUNT
}
```

---

## Array Field Filters (PostgreSQL)

Array field filters provide operations for PostgreSQL `ArrayField` columns, allowing you to filter by array contents, overlap, and length.

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_array_filters": True,
    }
}
```

### Model Setup

```python
from django.contrib.postgres.fields import ArrayField
from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=200)
    tags = ArrayField(models.CharField(max_length=50), default=list)
    categories = ArrayField(models.CharField(max_length=50), blank=True, null=True)
```

### Contains: Array Contains All Values

Get articles that have both "python" and "django" tags:

```graphql
query {
  articles(
    where: {
      tags: {
        contains: ["python", "django"]
      }
    }
  ) {
    id
    title
    tags
  }
}
```

### Overlaps: Array Has Any of the Values

Get articles that have at least one of the specified tags:

```graphql
query {
  articles(
    where: {
      tags: {
        overlaps: ["python", "javascript", "rust"]
      }
    }
  ) {
    id
    title
    tags
  }
}
```

### Contained By: Array is Subset of Values

Get articles whose tags are all within the allowed set:

```graphql
query {
  articles(
    where: {
      tags: {
        contained_by: ["python", "django", "rest", "graphql"]
      }
    }
  ) {
    id
    title
    tags
  }
}
```

### Length: Filter by Array Size

Get articles with at least 3 tags:

```graphql
query {
  articles(
    where: {
      tags: {
        length: { gte: 3 }
      }
    }
  ) {
    id
    title
    tags
  }
}
```

### Null Check

Get articles with no categories:

```graphql
query {
  articles(
    where: {
      categories: {
        is_null: true
      }
    }
  ) {
    id
    title
  }
}
```

### Array Filter Input Reference

```graphql
input ArrayFilterInput {
  # Array must contain all these values
  contains: [String!]

  # Array must be subset of these values
  contained_by: [String!]

  # Array must have at least one of these values
  overlaps: [String!]

  # Filter by array length
  length: IntFilterInput

  # Check if array is null
  is_null: Boolean
}
```

---

## F() Expression Field Comparison Filters

Field comparison filters allow you to compare model fields to each other using Django's F() expressions. This is useful for filtering records where one field's value relates to another field.

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_field_comparison": True,
    }
}
```

### Basic Field Comparison

Find products where price is greater than cost (profitable products):

```graphql
query {
  products(
    where: {
      _compare: {
        left: "price"
        operator: GT
        right: "cost_price"
      }
    }
  ) {
    id
    name
    price
    costPrice
  }
}
```

### Comparison with Multiplier

Find products with at least 50% markup (price >= cost * 1.5):

```graphql
query {
  products(
    where: {
      _compare: {
        left: "price"
        operator: GTE
        right: "cost_price"
        right_multiplier: 1.5
      }
    }
  ) {
    id
    name
    price
    costPrice
  }
}
```

### Comparison with Offset

Find products with at least $30 margin (price > cost + 30):

```graphql
query {
  products(
    where: {
      _compare: {
        left: "price"
        operator: GT
        right: "cost_price"
        right_offset: 30
      }
    }
  ) {
    id
    name
    price
    costPrice
  }
}
```

### Comparison with Multiplier and Offset

Find products where price > cost * 1.2 + 10:

```graphql
query {
  products(
    where: {
      _compare: {
        left: "price"
        operator: GT
        right: "cost_price"
        right_multiplier: 1.2
        right_offset: 10
      }
    }
  ) {
    id
    name
  }
}
```

### Comparison Operators

| Operator | Description |
|----------|-------------|
| `EQ` | Equal |
| `NEQ` | Not equal |
| `GT` | Greater than |
| `GTE` | Greater than or equal |
| `LT` | Less than |
| `LTE` | Less than or equal |

### Field Compare Filter Input Reference

```graphql
enum CompareOperatorEnum {
  EQ
  NEQ
  GT
  GTE
  LT
  LTE
}

input FieldCompareFilterInput {
  # Left-hand field name
  left: String!

  # Comparison operator
  operator: CompareOperatorEnum!

  # Right-hand field name
  right: String!

  # Optional multiplier for right-hand field
  right_multiplier: Float

  # Optional offset to add to right-hand field
  right_offset: Float
}
```

---

## Distinct Count Aggregation Filters

Distinct count filters allow you to filter by the count of unique values in a related field. This is an extension of standard aggregation filters.

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_distinct_count": True,
    }
}
```

### Basic Distinct Count

Find products with at least 3 distinct unit prices in their orders:

```graphql
query {
  products(
    where: {
      order_items_agg: {
        field: "unit_price"
        count_distinct: { gte: 3 }
      }
    }
  ) {
    id
    name
  }
}
```

### Distinct Count vs Regular Count

Regular `count` counts all records, while `count_distinct` counts unique values:

```graphql
query {
  products(
    where: {
      # At least 5 orders with at least 3 different prices
      order_items_agg: {
        field: "unit_price"
        count: { gte: 5 }
        count_distinct: { gte: 3 }
      }
    }
  ) {
    id
    name
  }
}
```

### Aggregation Filter Input with Distinct Count

```graphql
input AggregationFilterInput {
  # Field to aggregate (defaults to "id")
  field: String

  # Standard aggregations
  sum: FloatFilterInput
  avg: FloatFilterInput
  min: FloatFilterInput
  max: FloatFilterInput
  count: IntFilterInput

  # Count of distinct values
  count_distinct: IntFilterInput
}
```

---

## Date Truncation Filters

Date truncation filters allow you to filter date/datetime fields by truncated parts (year, quarter, month, week, day, hour, minute). This uses Django's TruncYear, TruncMonth, etc. functions.

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_date_trunc_filters": True,
    }
}
```

### Filter by Current Period

Find products created this year:

```graphql
query {
  products(
    where: {
      created_at_trunc: {
        precision: YEAR
        this_period: true
      }
    }
  ) {
    id
    name
    createdAt
  }
}
```

### Filter by Last Period

Find orders from last month:

```graphql
query {
  orders(
    where: {
      created_at_trunc: {
        precision: MONTH
        last_period: true
      }
    }
  ) {
    id
    total
    createdAt
  }
}
```

### Filter by Specific Year

Find products created in 2024:

```graphql
query {
  products(
    where: {
      created_at_trunc: {
        precision: YEAR
        year: 2024
      }
    }
  ) {
    id
    name
  }
}
```

### Filter by Year and Month

Find products created in March 2024:

```graphql
query {
  products(
    where: {
      created_at_trunc: {
        precision: MONTH
        year: 2024
        month: 3
      }
    }
  ) {
    id
    name
  }
}
```

### Filter by Quarter

Find products created in Q2 (April-June):

```graphql
query {
  products(
    where: {
      created_at_trunc: {
        precision: QUARTER
        year: 2024
        quarter: 2
      }
    }
  ) {
    id
    name
  }
}
```

### Filter by Week Number

Find products created in week 10 of the year:

```graphql
query {
  products(
    where: {
      created_at_trunc: {
        precision: WEEK
        year: 2024
        week: 10
      }
    }
  ) {
    id
    name
  }
}
```

### Precision Levels

| Precision | Description | Truncates to |
|-----------|-------------|--------------|
| `YEAR` | Year level | Start of year |
| `QUARTER` | Quarter level | Start of quarter |
| `MONTH` | Month level | Start of month |
| `WEEK` | Week level | Start of week (Monday) |
| `DAY` | Day level | Start of day |
| `HOUR` | Hour level | Start of hour |
| `MINUTE` | Minute level | Start of minute |

### Date Truncation Filter Input Reference

```graphql
enum DateTruncPrecisionEnum {
  YEAR
  QUARTER
  MONTH
  WEEK
  DAY
  HOUR
  MINUTE
}

input DateTruncFilterInput {
  # Truncation precision level
  precision: DateTruncPrecisionEnum!

  # ISO date string to match exactly
  value: String

  # Filter by specific year
  year: Int

  # Filter by quarter (1-4)
  quarter: Int

  # Filter by month (1-12)
  month: Int

  # Filter by ISO week number (1-53)
  week: Int

  # Filter by current period (this year/month/week/etc.)
  this_period: Boolean

  # Filter by previous period (last year/month/week/etc.)
  last_period: Boolean
}
```

---

## Extract Date Part Filters

Extract date part filters allow you to filter by specific date/time components without truncation. Unlike truncation which rounds to period boundaries, extraction pulls out specific parts like day of week, hour, quarter, etc. This is useful for recurring patterns like "all orders on Fridays" or "all invoices due on the 15th".

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "filtering_settings": {
        "enable_extract_date_filters": True,
    }
}
```

### Filter by Day of Month

Find invoices due on the 15th of any month:

```graphql
query {
  invoices(
    where: {
      due_date_extract: {
        day: { eq: 15 }
      }
    }
  ) {
    id
    amount
  }
}
```

### Filter by Day of Week

Find orders placed on weekends (Sunday or Saturday):

```graphql
query {
  orders(
    where: {
      created_at_extract: {
        day_of_week: { in: [1, 7] }  # Sunday=1, Saturday=7
      }
    }
  ) {
    id
    total
  }
}
```

Note: Django's `ExtractWeekDay` uses Sunday=1, Monday=2, ..., Saturday=7.

### Filter by Quarter

Find reports from Q4 (October-December) of any year:

```graphql
query {
  reports(
    where: {
      report_date_extract: {
        quarter: { eq: 4 }
      }
    }
  ) {
    id
    title
  }
}
```

### Filter by Business Hours

Find events during business hours (9 AM - 5 PM):

```graphql
query {
  events(
    where: {
      start_time_extract: {
        hour: { gte: 9, lt: 17 }
      }
    }
  ) {
    id
    title
  }
}
```

### Filter by ISO Week Day

Find records created on Monday using ISO weekday (Monday=1, Sunday=7):

```graphql
query {
  tasks(
    where: {
      created_at_extract: {
        iso_week_day: { eq: 1 }  # Monday
      }
    }
  ) {
    id
    title
  }
}
```

### Filter by Week Number

Find records from ISO week 10:

```graphql
query {
  timesheets(
    where: {
      week_start_extract: {
        week: { eq: 10 }
      }
    }
  ) {
    id
    hoursWorked
  }
}
```

### Combined Extraction Filters

Filter by multiple extracted parts (e.g., June of current year):

```graphql
query {
  products(
    where: {
      created_at_extract: {
        year: { eq: 2024 }
        month: { eq: 6 }
      }
    }
  ) {
    id
    name
  }
}
```

### Available Extraction Parts

| Part | Field Name | Range | Description |
|------|------------|-------|-------------|
| Year | `year` | 1-9999 | Calendar year |
| Month | `month` | 1-12 | Month of year |
| Day | `day` | 1-31 | Day of month |
| Quarter | `quarter` | 1-4 | Quarter of year |
| Week | `week` | 1-53 | ISO week number |
| Day of Week | `day_of_week` | 1-7 | Sunday=1 through Saturday=7 |
| Day of Year | `day_of_year` | 1-366 | Day number within year |
| ISO Week Day | `iso_week_day` | 1-7 | Monday=1 through Sunday=7 |
| ISO Year | `iso_year` | 1-9999 | ISO week-numbering year |
| Hour | `hour` | 0-23 | Hour of day (24-hour) |
| Minute | `minute` | 0-59 | Minute of hour |
| Second | `second` | 0-59 | Second of minute |

### Extract Date Filter Input Reference

```graphql
input ExtractDateFilterInput {
  # Filter by year
  year: IntFilterInput

  # Filter by month (1-12)
  month: IntFilterInput

  # Filter by day of month (1-31)
  day: IntFilterInput

  # Filter by quarter (1-4)
  quarter: IntFilterInput

  # Filter by ISO week number (1-53)
  week: IntFilterInput

  # Filter by day of week (Sunday=1, Saturday=7)
  day_of_week: IntFilterInput

  # Filter by day of year (1-366)
  day_of_year: IntFilterInput

  # Filter by ISO week day (Monday=1, Sunday=7)
  iso_week_day: IntFilterInput

  # Filter by ISO week-numbering year
  iso_year: IntFilterInput

  # Filter by hour (0-23)
  hour: IntFilterInput

  # Filter by minute (0-59)
  minute: IntFilterInput

  # Filter by second (0-59)
  second: IntFilterInput
}
```

### Difference Between Truncation and Extraction

| Feature | Date Truncation | Date Extraction |
|---------|-----------------|-----------------|
| Purpose | Round to period boundary | Extract component value |
| Use Case | "Orders in March 2024" | "Orders on any 15th" |
| Result | Date/DateTime | Integer |
| Requires Year | Usually yes | No |

---

## Combining Advanced Filters

Advanced filters can be combined with standard filters and boolean operators:

```graphql
query {
  products(
    where: {
      # Standard filter: price above $100
      price: { gte: 100 }

      # Exists filter: must have orders
      _exists: {
        relation: "order_items"
        exists: true
      }

      # Window filter: in top 10 by sales
      _window: {
        function: RANK
        order_by: ["-total_sales"]
        rank: { lte: 10 }
      }
    }
  ) {
    id
    name
    price
  }
}
```

### With Boolean Operators

```graphql
query {
  products(
    where: {
      AND: [
        { price: { gte: 50 } }
        {
          _exists: {
            relation: "order_items"
            filter: "{\"quantity\": {\"gte\": 5}}"
            exists: true
          }
        }
      ]
      OR: [
        { category_rel: { name: { eq: "Electronics" } } }
        { category_rel: { name: { eq: "Accessories" } } }
      ]
    }
  ) {
    id
    name
  }
}
```

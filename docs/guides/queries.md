# Query Generation

Rail Django automatically generates GraphQL queries from Django models, providing single-object retrieval, list queries with filtering, and paginated queries with metadata.

## Query Types

### Single Object Query

Retrieves a single model instance by ID.

```graphql
query {
  user(id: "123") {
    id
    username
    email
  }
}
```

### List Query

Retrieves a list of model instances with filtering, ordering, and offset/limit pagination.

```graphql
query {
  users(
    where: { is_active: { eq: true } }
    orderBy: ["-created_at"]
    offset: 0
    limit: 10
  ) {
    id
    username
  }
}
```

### Paginated Query

Retrieves paginated results with metadata (total count, page info).

```graphql
query {
  usersPages(
    where: { is_active: { eq: true } }
    orderBy: ["-created_at"]
    page: 1
    perPage: 25
  ) {
    items {
      id
      username
    }
    pageInfo {
      totalCount
      pageCount
      currentPage
      hasNextPage
      hasPreviousPage
    }
  }
}
```

## Query Arguments

### Filtering Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `where` | `ModelWhereInput` | Nested Prisma/Hasura-style filter |
| `presets` | `[String]` | List of filter preset names to apply |
| `savedFilter` | `String` | Name or ID of a saved filter |
| `include` | `[ID]` | IDs to include regardless of filters |
| `quick` | `String` | Quick search across text fields |

### Pagination Arguments

**Offset/Limit (List Queries):**

| Argument | Type | Description |
|----------|------|-------------|
| `offset` | `Int` | Number of records to skip |
| `limit` | `Int` | Number of records to return |

**Page-Based (Paginated Queries):**

| Argument | Type | Description |
|----------|------|-------------|
| `page` | `Int` | Page number (1-based, default: 1) |
| `perPage` | `Int` | Records per page (default: 25) |

### Ordering Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `orderBy` | `[String]` | Fields to order by (prefix with `-` for descending) |
| `distinctOn` | `[String]` | Distinct by fields (PostgreSQL DISTINCT ON) |

## Filter Presets

Define reusable filter configurations in `GraphQLMeta`:

```python
class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class GraphQLMeta:
        filter_presets = {
            "active": {"is_active": {"eq": True}},
            "expensive": {"price": {"gte": 100.00}},
            "on_sale": {
                "AND": [
                    {"is_active": {"eq": True}},
                    {"price": {"lt": 50.00}},
                ]
            },
        }
```

Use presets in queries:

```graphql
query {
  productsPages(presets: ["active", "expensive"]) {
    items { name price }
    pageInfo { totalCount }
  }
}
```

Presets can be combined with `where` filters - they are merged together.

## Saved Filters

Users can save and reuse filter configurations:

```graphql
# Apply a saved filter by name
query {
  productsPages(savedFilter: "my_favorites") {
    items { name }
  }
}

# Apply by ID
query {
  productsPages(savedFilter: "123") {
    items { name }
  }
}
```

Saved filters support access control:
- Users can access their own saved filters
- Shared filters (`is_shared=True`) are accessible to all

## Include IDs

The `include` argument creates a union with filtered results, ensuring specific IDs always appear:

```graphql
query {
  # Returns all expensive products PLUS product ID 5 (even if cheap)
  products(
    where: { price: { gte: 100 } }
    include: ["5"]
  ) {
    id
    name
    price
  }
}
```

## Ordering

### Basic Ordering

```graphql
query {
  users(orderBy: ["last_name", "first_name"]) {
    id name
  }
}
```

### Descending Order

Prefix with `-` for descending:

```graphql
query {
  users(orderBy: ["-created_at"]) {
    id name
  }
}
```

### Count-Based Ordering

Order by relationship counts using `_count` suffix:

```graphql
query {
  # Order authors by number of books
  authors(orderBy: ["-books_count"]) {
    id
    name
    booksCount
  }
}
```

### Property-Based Ordering

Properties (non-database fields) can be used for ordering, but require in-memory sorting:

```python
class Product(models.Model):
    @property
    def display_name(self):
        return f"{self.category} - {self.name}"

    class GraphQLMeta:
        ordering_config = OrderingConfig(
            allowed=["name", "price", "display_name"],
        )
```

> **Note:** Property ordering loads results into memory. Use `max_property_ordering_results` setting to limit.

### DISTINCT ON (PostgreSQL)

For PostgreSQL, use `distinctOn` to get one record per group:

```graphql
query {
  # Get highest-priced product per category
  products(
    distinctOn: ["category_id"]
    orderBy: ["category_id", "-price"]
  ) {
    id
    name
    categoryId
    price
  }
}
```

## Pagination Behavior

### Empty Results

When no results match filters:
- `totalCount`: 0
- `pageCount`: 0
- `currentPage`: 1 (consistent UX)
- `hasNextPage`: false
- `hasPreviousPage`: false

### Page Beyond Range

Requesting a page beyond available pages returns the last valid page:

```graphql
# If only 5 pages exist, page: 100 returns page 5
query {
  usersPages(page: 100, perPage: 10) {
    pageInfo {
      currentPage  # Returns 5
      pageCount    # Returns 5
    }
  }
}
```

## Architecture

Query generation is handled by the following components:

| Component | File | Responsibility |
|-----------|------|----------------|
| `QueryGenerator` | `queries.py` | Main orchestrator |
| `QueryFilterPipeline` | `queries_base.py` | Filter application pipeline |
| `QueryOrderingHelper` | `queries_base.py` | Ordering with annotations |
| `generate_list_query` | `queries_list.py` | List query generation |
| `generate_paginated_query` | `queries_pagination.py` | Paginated query generation |
| `NestedFilterInputGenerator` | `filter_inputs.py` | Where input type generation |
| `NestedFilterApplicator` | `filter_inputs.py` | Where filter application |

### Filter Pipeline

Filters are applied in order:

1. **Saved Filter** - Load and merge if specified
2. **Presets** - Apply and merge preset filters
3. **Include IDs** - Merge include IDs into filter
4. **Where Filter** - Apply main where filter
5. **Basic Filters** - Apply FilterSet filters

### Query Context

The `QueryContext` dataclass holds all state for query processing:

```python
@dataclass
class QueryContext:
    model: Type[models.Model]
    queryset: models.QuerySet
    info: graphene.ResolveInfo
    kwargs: Dict[str, Any]
    graphql_meta: Any
    filter_applicator: Any
    filter_class: Any
    ordering_config: Any
    settings: Any
    schema_name: str = "default"
```

## Configuration

### QueryGeneratorSettings

```python
from rail_django.generators import QueryGeneratorSettings

settings = QueryGeneratorSettings(
    enable_pagination=True,
    enable_ordering=True,
    default_page_size=25,
    max_page_size=100,
    max_property_ordering_results=1000,
    property_ordering_warn_on_cap=True,
)
```

### GraphQLMeta Ordering Config

```python
from rail_django.core.meta import OrderingConfig

class Product(models.Model):
    class GraphQLMeta:
        ordering_config = OrderingConfig(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"],
        )
```

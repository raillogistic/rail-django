# Query Generator

> **Module Path:** `rail_django.generators.queries.generator`

The QueryGenerator creates GraphQL query fields for Django models, including single object retrieval, list queries, pagination, filtering, and ordering.

## Architecture Overview

```
                         QueryGenerator
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   Single Queries        List Queries        Paginated Queries
   product(id: ID)       products(...)       productsPaginated(...)
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ Advanced Filter │
                     │   Generator     │
                     └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  Optimization   │
                     │ select_related  │
                     │ prefetch_related│
                     └─────────────────┘
```

## Class Reference

### QueryGenerator

```python
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator

type_gen = TypeGenerator(schema_name="default")
query_gen = QueryGenerator(type_gen, schema_name="default")

# Generate single object query
product_query = query_gen.generate_single_query(Product)

# Generate list query
products_query = query_gen.generate_list_query(Product)

# Generate paginated query
products_paginated = query_gen.generate_paginated_query(Product)
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type_generator` | `TypeGenerator` | Required | Type generator instance |
| `settings` | `QueryGeneratorSettings` | `None` | Query generation settings |
| `schema_name` | `str` | `"default"` | Schema identifier |

#### Key Properties

| Property | Type | Description |
|----------|------|-------------|
| `type_generator` | `TypeGenerator` | Associated type generator |
| `settings` | `QueryGeneratorSettings` | Query settings |
| `filter_generator` | `AdvancedFilterGenerator` | Filter generation helper |
| `query_optimizer` | `QueryOptimizer` | Query optimization |
| `authorization_manager` | `AuthzManager` | Permission checks |

## Query Types

### Single Object Query

```python
product_query = query_gen.generate_single_query(Product)
```

**Generated GraphQL:**
```graphql
type Query {
  product(id: ID, slug: String, uuid: UUID): Product
}
```

**Features:**
- Primary key lookup (`id`)
- Additional lookup fields (configured)
- Permission enforcement
- Tenant scoping
- Field masking

**Usage:**
```graphql
query {
  product(id: "123") {
    id
    name
    price
  }
}

# Or with alternate lookup
query {
  product(slug: "awesome-product") {
    id
    name
  }
}
```

### List Query

```python
products_query = query_gen.generate_list_query(Product)
```

**Generated GraphQL:**
```graphql
type Query {
  products(
    where: ProductWhereInput
    orderBy: [String]
    limit: Int
    offset: Int
  ): [Product]
}
```

**Features:**
- Advanced filtering (`where`)
- Ordering (`orderBy`)
- Pagination (`limit`, `offset`)
- Permission enforcement
- Tenant scoping
- Query optimization

**Usage:**
```graphql
query {
  products(
    where: { status: { eq: "active" }, price: { gt: 100 } }
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

### Paginated Query

```python
products_paginated = query_gen.generate_paginated_query(Product)
```

**Generated GraphQL:**
```graphql
type Query {
  productsPaginated(
    where: ProductWhereInput
    orderBy: [String]
    page: Int
    pageSize: Int
  ): ProductPaginatedResult
}

type ProductPaginatedResult {
  items: [Product]
  pagination: PaginationInfo
}

type PaginationInfo {
  totalCount: Int!
  totalPages: Int!
  currentPage: Int!
  pageSize: Int!
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
}
```

**Usage:**
```graphql
query {
  productsPaginated(
    where: { category: { name: { eq: "Electronics" } } }
    page: 1
    pageSize: 20
  ) {
    items {
      id
      name
      price
    }
    pagination {
      totalCount
      totalPages
      hasNextPage
    }
  }
}
```

### Grouping Query

```python
products_grouped = query_gen.generate_grouping_query(Product)
```

**Generated GraphQL:**
```graphql
type Query {
  productsGrouped(
    groupBy: [String!]!
    aggregations: [AggregationInput]
    where: ProductWhereInput
    limit: Int
  ): [GroupingBucket]
}

type GroupingBucket {
  keys: JSONScalar
  count: Int!
  aggregations: JSONScalar
}
```

**Usage:**
```graphql
query {
  productsGrouped(
    groupBy: ["status", "category__name"]
    aggregations: [
      { field: "price", function: SUM, alias: "totalValue" }
      { field: "price", function: AVG, alias: "avgPrice" }
    ]
  ) {
    keys
    count
    aggregations
  }
}
```

## Filtering System

### Where Input

The `where` argument accepts a structured filter input:

```graphql
input ProductWhereInput {
  # Logical operators
  AND: [ProductWhereInput]
  OR: [ProductWhereInput]
  NOT: ProductWhereInput

  # Field filters
  id: IDFilter
  name: StringFilter
  price: DecimalFilter
  status: StringFilter
  createdAt: DateTimeFilter
  category: CategoryWhereInput  # Nested relation
}

input StringFilter {
  eq: String
  in: [String]
  isNull: Boolean
  contains: String
  icontains: String
  startsWith: String
  iStartsWith: String
  endsWith: String
  iEndsWith: String
}

input DecimalFilter {
  eq: Decimal
  in: [Decimal]
  gt: Decimal
  gte: Decimal
  lt: Decimal
  lte: Decimal
  between: [Decimal]
}
```

### Filter Examples

**Simple Filter:**
```graphql
query {
  products(where: { status: { eq: "active" } }) {
    id
    name
  }
}
```

**Multiple Conditions (AND):**
```graphql
query {
  products(where: {
    status: { eq: "active" }
    price: { gte: 100, lte: 500 }
  }) {
    id
    name
  }
}
```

**OR Conditions:**
```graphql
query {
  products(where: {
    OR: [
      { status: { eq: "active" } }
      { featured: { eq: true } }
    ]
  }) {
    id
    name
  }
}
```

**Nested Relations:**
```graphql
query {
  products(where: {
    category: {
      name: { icontains: "electronics" }
    }
  }) {
    id
    name
    category {
      name
    }
  }
}
```

**Complex Query:**
```graphql
query {
  products(where: {
    AND: [
      { status: { eq: "active" } }
      { OR: [
        { price: { lt: 100 } }
        { featured: { eq: true } }
      ]}
      { NOT: { category: { name: { eq: "Archived" } } } }
    ]
  }) {
    id
    name
  }
}
```

## Ordering System

### Order By Argument

```graphql
query {
  products(
    orderBy: ["name", "-price", "category__name"]
  ) {
    id
    name
    price
  }
}
```

**Syntax:**
- `"field"` - Ascending order
- `"-field"` - Descending order (prefix with `-`)
- `"relation__field"` - Order by related field

### Ordering Configuration

Via GraphQLMeta:
```python
class Product(models.Model):
    class GraphQLMeta:
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"]
        )
```

### Property Ordering

Ordering by Python properties (slower, use cautiously):

```python
class Product(models.Model):
    @property
    def profit_margin(self):
        return self.price - self.cost

    class GraphQLMeta:
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "profit_margin"],
            allow_property_ordering=True
        )
```

```graphql
query {
  products(orderBy: ["-profit_margin"]) {
    name
    profitMargin
  }
}
```

## Pagination

### Offset Pagination

Default pagination style:

```graphql
query {
  products(offset: 20, limit: 10) {
    id
    name
  }
}
```

### Page-Based Pagination

Using paginated queries:

```graphql
query {
  productsPaginated(page: 3, pageSize: 20) {
    items { id name }
    pagination {
      totalCount
      currentPage
      hasNextPage
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

## Query Optimization

### Automatic Optimization

The generator automatically optimizes queries:

```python
# For this query:
# products { category { name } tags { name } }

# Generated resolver applies:
queryset = Product.objects.all()
queryset = queryset.select_related("category")  # FK
queryset = queryset.prefetch_related("tags")    # M2M
```

### Optimization Settings

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_query_optimization": True,
        "enable_select_related": True,
        "enable_prefetch_related": True,
        "enable_only_fields": True
    }
}
```

## Permission Enforcement

### Model Permissions

```python
# Settings
"query_settings": {
    "require_model_permissions": True,
    "model_permission_codename": "view"
}
```

Requires `app.view_model` permission for queries.

### Operation Guards

Via GraphQLMeta:
```python
class Product(models.Model):
    class GraphQLMeta:
        access = GraphQLMetaConfig.Access(
            operations={
                "list": GraphQLMetaConfig.OperationAccess(
                    roles=["catalog_viewer"],
                    permissions=["store.view_product"]
                )
            }
        )
```

### Field Masking

Sensitive fields are masked based on permissions:

```python
def _apply_field_masks(self, data, info, model):
    """Hide or mask fields based on field-level permissions."""
    # Applied automatically in resolvers
```

## Tenant Scoping

Multi-tenant queries are automatically scoped:

```python
def _apply_tenant_scope(self, queryset, info, model, operation="read"):
    """Apply tenant filtering to queryset."""
    from rail_django.extensions.multitenancy import apply_tenant_queryset
    return apply_tenant_queryset(queryset, info, model, ...)
```

## Settings Reference

### QueryGeneratorSettings

```python
@dataclass
class QueryGeneratorSettings:
    # Filter generation
    generate_filters: bool = True

    # Ordering generation
    generate_ordering: bool = True

    # Pagination generation
    generate_pagination: bool = True
    enable_pagination: bool = True
    enable_ordering: bool = True

    # Relay-style connections
    use_relay: bool = False

    # Page size limits
    default_page_size: int = 20
    max_page_size: int = 100

    # Grouping limits
    max_grouping_buckets: int = 200

    # Property ordering limit
    max_property_ordering_results: int = 2000

    # Additional lookup fields per model
    additional_lookup_fields: dict[str, list[str]] = field(default_factory=dict)

    # Permission requirements
    require_model_permissions: bool = True
    model_permission_codename: str = "view"
```

## Usage Examples

### Basic Query Generation

```python
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator

type_gen = TypeGenerator()
query_gen = QueryGenerator(type_gen)

# Generate all queries for a model
product_single = query_gen.generate_single_query(Product)
product_list = query_gen.generate_list_query(Product)
product_paginated = query_gen.generate_paginated_query(Product)
product_grouped = query_gen.generate_grouping_query(Product)

# Create Query class
Query = type(
    "Query",
    (graphene.ObjectType,),
    {
        "product": product_single,
        "products": product_list,
        "products_paginated": product_paginated,
        "products_grouped": product_grouped
    }
)
```

### Custom Manager

Query from a custom manager:

```python
class PublishedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status="published")

class Article(models.Model):
    objects = models.Manager()
    published = PublishedManager()

# Generate query using custom manager
articles_query = query_gen.generate_list_query(Article, manager_name="published")
```

### Adding Filtering to Custom Query

```python
custom_query = graphene.Field(
    graphene.List(ProductType),
    resolver=custom_resolver
)

# Add filtering support
filtered_query = query_gen.add_filtering_support(custom_query, Product)
```

## Introspection Queries

The generator adds introspection queries:

```python
introspection_queries = query_gen.generate_introspection_queries()
# {"filterSchema": graphene.Field(...)}
```

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

## Internal Methods

### Ordering Utilities

```python
# Normalize ordering specs
normalized = query_gen._normalize_ordering_specs(
    order_by=["name", "-price"],
    ordering_config=meta.ordering
)

# Split into DB and property specs
db_specs, prop_specs = query_gen._split_order_specs(Product, normalized)

# Apply property ordering (in-memory)
sorted_items = query_gen._apply_property_ordering(items, prop_specs)
```

### Permission Utilities

```python
# Check if operation has custom guard
has_guard = query_gen._has_operation_guard(graphql_meta, "list")

# Build permission name
perm = query_gen._build_model_permission_name(Product, "view")
# "store.view_product"

# Enforce permission (raises GraphQLError if denied)
query_gen._enforce_model_permission(info, Product, "list", graphql_meta)
```

## Related Modules

- [Schema Builder](../core/schema-builder.md) - Uses QueryGenerator
- [Type Generator](./type-generator.md) - Provides types
- [Filter Generator](./filter-generator.md) - Advanced filtering
- [GraphQLMeta](../core/graphql-meta.md) - Query configuration
- [RBAC System](../security/rbac.md) - Permission checks

# Rail Django Tutorial: Filtering and Settings

This tutorial guides you through configuring Rail Django and mastering its powerful filtering capabilities. You will learn how to set up the library, configure its behavior, and implement advanced filtering patterns for your GraphQL API.

## 1. Configuration

Rail Django uses a centralized configuration dictionary `RAIL_DJANGO_GRAPHQL` in your Django `settings.py`.

### Basic Setup

Add `rail_django` and its dependencies to your `INSTALLED_APPS`:

```python
# settings.py

INSTALLED_APPS = [
    # ... standard django apps ...
    "graphene_django",
    "django_filters",
    "corsheaders",
    "rail_django",
    "your_app",
]
```

### The `RAIL_DJANGO_GRAPHQL` Setting

This dictionary controls almost every aspect of the library. Here is a recommended starting configuration:

```python
# settings.py

RAIL_DJANGO_GRAPHQL = {
    # General Schema Settings
    "schema_settings": {
        "enable_graphiql": True,        # Enable the interactive browser
        "enable_introspection": True,   # Allow schema introspection
        "authentication_required": False, # Set to True to require auth globally
    },

    # Query Behavior
    "query_settings": {
        "default_page_size": 20,
        "max_page_size": 100,
        "filter_input_style": "nested", # "nested" (Prisma-style) or "flat" (Django-style)
    },

    # Filtering Configuration
    "filtering_settings": {
        "enable_full_text_search": True, # Enable Postgres FTS if available
        "max_filter_depth": 5,           # Limit nested filter depth for security
        "max_filter_clauses": 50,        # Limit total number of filter conditions
    },

    # Security Defaults
    "security_settings": {
        "enable_input_validation": True,
        "input_failure_severity": "high", # "high" raises errors, "low" logs warnings
    }
}
```

## 2. Setting Up Models

To expose a model in your GraphQL API with filtering, you need to define a `GraphQLMeta` class within your Django model.

### Field Visibility and Basic Setup

You can control which fields are exposed, read-only, or write-only using `GraphQLMetaConfig.Fields`.

```python
# your_app/models.py
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    internal_notes = models.TextField() # Should be hidden
    secret_token = models.CharField(max_length=100) # Write-only

    class GraphQLMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            include=["id", "name", "sku", "price"], # Only expose these
            exclude=["internal_notes"],             # Explicitly exclude
            write_only=["secret_token"],            # Only for mutations
        )
```

## 3. Mastering Filtering

Rail Django provides a "nested" filter style (similar to Prisma or Hasura), allowing for intuitive and type-safe queries.

### Basic Scalar Filtering

Filter by standard fields like strings, numbers, and booleans.

```graphql
query {
  products(
    where: {
      name: { icontains: "phone" } # Case-insensitive contains
      price: { gte: 100, lte: 999.99 } # Range: 100 <= price <= 999.99
    }
  ) {
    id
    name
    price
  }
}
```

### Logic Operators (AND, OR, NOT)

Combine conditions for complex logic.

```graphql
query {
  products(
    where: {
      OR: [{ price: { lt: 50 } }, { price: { gt: 1000 } }]
      NOT: { name: { icontains: "deprecated" } }
    }
  ) {
    name
    price
  }
}
```

### Relational Filtering

Filter records based on their related objects.

#### Foreign Key (One-to-Many)

Find products based on their category.

```graphql
query {
  products(where: { categoryRel: { name: { eq: "Electronics" } } }) {
    name
    category {
      name
    }
  }
}
```

#### Reverse Relations (Many-to-One / Many-to-Many)

Use quantifiers: `_some`, `_every`, `_none`.

```graphql
query {
  categories(
    where: {
      # Categories that have at least one active product
      productsSome: { isActive: { eq: true } }
      # Categories where NO product is over $1000
      productsNone: { price: { gt: 1000 } }
    }
  ) {
    name
  }
}
```

### Aggregation Filters

Filter based on aggregates of related data (e.g., "Categories with more than 10 products").

```graphql
query {
  categories(where: { productsAgg: { count: { gt: 10 } } }) {
    name
  }
}
```

## 4. Advanced Filtering & Ordering

### Ordering

Control the sorting behavior of your lists.

```python
class GraphQLMeta(GraphQLMetaConfig):
    ordering = GraphQLMetaConfig.Ordering(
        allowed=["name", "created_at", "price"],
        default=["-created_at"], # Default to newest first
        allow_related=True,      # Allow sorting by related fields (e.g. category__name)
    )
```

Usage:

```graphql
query {
  products(orderBy: ["price", "-createdAt"]) {
    name
  }
}
```

### Computed Filters

Filter by values calculated on the fly using Django Expressions (annotation-based filtering).

```python
from django.db.models import F
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    # ...

    class GraphQLMeta(GraphQLMetaConfig):
        filtering = GraphQLMetaConfig.Filtering(
            computed_filters={
                "profit_margin": {
                    "expression": F("price") - F("cost"),
                    "filter_type": "decimal",
                    "description": "Profit (Price - Cost)"
                }
            }
        )
```

Usage:

```graphql
query {
  products(where: { profitMargin: { gt: 50.0 } }) {
    name
    price
  }
}
```

### Custom Filters

For complex logic that cannot be expressed with standard lookups, use a custom static method.

```python
class GraphQLMeta(GraphQLMetaConfig):
    filtering = GraphQLMetaConfig.Filtering(
        custom={
            "is_best_seller": "filter_best_seller"
        }
    )

    @staticmethod
    def filter_best_seller(queryset, name, value):
        if value is True:
            return queryset.filter(sales_count__gt=1000)
        return queryset
```

Usage:

```graphql
query {
  products(where: { isBestSeller: true }) {
    name
  }
}
```

### Filter Presets

Define reusable filters in your model's `GraphQLMeta`. This is great for common queries like "active users" or "recent orders".

```python
class GraphQLMeta(GraphQLMetaConfig):
    filtering = GraphQLMetaConfig.Filtering(
        presets={
            "on_sale": {
                "price": {"lt": 50},
                "is_active": {"eq": True}
            }
        }
    )
```

Usage in GraphQL:

```graphql
query {
  products(presets: ["on_sale"]) {
    name
    price
  }
}
```

### Full-Text Search

If you enabled `enable_full_text_search` in settings (requires Postgres), you can perform advanced text searches.

```graphql
query {
  products(
    where: {
      search: {
        query: "wireless bluetooth"
        fields: ["name", "description"]
        searchType: WEBSEARCH
      }
    }
  ) {
    name
  }
}
```

## 5. Alternative Configuration: YAML

Instead of defining `GraphQLMeta` inside your models, you can use a `meta.yaml` file in your app directory. This is useful for keeping models clean or configuring third-party models.

```yaml
# my_app/meta.yaml
models:
  my_app.Product:
    fields:
      include: [id, name, price]
    filtering:
      quick: [name]
      fields:
        status:
          lookups: [eq, in]
```

## 6. Security & Limits

To prevent Denial of Service (DoS) attacks via complex queries, you should configure limits in `RAIL_DJANGO_GRAPHQL["filtering_settings"]`.

- **`max_filter_depth`**: Prevents deeply nested queries (e.g., `user.posts.comments.author.posts...`). Default is usually sufficient, but tune it to your schema needs.
- **`max_filter_clauses`**: Limits the total number of conditions in a single query.
- **`max_regex_length`**: Restricts the length of regex patterns to prevent ReDoS (Regular Expression Denial of Service).

```python
# settings.py example
"filtering_settings": {
    "max_filter_depth": 4,
    "max_filter_clauses": 30,
    "reject_unsafe_regex": True,
}
```

## Summary

1.  **Configure** `RAIL_DJANGO_GRAPHQL` in `settings.py`.
2.  **Define** `GraphQLMeta` on your models (or use `meta.yaml`) to control fields, ordering, and advanced filters.
3.  **Query** using the `where` argument with nested fields, logic operators, and aggregations.
4.  **Secure** your API by setting depth and complexity limits.

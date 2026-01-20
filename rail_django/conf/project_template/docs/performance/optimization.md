# Query Optimization

## Overview

Rail Django includes automatic optimizations to avoid the N+1 problem and improve GraphQL query performance. This guide covers built-in mechanisms and advanced configurations.

---

## Table of Contents

1. [Automatic Optimization](#automatic-optimization)
2. [Configuration](#configuration)
3. [DataLoader](#dataloader)
4. [Complexity Limits](#complexity-limits)
5. [Profiling and Debugging](#profiling-and-debugging)
6. [Best Practices](#best-practices)

---

## Automatic Optimization

### The N+1 Problem

Without optimization, a GraphQL query can generate hundreds of SQL queries:

```graphql
# This naive query would generate 1 + N queries
query {
  products(limit: 100) {
    name
    category {
      name
    } # 100 additional queries!
  }
}
```

### Rail Django Solution

The framework analyzes requested fields and automatically injects optimizations:

```python
# Rail Django automatically generates:
Product.objects.select_related("category").only("id", "name", "category__name")
```

### Optimization Mechanisms

| Mechanism          | Use Case               | Result           |
| ------------------ | ---------------------- | ---------------- |
| `select_related`   | ForeignKey, OneToOne   | SQL JOIN         |
| `prefetch_related` | ManyToMany, reverse FK | Batch query      |
| `only()`           | All fields             | Column selection |
| `defer()`          | Large fields           | Column exclusion |

---

## Configuration

### Performance Settings

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        # ─── QuerySet Optimization ───
        "enable_query_optimization": True,
        "enable_select_related": True,
        "enable_prefetch_related": True,
        "enable_only_fields": True,
        "enable_defer_fields": False,  # Disabled by default

        # ─── DataLoader ───
        "enable_dataloader": True,
        "dataloader_batch_size": 100,

        # ─── Limits ───
        "max_query_depth": 10,
        "max_query_complexity": 1000,

        # ─── Cost Analysis ───
        "enable_query_cost_analysis": False,

        # ─── Timeout ───
        "query_timeout": 30,
    },
}
```

### Per-Model Disable

```python
class LargeReport(models.Model):
    class GraphQLMeta:
        # Disable auto optimization for this model
        enable_optimization = False

        # Or customize
        select_related = ["user"]
        prefetch_related = ["items"]
        only_fields = ["id", "title", "status"]
```

---

## DataLoader

### How It Works

DataLoader solves the N+1 problem for cases where `select_related` isn't sufficient:

```python
# Without DataLoader: N queries for N objects
for order in orders:
    customer = order.customer  # Query per order

# With DataLoader: 1 batch query
customers = Customer.objects.filter(id__in=[o.customer_id for o in orders])
```

### Activation

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_dataloader": True,
        "dataloader_batch_size": 100,
    },
}
```

### Use Cases

DataLoader is particularly useful for:

- Relationships with complex conditions
- Computed properties accessing the DB
- Polymorphic relationships
- External service calls

### Custom DataLoader

```python
from graphene import ObjectType, Field
from promise import Promise
from promise.dataloader import DataLoader

class CustomerLoader(DataLoader):
    """
    Custom DataLoader for customers.
    """
    def batch_load_fn(self, customer_ids):
        customers = Customer.objects.filter(id__in=customer_ids)
        customer_map = {c.id: c for c in customers}
        return Promise.resolve([
            customer_map.get(cid) for cid in customer_ids
        ])

class OrderType(ObjectType):
    customer = Field(CustomerType)

    def resolve_customer(self, info):
        # Use loader from context
        return info.context.loaders.customer.load(self.customer_id)
```

---

## Complexity Limits

### Query Depth

Limits relationship nesting:

```python
"max_query_depth": 10
```

```graphql
# Depth 4 - OK
query {
  orders {
    customer {
      company {
        address { city }
      }
    }
  }
}

# Depth > 10 - Rejected
query {
  orders {
    customer {
      orders {
        customer {
          # ... too deep
        }
      }
    }
  }
}
```

### Query Complexity

Each field has a calculated cost:

```python
"max_query_complexity": 1000
```

| Field Type     | Default Cost   |
| -------------- | -------------- |
| Scalar         | 1              |
| Relation (FK)  | 5              |
| List           | 10 × limit     |
| Paginated List | 10 × page_size |

### Cost Configuration

```python
class Order(models.Model):
    class GraphQLMeta:
        field_costs = {
            "items": 5,           # Relation costs 5
            "total_calculated": 2, # Computed property costs 2
        }
        max_complexity = 500      # Model-specific limit
```

### Response with Complexity

```json
{
  "data": { ... },
  "extensions": {
    "complexity": {
      "cost": 142,
      "limit": 1000,
      "depth": 4,
      "maxDepth": 10
    }
  }
}
```

---

## Profiling and Debugging

### Performance Middleware

```python
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "enable_performance_middleware": True,
        "log_performance": True,
        "performance_threshold_ms": 1000,  # Alert if > 1s
    },
}
```

### Performance Headers

Enable headers for debugging:

```python
# Environment
GRAPHQL_PERFORMANCE_HEADERS = True
```

```http
X-GraphQL-Duration: 45ms
X-GraphQL-SQL-Queries: 3
X-GraphQL-Complexity: 142
```

### Django Debug Toolbar

In development, use the toolbar to analyze queries:

```python
# settings/dev.py
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
```

### SQL Logging

```python
# settings/dev.py
LOGGING = {
    "version": 1,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "django.db.backends": {
            "level": "DEBUG",
            "handlers": ["console"],
        },
    },
}
```

### Query Explain

Analyze SQL execution plans:

```python
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("EXPLAIN ANALYZE SELECT ...")
    print(cursor.fetchall())
```

---

## Best Practices

### 1. Indexing

```python
class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, db_index=True)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]
```

### 2. Avoid N+1 Properties

```python
# Bad: N+1 in a property
@property
def orderCount(self):
    return self.orders.count()  # Query on each access!

# Good: Annotation in the query
queryset = Customer.objects.annotate(
    orderCount=Count("orders")
)
```

### 3. Limit Lists

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "default_page_size": 20,
        "max_page_size": 100,  # Max 100 items
    },
}
```

### 4. Use only() for Large Fields

```python
class Document(models.Model):
    content = models.TextField()  # Potentially large

    class GraphQLMeta:
        defer_fields = ["content"]  # Defer loading
```

### 5. Cache Expensive Calculations

```python
from django.core.cache import cache

class Dashboard:
    @property
    def expensive_stats(self):
        cache_key = f"dashboard_stats_{self.id}"
        stats = cache.get(cache_key)

        if stats is None:
            stats = self._calculate_stats()
            cache.set(cache_key, stats, timeout=300)

        return stats
```

### 6. Continuous Monitoring

```python
# Alert on slow queries
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "performance_threshold_ms": 500,
    },
    "monitoring_settings": {
        "enable_metrics": True,
        "metrics_backend": "prometheus",
    },
}
```

---

## See Also

- [Rate Limiting](./rate-limiting.md) - Request rate limiting
- [Configuration](../graphql/configuration.md) - All settings
- [Production Deployment](../deployment/production.md) - Server optimizations

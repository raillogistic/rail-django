# Performance & Optimization

Rail Django is "Fast by Default". It includes several layers of optimization to ensure your GraphQL API scales.

## 1. N+1 Problem Solved

The N+1 problem is the most common performance killer in GraphQL. Rail Django solves this automatically.

### Automatic Optimization
The framework analyzes the incoming GraphQL query selection set.
*   For `ForeignKey` fields requested, it adds `select_related`.
*   For `ManyTo` fields requested, it adds `prefetch_related`.

You usually do **not** need to manually optimize your querysets.

### Configuration
```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_select_related": True,
        "enable_prefetch_related": True,
        "enable_n_plus_one_detection": True, # Warns if something was missed
    }
}
```

## 2. Query Complexity & Depth Limiting

To prevent DoS attacks via complex queries, you can enforce limits.

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "max_query_depth": 10,       # Max nesting levels
        "max_query_complexity": 1000 # Max calculated complexity score
    }
}
```

## 3. DataLoaders

For complex custom resolvers that cannot be optimized via Django ORM (e.g. calling external APIs), Rail Django provides a `DataLoader` integration.

```python
from rail_django.core.performance import get_loader

def resolve_external_data(root, info):
    loader = get_loader(info, MyCustomLoader)
    return loader.load(root.id)
```

## 4. Query Caching

You can enable short-lived caching for queries.

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_query_caching": True,
        "query_cache_timeout": 60, # seconds
    }
}
```

## 5. Only/Defer Fields

Rail Django respects the `enable_only_fields` setting. It attempts to fetch *only* the columns requested in the GraphQL query from the database, reducing memory usage for wide tables.

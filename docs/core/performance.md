# Performance & Optimization

Rail Django is designed to be "Fast by Default". It includes multiple layers of optimization to ensure your GraphQL API remains performant even as your data grows.

## Solving the N+1 Problem

The N+1 query problem is the most common performance issue in GraphQL. Rail Django solves this automatically using several strategies.

### 1. Automatic ORM Optimization
The framework analyzes the GraphQL selection set and automatically applies optimizations to the Django QuerySet:
- **`select_related`**: Automatically added for requested `ForeignKey` and `OneToOne` fields.
- **`prefetch_related`**: Automatically added for requested many-to-many and reverse relationships.
- **`only()` / `defer()`**: The framework fetches only the columns requested in the GraphQL query, reducing database memory usage.

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_query_optimization": True,
        "enable_select_related": True,
        "enable_prefetch_related": True,
        "enable_only_fields": True,
    }
}
```

### 2. DataLoaders
For complex custom resolvers or cases where standard ORM optimization isn't enough, Rail Django provides built-in `DataLoader` support to batch and cache requests.

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_dataloader": True,
        "dataloader_batch_size": 100,
    }
}
```

## Query Protection

To prevent malicious or accidental performance degradation, Rail Django allows you to set strict limits on query complexity.

### Depth Limiting
Restricts how deep a query can nest relationships.
```python
"max_query_depth": 10
```

### Complexity Scoring
Assigns a "cost" to each field and rejects queries that exceed a total complexity threshold.
```python
"max_query_complexity": 1000
```

## Rate Limiting

Protect your API from abuse by limiting the number of requests per user or IP address.

### Configuration
```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_rate_limiting": True,
        "rate_limit_requests_per_minute": 60,
    }
}
```

You can define different limits for different contexts (e.g., stricter limits for login, more generous for premium users).

## Caching Strategies

### Query Caching
Cache the results of entire GraphQL queries for a short duration.
```python
"enable_query_caching": True,
"query_cache_timeout": 60 # seconds
```

### Field Caching
Use Django's cache framework within specific resolvers for expensive calculations.

## Monitoring & Profiling

### Performance Headers
Enable headers to see how long queries take and how many SQL queries were executed:
```http
X-GraphQL-Duration: 45ms
X-GraphQL-SQL-Queries: 3
```

### Performance Middleware
Log queries that exceed a certain time threshold:
```python
"performance_threshold_ms": 1000 # Log queries slower than 1s
```

## Best Practices

1. **Database Indexing**: Ensure all fields used in filters (`where`) or ordering are properly indexed in your database.
2. **Limit List Sizes**: Always use pagination or the `limit` argument for list fields to avoid fetching thousands of records at once.
3. **Avoid Heavy Properties**: Be careful with `@property` methods that perform database queries, as they bypass the automatic optimization layer. Use annotations instead.
4. **Use Stored Procedures/Views**: For extremely complex analytical queries, use database views and map them to Django models.

## See Also

- [Observability](../extensions/observability.md)
- [Reporting & BI](../extensions/reporting.md)
- [Audit Logging](../extensions/audit-logging.md)

# Troubleshooting Guide

This guide covers common issues, error messages, and "gotchas" you might encounter when developing with Rail Django.

## Common Errors

### CircularReferenceError

**Message**: `Circular reference detected in nested data for {model_name}. Path: {path}`

**Cause**: This occurs during nested mutation operations (for example, creating a user and their profile simultaneously) when the data structure creates a cycle (User -> Profile -> User).

**Solution**:
- Break the cycle by using ID references for one side of the relationship instead of nesting full objects.
- Use the `connect` operation to link existing objects rather than creating new ones inline.

### Query Complexity Exceeded

**Message**: `Query complexity {x} exceeds maximum allowed complexity {y}`

**Cause**: The query is too deep or requests too many fields, violating the security limits configured in `RAIL_DJANGO_GRAPHQL['security']`.

**Solution**:
- Simplify the query on the client side.
- Increase `max_query_complexity` or `max_query_depth` in your settings if the query is legitimate.

### TenantAccessError

**Message**: `Tenant access denied for {operation} on {model_name}`

**Cause**: The multi-tenancy middleware has detected an attempt to access or modify data belonging to a different tenant.

**Solution**:
- Verify that the request includes the correct tenant identifier (for example, via headers or subdomain).
- Check that the `TenantMiddleware` is installed and correctly configured.

## "Missing" Data

### Fields Not Appearing in Schema

If a field exists on your Django model but isn't showing up in the GraphQL schema:

1.  **Check `GraphQLMeta`**: Ensure the field isn't listed in `exclude_fields` or that `fields` isn't set to a restricted list.
2.  **CamelCase**: Remember that `auto_camelcase` is enabled by default. `first_name` in Django becomes `firstName` in GraphQL.
3.  **Permissions**: If you have `field_permissions` configured, the field might be hidden from your user role.

### Fields returning `null` or `***HIDDEN***`

The `FieldPermissionMiddleware` may redact data based on security rules.

- `***HIDDEN***`: The field is masked.
- `pa***wd`: The field is redacted.
- `null`: The field permission level is `HIDDEN` for the current user.

**Debugging**: Check your logs for `Field permission rule registered for {key}` to see what rules are active.

## Performance Issues (N+1)

Rail Django uses `QueryOptimizer` to automatically inject `select_related` and `prefetch_related`. However, N+1 issues can still occur.

### Causes
1.  **Custom Resolvers**: If you access related objects inside a custom resolver method, the optimizer cannot see this access.
    *   **Fix**: Use `optimizer.annotate` or manually prefetch data in the parent resolver.
2.  **Deferred Fields**: Large `TextField`s are deferred by default. Accessing them later triggers a query.
3.  **Optimization Disabled**: Ensure `enable_query_optimization` is `True` in `performance_settings`.

## Debugging Tips

### Enable Detailed Errors

In development, enable detailed errors to see Python tracebacks in the GraphQL response:

```python
# settings.py
RAIL_DJANGO_GRAPHQL = {
    "debug": True,  # Enables detailed_errors and include_stack_trace
    # ...
}
```

### Logging

Set the log level for `rail_django` to `DEBUG` to see detailed information about schema generation, permission registration, and query optimization.

```python
LOGGING = {
    'loggers': {
        'rail_django': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
    },
    # ...
}
```

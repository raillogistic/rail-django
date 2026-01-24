# Configuration Tutorial

This tutorial explains how to customize Rail Django using the central configuration system.

## The Configuration Dictionary

All Rail Django settings are defined within the `RAIL_DJANGO_GRAPHQL` dictionary in your `settings.py`.

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "auto_camelcase": True,
        "enable_introspection": True,
    },
    "query_settings": {
        "default_page_size": 20,
    },
    # ... other sections
}
```

## Common Customizations

### 1. Naming Conventions
By default, Rail Django converts `snake_case` Django fields to `camelCase` GraphQL fields. You can disable this if preferred:

```python
"schema_settings": {
    "auto_camelcase": False,
}
```

### 2. Disabling Auto-Discovery
If you want to explicitly register every model rather than having the framework scan your apps:

```python
"schema_settings": {
    "discover_models": False,
}
```

### 3. Adjusting Pagination
Change the default and maximum page sizes:

```python
"query_settings": {
    "default_page_size": 50,
    "max_page_size": 500,
}
```

## Environment Overrides

We recommend using environment variables for sensitive settings like signing secrets.

```python
import os

RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": {
        "signing_secret": os.environ.get("WEBHOOK_SECRET"),
    },
}
```

## Per-Schema Configuration

If your project has multiple schemas (e.g., Public API vs Admin API), you can define them in `RAIL_DJANGO_GRAPHQL_SCHEMAS`.

```python
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "admin": {
        "schema_settings": {
            "authentication_required": True,
            "enable_introspection": True,
        }
    },
    "public": {
        "schema_settings": {
            "authentication_required": False,
            "enable_introspection": False,
        }
    }
}
```

## Next Steps

- [Complete Configuration Reference](../core/configuration.md)
- [Performance Optimization Guide](../core/performance.md)

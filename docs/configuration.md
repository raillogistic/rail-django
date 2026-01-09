# Configuration Guide

Rail Django reads configuration from three sources, in this order:

1. `RAIL_DJANGO_GRAPHQL_SCHEMAS[<schema_name>]`
2. `RAIL_DJANGO_GRAPHQL`
3. `rail_django.defaults.LIBRARY_DEFAULTS`

## Minimal settings

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_graphiql": True,
        "enable_introspection": True,
        "authentication_required": False,
        "auto_camelcase": False,
    },
    "query_settings": {
        "default_page_size": 20,
        "max_page_size": 100,
        "additional_lookup_fields": {},
    },
    "mutation_settings": {
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_bulk_operations": False,
        "enable_nested_relations": True,
    },
    "type_generation_settings": {
        "exclude_fields": {},
        "include_fields": None,
        "auto_camelcase": False,
    },
    "performance_settings": {
        "enable_query_optimization": True,
        "enable_select_related": True,
        "enable_prefetch_related": True,
        "max_query_depth": 10,
        "max_query_complexity": 1000,
    },
    "security_settings": {
        "enable_authentication": True,
        "enable_authorization": True,
        "enable_rate_limiting": False,
        "rate_limit_requests_per_minute": 60,
        "rate_limit_requests_per_hour": 1000,
        "enable_input_validation": True,
    },
    "middleware_settings": {
        "enable_query_complexity_middleware": True,
        "performance_threshold_ms": 1000,
    },
}
```

## Schema-specific overrides

```python
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "default": {
        "schema_settings": {
            "enable_graphiql": True,
            "enable_introspection": True,
        },
        "performance_settings": {
            "max_query_depth": 8,
        },
    },
    "admin": {
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": False,
        },
    },
}
```

## Graphene settings

Rail Django uses Graphene-Django. You can keep standard `GRAPHENE` settings:

```python
GRAPHENE = {
    "SCHEMA": "rail_django.schema.schema",
    "CAMELCASE_ERRORS": False,
    "ATOMIC_MUTATIONS": True,
}
```

## JWT settings

JWT is used by the auth extension and middleware:

```python
JWT_SECRET_KEY = "<secret>"  # Defaults to Django SECRET_KEY
JWT_ACCESS_TOKEN_LIFETIME = 3600
JWT_REFRESH_TOKEN_LIFETIME = 86400
JWT_AUTH_COOKIE = "jwt"
JWT_REFRESH_COOKIE = "refresh_token"
JWT_ALLOW_COOKIE_AUTH = True
JWT_ENFORCE_CSRF = True  # Require CSRF token for cookie-based auth on unsafe methods
CSRF_COOKIE_NAME = "csrftoken"
```

## Performance and monitoring settings

```python
GRAPHQL_PERFORMANCE_ENABLED = False
GRAPHQL_SLOW_QUERY_THRESHOLD = 1.0
GRAPHQL_COMPLEXITY_THRESHOLD = 100
GRAPHQL_MEMORY_THRESHOLD = 100.0
GRAPHQL_PERFORMANCE_HEADERS = False
```

## CORS and CSRF

```python
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = ["https://example.com"]
```

## Schema API settings

The schema management REST endpoints require JWT access tokens and admin
permissions. You can tune the API behavior with:

```python
GRAPHQL_SCHEMA_API_REQUIRED_PERMISSIONS = ["rail_django.manage_schema"]
GRAPHQL_SCHEMA_API_RATE_LIMIT = {
    "enable": True,
    "window_seconds": 60,
    "max_requests": 60,
}
GRAPHQL_SCHEMA_API_CORS_ENABLED = True
GRAPHQL_SCHEMA_API_CORS_ALLOWED_ORIGINS = ["https://admin.example.com"]
```

## Export settings

Export settings can be defined under `RAIL_DJANGO_EXPORT` (preferred) or
`RAIL_DJANGO_GRAPHQL["export_settings"]`.

```python
RAIL_DJANGO_EXPORT = {
    "max_rows": 5000,
    "stream_csv": True,
    "csv_chunk_size": 1000,
    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30,
    },
    "allowed_models": ["blog.Post", "auth.User"],
    "allowed_fields": {
        "blog.Post": ["id", "title", "author.username", "created_at"],
    },
    "require_model_permissions": True,
    "require_field_permissions": True,
    "required_permissions": ["blog.export_post"],
}
```

## SettingsProxy internals

`rail_django.config_proxy.SettingsProxy` exposes dot-notation reads with caching.
Example:

```python
from rail_django.config_proxy import get_setting

max_depth = get_setting("performance_settings.max_query_depth", 10)
```

## Notes

- `schema_settings.auto_camelcase` controls GraphQL field naming.
- `schema_settings.enable_introspection` and `schema_settings.enable_graphiql`
  should be disabled in production.
- Caching has been removed from this codebase; cache-related settings are ignored.

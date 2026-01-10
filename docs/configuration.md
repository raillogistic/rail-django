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
        "enable_input_validation": True,
        "input_allow_html": False,
        "input_failure_severity": "high",
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

## Input validation settings

Input validation uses a unified sanitizer with allowlisted HTML and pattern
detection. Configure it under `security_settings`:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_input_validation": True,
        "enable_sql_injection_protection": True,
        "enable_xss_protection": True,
        "input_allow_html": False,
        "input_allowed_html_tags": ["p", "br", "strong", "em", "u", "ul", "li"],
        "input_allowed_html_attributes": {"*": ["class"], "a": ["href", "title"]},
        "input_max_string_length": 10000,
        "input_truncate_long_strings": False,
        "input_failure_severity": "high",
        "input_pattern_scan_limit": 10000,
    }
}
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
GRAPHQL_SCHEMA_API_CORS_ENABLED = True
GRAPHQL_SCHEMA_API_CORS_ALLOWED_ORIGINS = ["https://admin.example.com"]
```

Rate limiting for these endpoints is configured under
`RAIL_DJANGO_RATE_LIMITING["contexts"]["schema_api"]` (legacy
`GRAPHQL_SCHEMA_API_RATE_LIMIT` is still supported when the central config is
unset).

## Rate limiting

Rate limiting is configured via the centralized limiter:

```python
RAIL_DJANGO_RATE_LIMITING = {
    "enabled": True,
    "contexts": {
        "graphql": {
            "enabled": True,
            "rules": [
                {"name": "user_minute", "scope": "user_or_ip", "limit": 600, "window_seconds": 60},
                {"name": "user_hour", "scope": "user_or_ip", "limit": 36000, "window_seconds": 3600},
                {"name": "ip_hour_backstop", "scope": "ip", "limit": 500000, "window_seconds": 3600},
            ],
        },
        "graphql_login": {
            "enabled": True,
            "rules": [
                {"name": "login_ip", "scope": "ip", "limit": 60, "window_seconds": 900},
            ],
        },
        "schema_api": {
            "enabled": True,
            "rules": [
                {"name": "schema_api_minute", "scope": "user_or_ip", "limit": 120, "window_seconds": 60},
                {"name": "schema_api_hour", "scope": "user_or_ip", "limit": 2000, "window_seconds": 3600},
            ],
        },
    },
}
```

Optional schema overrides can be provided with `RAIL_DJANGO_RATE_LIMITING_SCHEMAS`:

```python
RAIL_DJANGO_RATE_LIMITING_SCHEMAS = {
    "default": {
        "contexts": {
            "graphql": {
                "rules": [
                    {"name": "user_minute", "scope": "user_or_ip", "limit": 300, "window_seconds": 60},
                ]
            }
        }
    }
}
```

Legacy keys are still supported when `RAIL_DJANGO_RATE_LIMITING` is unset:

- `RAIL_DJANGO_GRAPHQL["security_settings"].enable_rate_limiting`
- `RAIL_DJANGO_GRAPHQL["security_settings"].rate_limit_requests_per_minute`
- `RAIL_DJANGO_GRAPHQL["security_settings"].rate_limit_requests_per_hour`
- `GRAPHQL_REQUESTS_LIMIT` / `GRAPHQL_REQUESTS_WINDOW`
- `AUTH_LOGIN_ATTEMPTS_LIMIT` / `AUTH_LOGIN_ATTEMPTS_WINDOW`
- `GRAPHQL_SCHEMA_API_RATE_LIMIT`

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
- Caching helpers were removed, but rate limiting uses Django cache; configure
  `CACHES` with a shared backend in production.

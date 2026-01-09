# Security Guide

This document explains security features and how to configure them.

## Authentication

Rail Django supports JWT authentication. Tokens can be passed via the
`Authorization: Bearer <jwt>` header or via cookies if enabled.

Key settings:

```python
JWT_SECRET_KEY = "<secret>"  # defaults to SECRET_KEY
JWT_ACCESS_TOKEN_LIFETIME = 3600
JWT_REFRESH_TOKEN_LIFETIME = 86400
JWT_AUTH_COOKIE = "jwt"
JWT_REFRESH_COOKIE = "refresh_token"
JWT_ALLOW_COOKIE_AUTH = True
JWT_ENFORCE_CSRF = True
CSRF_COOKIE_NAME = "csrftoken"
```

Auth mutations (if enabled): `login`, `refresh_token`, `logout`, `register`.

## Authorization

Authorization uses a hybrid RBAC system:

- Role definitions live in code (`rail_django.security.rbac.RoleManager`).
- Assignments use Django `Group` records.
- The permission manager also checks GraphQLMeta guards (per model).

Use GraphQLMeta to guard operations per model and to hide fields.

## Field permissions

`rail_django.security.field_permissions` can hide or mask sensitive fields based
on roles, permissions, and ownership. Sensitive names like `password` or `token`
are masked by default.

## Input validation

`rail_django.security.input_validation` sanitizes string inputs and detects
common XSS patterns. You can also wrap resolvers with `@validate_input`.

## Rate limiting

There are two levels:

- Django middleware: `GraphQLRateLimitMiddleware` for IP-based limits
- Graphene middleware: `GraphQLSecurityMiddleware` for per-field limits

Rate limiting should be backed by shared cache/Redis in production. In-memory
limits only apply per process.

The built-in rate limiters now use Django cache by default, so make sure
`CACHES` is configured for a shared backend in production.

## Introspection and GraphiQL

Production should disable introspection and GraphiQL:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_introspection": False,
        "enable_graphiql": False,
    }
}
```

## CORS and CSRF

The library uses `django-cors-headers` when configured. Do not leave
`CORS_ALLOW_ALL_ORIGINS = True` in production. If you use cookie auth, do not
`csrf_exempt` sensitive endpoints. Cookie-based JWT auth enforces CSRF by
default outside DEBUG (`JWT_ENFORCE_CSRF`).

## Audit logging

Audit events are emitted by `rail_django.extensions.audit`. Configure:

```python
GRAPHQL_ENABLE_AUDIT_LOGGING = True
AUDIT_STORE_IN_DATABASE = True
AUDIT_STORE_IN_FILE = True
AUDIT_WEBHOOK_URL = None
```

## Recommended Django security settings

See `rail_django.security_config.SecurityConfig.get_recommended_django_settings()`
for a hardened baseline (HSTS, secure cookies, strict CSRF).

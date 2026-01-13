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

Refresh tokens can be rotated and protected against reuse:

```python
JWT_ROTATE_REFRESH_TOKENS = True
JWT_REFRESH_REUSE_DETECTION = True
JWT_REFRESH_TOKEN_CACHE = "default"
```

Cookie policies can be set globally (`JWT_COOKIE_*`) or per cookie
(`JWT_AUTH_COOKIE_*`, `JWT_REFRESH_COOKIE_*`).

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

`rail_django.security.input_validation` provides a unified validation pipeline
that sanitizes strings, applies allowlisted HTML rules, and flags high-risk
patterns. You can wrap resolvers with `@validate_input` or use
`InputValidator.validate_payload` directly.

Recommended configuration:

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

`input_failure_severity` accepts `low`, `medium`, `high`, or `critical` to control
which issues fail the request.

## Persisted queries

Persisted queries can be enforced with an allowlist to reduce the attack
surface for arbitrary query text:

```python
RAIL_DJANGO_GRAPHQL = {
    "persisted_query_settings": {
        "enabled": True,
        "enforce_allowlist": True,
        "allowlist": {
            "<sha256>": "query { me { id } }",
        },
    }
}
```

When `enforce_allowlist` is false, allowlist entries are treated as pre-registered
queries and unknown hashes return `PERSISTED_QUERY_NOT_FOUND` so clients can
register them when `allow_unregistered` is enabled.

## Rate limiting

Rate limiting is centralized in `rail_django.rate_limiting` and applied in:

- Django middleware: `GraphQLRateLimitMiddleware` for GraphQL requests
- Graphene middleware: root operation checks for GraphQL requests
- Schema REST API endpoints

Configure it with `RAIL_DJANGO_RATE_LIMITING`:

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
            ],
        },
    },
}
```

Notes:

- Scopes: `user`, `ip`, `user_or_ip`, `user_ip`, `global`.
- GraphQL limits are enforced once per request (root field), not per field.
- The limiter uses Django cache; configure a shared backend (Redis) in production.
- Legacy settings are still supported when `RAIL_DJANGO_RATE_LIMITING` is unset
  (`security_settings.enable_rate_limiting`, `rate_limit_requests_per_minute`,
  `rate_limit_requests_per_hour`, `GRAPHQL_REQUESTS_LIMIT`,
  `AUTH_LOGIN_ATTEMPTS_LIMIT`, and `GRAPHQL_SCHEMA_API_RATE_LIMIT`).

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

The `DjangoDebug` field is only exposed when `DEBUG=True`.

When introspection is disabled, `security_settings.introspection_roles`
allows specific roles (or superusers) to access it. Authentication is enforced
at the middleware layer when `schema_settings.authentication_required = True`.

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
AUDIT_REDACTION_FIELDS = ["password", "token", "secret"]
AUDIT_REDACTION_MASK = "***REDACTED***"
AUDIT_REDACT_ERROR_MESSAGES = True
AUDIT_RETENTION_DAYS = 90
AUDIT_RETENTION_RUN_INTERVAL = 3600
AUDIT_RETENTION_HOOK = None  # Optional dotted path or callable
```

## Recommended Django security settings

See `rail_django.security_config.SecurityConfig.get_recommended_django_settings()`
for a hardened baseline (HSTS, secure cookies, strict CSRF).

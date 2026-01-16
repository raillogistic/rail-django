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
- Installed apps can define role definitions in `meta.json` under a top-level
  `roles` key (additive with code-defined roles).

Auto-generated model queries enforce Django model permissions by default. The
required permission is built as `<app_label>.<codename>_<model>` with the
codename defaulting to `view`. Auto-generated CRUD mutations enforce
`add`/`change`/`delete` permissions by default. Configure `query_settings` or
`mutation_settings` to change or disable the default checks, or define
GraphQLMeta access guards per model.

Use GraphQLMeta to guard operations per model and to hide fields. See the
[GraphQLMeta guide](meta.md) for configuration examples and field-level rules.

### Role definitions in `meta.json`

Place a `meta.json` file in the root of a Django app and define roles under
`roles`. The loader scans installed apps at startup and registers each role
with `role_manager`. It does not override existing role definitions (for
example, system roles or GraphQLMeta roles with the same name).

Example (`apps/store/meta.json`):

```json
{
  "roles": {
    "catalog_viewer": {
      "description": "Read-only access to the catalog.",
      "role_type": "functional",
      "permissions": ["store.view_product", "store.view_category"]
    },
    "catalog_editor": {
      "description": "Create and update catalog entries.",
      "role_type": "business",
      "permissions": [
        "store.view_product",
        "store.add_product",
        "store.change_product"
      ],
      "parent_roles": ["catalog_viewer"]
    },
    "catalog_admin": {
      "description": "Full control over catalog data.",
      "role_type": "system",
      "permissions": ["store.*"],
      "parent_roles": ["catalog_editor"],
      "is_system_role": true,
      "max_users": 5
    }
  },
  "models": {}
}
```

Notes:
- `role_type` supports `system`, `business`, and `functional` (default: `business`).
- Omit or leave `roles` empty if the app does not define roles.

## Policy engine

The access policy engine adds explicit allow/deny rules with precedence. Policies
are evaluated by priority (higher wins); ties resolve to deny. When a policy
matches, it overrides RBAC and field rules.

Example policy:

```python
from rail_django.security import AccessPolicy, PolicyEffect, policy_manager

policy_manager.register_policy(
    AccessPolicy(
        name="deny_tokens_for_contractors",
        effect=PolicyEffect.DENY,
        priority=50,
        roles=["contractor"],
        fields=["*token*"],
        operations=["read"],
        reason="Token values are not exposed to contractors.",
    )
)
```

## Permission caching

RBAC permission checks are cached per user/context. Invalidation happens on
group/role membership changes. Tune behavior with:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
    }
}
```

## Field permissions

`rail_django.security.field_permissions` can hide or mask sensitive fields based
on roles, permissions, ownership, and policy overrides. Sensitive names like
`password` or `token` are masked by default.

Enable the GraphQL middleware that enforces field visibility and input writes:

```python
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "enable_field_permission_middleware": True,
    },
    "security_settings": {
        "field_permission_input_mode": "reject",  # or "strip"
    },
}
```

Input enforcement traverses nested mutation payloads (including `nested_*` inputs
and `create`/`update`/`set` structures) and applies related-model field rules.

### Classification tags

You can tag fields or models with classifications (e.g., `pii`, `financial`) and
apply policies once per tag:

```python
from rail_django.core.meta import GraphQLMeta

class Customer(models.Model):
    email = models.EmailField()
    salary = models.DecimalField(max_digits=10, decimal_places=2)

    class GraphQLMeta(GraphQLMeta):
        classifications = GraphQLMeta.Classification(
            model=["pii"],
            fields={"salary": ["financial"]},
        )
```

Register policies per classification:

```python
from rail_django.security import AccessPolicy, PolicyEffect, policy_manager

policy_manager.register_classification_bundle(
    "pii",
    [
        AccessPolicy(
            name="mask_pii_for_non_admins",
            effect=PolicyEffect.ALLOW,
            priority=20,
            roles=["admin", "superadmin"],
            visibility="visible",
        ),
        AccessPolicy(
            name="mask_pii_default",
            effect=PolicyEffect.ALLOW,
            priority=10,
            visibility="masked",
            mask_value="***REDACTED***",
        ),
    ],
)
```

## Explain API and auditing

Use the permission explain query to debug decisions:

```graphql
query {
  explainPermission(permission: "project.update_own", modelName: "test_app.Project", objectId: "123") {
    allowed
    reason
    policyDecision { name effect priority reason }
    policyMatches { name effect }
  }
}
```

When permission audit logging is enabled, decisions are emitted via
`rail_django.extensions.audit` with context and policy metadata.

Enable permission auditing with:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_permission_audit": True,
        "permission_audit_log_all": False,
        "permission_audit_log_denies": True,
    }
}
```

## Input validation

`rail_django.security.input_validation` provides a unified validation pipeline
that sanitizes strings, applies allowlisted HTML rules, and flags high-risk
patterns. You can wrap resolvers with `@validate_input` or use
`InputValidator.validate_payload` directly.

Auto-generated CRUD, bulk, and method mutations also call
`InputValidator.validate_and_sanitize` and run `model.full_clean()` before save,
so model validators and `clean()` hooks are enforced.

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

## Reporting datasets

Reporting dataset queries enforce field allowlists and default filters:

- `mode = "records"` respects `metadata.record_fields` (or `metadata.fields`) as
  the explicit allowlist for record selection.
- When `allow_ad_hoc` is false, record fields are restricted to dataset
  dimensions/metrics plus `metadata.allowed_fields`.
- When `allow_ad_hoc` is true and `metadata.allowed_fields` is empty, any valid
  model field is allowed; otherwise, record fields remain allowlisted.
- `default_filters` are always merged into dataset previews and `run_query`
  executions and cannot be bypassed by user specs.

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
- The limiter uses Django cache; configure a shared backend in production.
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

## Webhooks

Model webhooks can include sensitive fields, so prefer explicit allowlists and
redaction:

```python
RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": {
        "enabled": True,
        "endpoints": [
            {
                "name": "orders",
                "url": "https://example.com/webhooks/orders",
                "include_models": ["shop.Order"],
                "signing_secret": "rotate-this",
            },
        ],
        "include_fields": {"shop.order": ["id", "status", "total"]},
        "redact_fields": ["email", "token"],
    }
}
```

When a signing secret is configured, each request includes an HMAC SHA256
signature in the `X-Rail-Signature` header.

If you use `auth_token_path` to fetch tokens, treat auth secrets and tokens as
sensitive data and rotate them regularly.

## Recommended Django security settings

See `rail_django.security_config.SecurityConfig.get_recommended_django_settings()`
for a hardened baseline (HSTS, secure cookies, strict CSRF).

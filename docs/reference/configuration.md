# Configuration Guide

Rail Django resolves configuration from four sources, in this order:

1. `RAIL_DJANGO_GRAPHQL_SCHEMAS[<schema_name>]`
2. `RAIL_DJANGO_GRAPHQL`
3. `ENVIRONMENT` defaults from `rail_django.defaults.ENVIRONMENT_DEFAULTS`
4. `rail_django.defaults.LIBRARY_DEFAULTS`

Note: the `ConfigLoader` applies `ENVIRONMENT` defaults, while the
`SettingsProxy` resolves schema/global overrides on top of library defaults.

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
        "max_property_ordering_results": 2000,
        "property_ordering_warn_on_cap": True,
        "additional_lookup_fields": {},
        "require_model_permissions": True,
        "model_permission_codename": "view",
    },
    "mutation_settings": {
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_bulk_operations": False,
        "enable_nested_relations": True,
        "require_model_permissions": True,
        "model_permission_codenames": {
            "create": "add",
            "update": "change",
            "delete": "delete",
        },
    },
    "subscription_settings": {
        "enable_subscriptions": True,
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_filters": True,
        "include_models": [],
        "exclude_models": [],
    },
    "task_settings": {
        "enabled": False,
        "backend": "thread",
        "default_queue": "default",
        "result_ttl_seconds": 86400,
        "max_retries": 3,
        "retry_backoff": True,
        "track_in_database": True,
        "emit_subscriptions": True,
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
        "max_prefetch_depth": 3,
        "max_query_depth": 10,
        "max_query_complexity": 1000,
        "enable_query_metrics": True,
        "enable_n_plus_one_detection": True,
        "n_plus_one_threshold": 5,
        "enable_query_caching": False,
        "query_cache_timeout": 300,
        "query_cache_user_specific": False,
        "query_cache_scope": "schema",
    },
    "persisted_query_settings": {
        "enabled": False,
        "cache_alias": "default",
        "ttl": 86400,
        "allow_unregistered": True,
        "enforce_allowlist": False,
        "allowlist": {},
        "allowlist_path": None,
        "hash_algorithm": "sha256",
        "max_query_length": 0,
    },
    "security_settings": {
        "enable_authentication": True,
        "enable_authorization": True,
        "enable_policy_engine": True,
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
        "enable_permission_audit": False,
        "permission_audit_log_all": False,
        "permission_audit_log_denies": True,
        "field_permission_input_mode": "reject",
        "enable_input_validation": True,
        "input_allow_html": False,
        "input_failure_severity": "high",
        "introspection_roles": ["admin", "developer"],
    },
    "middleware_settings": {
        "enable_query_complexity_middleware": True,
        "enable_field_permission_middleware": True,
        "performance_threshold_ms": 1000,
    },
    "plugin_settings": {
        "enable_schema_hooks": True,
        "enable_execution_hooks": True,
    },
}
```

## Mutation settings

Nested relation writes are controlled by `mutation_settings.enable_nested_relations`
and can be overridden per model/field via `nested_relations_config` and
`nested_field_config`. When disabled, `nested_*` inputs are not generated and
nested payloads are rejected during mutation execution.

## Query permissions

Auto-generated model queries (list, single, paginated) require a Django
permission by default. `query_settings.model_permission_codename` controls the
permission codename (default: `view`), and the permission string is built as
`<app_label>.<codename>_<model>`. GraphQLMeta access guards for the operation
override the default model permission check. Set
`query_settings.require_model_permissions` to `False` to disable the default
check. Use `model_permission_codename: "add"` if you prefer create permissions.

## Mutation permissions

Auto-generated CRUD mutations require a Django permission by default. The
permission string is built as `<app_label>.<codename>_<model>` with default
codenames of `add` (create), `change` (update), and `delete` (delete). Override
the mapping with `mutation_settings.model_permission_codenames`, or disable the
default check with `mutation_settings.require_model_permissions`. GraphQLMeta
access guards for the operation override the default model permission check.

## Multi-tenancy settings

Multi-tenancy is opt-in and scopes GraphQL queries, mutations, and nested
relations to the current tenant. Tenant context can be resolved from a JWT
claim, a header, or the request subdomain. Missing tenant context raises
`Tenant context required` when `require_tenant` is true.

```python
RAIL_DJANGO_GRAPHQL = {
    "multitenancy_settings": {
        "enabled": True,
        "isolation_mode": "row",
        "tenant_header": "X-Tenant-ID",
        "tenant_claim": "tenant_id",
        "tenant_subdomain": False,
        "default_tenant_field": "tenant",
        "allow_cross_tenant_superuser": True,
        "require_tenant": True,
        "reject_mismatched_tenant_input": True,
        "tenant_model": "accounts.Organization",
    }
}
```

Key options:

- `enabled`: master toggle.
- `isolation_mode`: `row` is supported; `schema` is reserved for future use.
- `tenant_header`: request header name used to resolve the tenant.
- `tenant_claim`: JWT claim name used when `request.jwt_payload` is available.
- `tenant_subdomain`: enable subdomain-based tenant resolution.
- `default_tenant_field`: model field path used when GraphQLMeta does not set `tenant_field`.
- `allow_cross_tenant_superuser`: allow superusers to bypass tenant filters.
- `require_tenant`: reject requests when no tenant could be resolved.
- `reject_mismatched_tenant_input`: reject create/update payloads that specify a different tenant.
- `tenant_model`: optional model path used by `TenantMixin` for the tenant FK.

To disable tenant scoping for a specific model, set `tenant_field = None` in
its GraphQLMeta definition.

## Schema-specific overrides

```python
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "gql": {
        "schema_settings": {
            "authentication_required": True,
        },
        "performance_settings": {
            "max_query_depth": 8,
        },
    },
    "auth": {
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False,
        },
    },
}
```

## Subscription settings

Auto-generated subscriptions are enabled by default and require
`channels-graphql-ws` for WebSocket support.
Disable by setting `subscription_settings.enable_subscriptions` to `False`.
Full reference: `../guides/subscriptions.md`.

```python
RAIL_DJANGO_GRAPHQL = {
    "subscription_settings": {
        "enable_subscriptions": True,
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_filters": True,
        "include_models": ["shop.Order", "User"],
        "exclude_models": ["audit.AuditEvent"],
    },
    "schema_settings": {
        "subscription_field_allowlist": ["order_created", "order_updated"],
    },
}
```

## Task settings

Background task orchestration lets you run long-running mutations asynchronously.

```python
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        "enabled": True,
        "backend": "thread",  # thread, sync, celery, dramatiq, django_q
        "default_queue": "default",
        "result_ttl_seconds": 86400,
        "max_retries": 3,
        "retry_backoff": True,
        "track_in_database": True,
        "emit_subscriptions": True,
    }
}
```

Key options:

- `enabled`: master toggle for task orchestration.
- `backend`: execution backend (`thread` by default).
- `default_queue`: queue name for backends that support queues.
- `result_ttl_seconds`: how long task results are kept.
- `max_retries`: retry attempts on failure.
- `retry_backoff`: exponential retry backoff when enabled.
- `track_in_database`: persist results/progress in `TaskExecution`.
- `emit_subscriptions`: emit `task_updated` events when subscriptions are available.

## Webhook settings

Model webhooks send create/update/delete events to HTTP endpoints asynchronously.
Configure them under `RAIL_DJANGO_GRAPHQL["webhook_settings"]` or use the
project template file `root/webhooks.py`.
Full reference: `../guides/webhooks.md`.

```python
RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": {
        "enabled": True,
        "endpoints": [
            {
                "name": "orders",
                "url": "https://example.com/webhooks/orders",
                "include_models": ["shop.Order"],
            },
            {
                "name": "customers",
                "url": "https://example.com/webhooks/customers",
                "include_models": ["crm.Customer"],
                "headers": {"Authorization": "Bearer token"},
                "signing_secret": "change-me",
            },
        ],
        "events": {"created": True, "updated": True, "deleted": True},
        "exclude_models": ["audit.AuditEvent"],
        "async_backend": "thread",
        "max_workers": 4,
        "max_retries": 3,
    },
}
```

Key options:

- `enabled`: master toggle.
- `endpoints`: list of endpoint configs (url + optional headers/signing).
- `events`: toggle created/updated/deleted delivery.
- `include_models`/`exclude_models`: model allowlist/blocklist (use `app.Model`).
- `include_fields`/`exclude_fields`: per-model field lists.
- `redact_fields`: global or per-model field redaction.
- `endpoints[].include_models`/`endpoints[].exclude_models`: per-endpoint model routing.
- `auth_token_path`: dotted path to a token provider; uses `auth_header`/`auth_scheme`.
- `auth_header`/`auth_scheme`: header name and prefix for token providers.
- `auth_url`/`auth_payload`/`auth_headers`/`auth_timeout_seconds`: parameters for token fetchers.
- `auth_token_field`: JSON field name used by token fetchers (default `access_token`).
- `async_backend`: `thread`, `sync`, or `custom` (uses `async_task_path`).
- `async_task_path`: dotted path to a custom enqueuer (Celery/RQ integration).
- `retry_*`: retry/backoff controls and retryable status codes.

If both global and per-endpoint allowlists are set, the effective models are
the intersection of the two.

Token helper:

```python
RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": {
        "endpoints": [
            {
                "name": "ops",
                "url": "https://example.com/webhooks/rail",
                "auth_token_path": "rail_django.webhooks.auth.fetch_auth_token",
                "auth_url": "https://example.com/oauth/token",
                "auth_payload": {"client_id": "id", "client_secret": "secret"},
                "auth_headers": {"Content-Type": "application/json"},
                "auth_timeout_seconds": 10,
                "auth_token_field": "access_token",
            },
        ],
    },
}
```

Token callables are invoked with `(endpoint, payload, payload_json)`; you can
accept fewer arguments if you don't need them.

## Metadata settings

Metadata exposure is gated by `schema_settings.show_metadata` and requires
authentication. Configure caching and startup invalidation under
`RAIL_DJANGO_GRAPHQL["METADATA"]`:

```python
RAIL_DJANGO_GRAPHQL = {
    "METADATA": {
        "table_cache_enabled": True,
        "table_cache_timeout_seconds": 0,  # 0 = no expiry; defaults to none in prod
        "table_cache_max_entries": 1000,
        "table_cache_authenticated": True,
        "clear_cache_on_start": False,
        "clear_cache_on_start_debug_only": False,
    }
}
```

## Graphene settings

Rail Django uses Graphene-Django. You can keep standard `GRAPHENE` settings:

```python
GRAPHENE = {
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
JWT_ROTATE_REFRESH_TOKENS = True
JWT_REFRESH_REUSE_DETECTION = True
JWT_REFRESH_TOKEN_CACHE = "default"
JWT_COOKIE_SECURE = True
JWT_COOKIE_SAMESITE = "Lax"
JWT_COOKIE_DOMAIN = None
JWT_COOKIE_PATH = "/"
JWT_AUTH_COOKIE_SECURE = True
JWT_AUTH_COOKIE_SAMESITE = "Lax"
JWT_REFRESH_COOKIE_SECURE = True
JWT_REFRESH_COOKIE_SAMESITE = "Lax"
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

## Permission policy settings

The policy engine adds explicit allow/deny rules with precedence and can be
audited. Field permission input handling is configured here as well:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_policy_engine": True,
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
        "enable_permission_audit": False,
        "permission_audit_log_all": False,
        "permission_audit_log_denies": True,
        "field_permission_input_mode": "reject",  # or "strip"
    },
    "middleware_settings": {
        "enable_field_permission_middleware": True,
    },
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

Enable query metrics and N+1 detection through `performance_settings`:

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_query_metrics": True,
        "enable_n_plus_one_detection": True,
        "n_plus_one_threshold": 5,
    }
}
```

## Query caching hooks

Query caching is opt-in and requires a cache backend registered via
`set_query_cache_factory`. You can use the in-memory backend for tests or wire
in your own cache adapter.

```python
from rail_django.core.services import set_query_cache_factory
from rail_django.extensions.query_cache import InMemoryQueryCacheBackend

backend = InMemoryQueryCacheBackend(default_timeout=300)
set_query_cache_factory(lambda schema_name=None: backend)

RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_query_caching": True,
        "query_cache_timeout": 300,
        "query_cache_user_specific": False,
        "query_cache_scope": "schema",
    }
}
```

Use `invalidate_query_cache(schema_name="...")` when writes should invalidate
cached query results.

## Persisted queries (APQ)

Persisted queries are opt-in and can be backed by cache or an allowlist.

```python
RAIL_DJANGO_GRAPHQL = {
    "persisted_query_settings": {
        "enabled": True,
        "cache_alias": "default",
        "ttl": 86400,
        "allow_unregistered": True,
        "enforce_allowlist": False,
        "allowlist": {},
        "allowlist_path": None,
        "hash_algorithm": "sha256",
        "max_query_length": 0,
    }
}
```

If you want a strict allowlist, set `enforce_allowlist = True` and provide a
hash->query mapping (or a list of hashes) in `allowlist` or `allowlist_path`.
When `enforce_allowlist` is false, allowlist entries are treated as
pre-registered queries and unknown hashes return `PERSISTED_QUERY_NOT_FOUND`
so clients can register them when `allow_unregistered` is enabled.

## Plugin settings

Plugin execution hooks are controlled via `plugin_settings`:

```python
RAIL_DJANGO_GRAPHQL = {
    "plugin_settings": {
        "enable_schema_hooks": True,
        "enable_execution_hooks": True,
    }
}
```

Enable plugins via `GRAPHQL_SCHEMA_PLUGINS`:

```python
GRAPHQL_SCHEMA_PLUGINS = {
    "rail_django.extensions.observability.SentryIntegrationPlugin": {"enabled": True},
    "rail_django.extensions.observability.OpenTelemetryIntegrationPlugin": {"enabled": False},
}
```

## Schema registry snapshots

Enable snapshots to power the schema export, history, and diff endpoints.

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_registry": {
        "enable_schema_snapshots": True,
        "snapshot_max_entries": 50,
        "enable_schema_export": True,
        "enable_schema_diff": True,
    }
}
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
    "enforce_streaming_csv": True,
    "csv_chunk_size": 1000,
    "excel_write_only": True,
    "excel_auto_width": False,
    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30,
        "trusted_proxies": ["10.0.0.1"],
    },
    "allowed_models": ["blog.Post", "auth.User"],
    "export_fields": {
        "blog.Post": ["id", "title", "author.username", "created_at"],
    },
    "export_exclude": {
        "blog.Post": ["author.password"],
    },
    "sensitive_fields": ["password", "token"],
    "require_export_fields": True,
    "require_model_permissions": True,
    "require_field_permissions": True,
    "required_permissions": ["blog.export_post"],
    "filterable_fields": {
        "blog.Post": ["status", "author.username", "created_at"],
    },
    "filterable_special_fields": ["quick"],
    "orderable_fields": {
        "blog.Post": ["created_at", "title"],
    },
    "max_filters": 50,
    "max_or_depth": 3,
    "max_prefetch_depth": 2,
    "sanitize_formulas": True,
    "formula_escape_strategy": "prefix",
    "formula_escape_prefix": "'",
    "field_formatters": {
        "blog.Post": {
            "author.email": {"type": "mask", "show_last": 4},
            "created_at": {"type": "datetime", "format": "Y-m-d H:i"},
        }
    },
    "export_templates": {
        "recent_posts": {
            "app_name": "blog",
            "model_name": "Post",
            "fields": ["id", "title", "created_at"],
            "ordering": ["-created_at"],
            "required_permissions": ["blog.export_post"],
            "shared": True,
        }
    },
    "async_jobs": {
        "enable": True,
        "backend": "thread",  # or "celery"/"rq"
        "expires_seconds": 3600,
    },
}
```

Notes:

- Exports are default-deny when `require_export_fields` is `True`. Each model must
  have an explicit `export_fields` entry to allow accessors.
- Accessors must be full-path allowlisted (`author.username`), not base field names.
- Filters and ordering are allowlisted via `filterable_fields` / `orderable_fields`.
- Add GraphQL special filter keys (e.g., `quick`) to `filterable_special_fields`.
- Async jobs require a shared cache between web and workers.
- Callable accessors are disabled by default; enable `allow_callables` for explicit
  allowlisted method access.
- `allowed_fields` remains as a legacy alias for `export_fields`.
- Async jobs are enabled by default with the `thread` backend; switch to `celery`
  or `rq` for worker-based processing.

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
- Use `schema_settings.graphiql_superuser_only` and
  `schema_settings.graphiql_allowed_hosts` on the `graphiql` schema to gate
  GraphiQL in production. Leave the allowlist empty to permit any host.
- Caching helpers were removed, but rate limiting uses Django cache; configure
  `CACHES` with a shared backend in production.

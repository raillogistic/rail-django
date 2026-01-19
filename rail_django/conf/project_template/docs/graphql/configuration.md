# Complete Configuration

## Overview

This document is the complete reference for all Rail Django configuration settings. All settings are defined in `RAIL_DJANGO_GRAPHQL` in your `settings.py` file.

---

## Table of Contents

1. [General Structure](#general-structure)
2. [schema_settings](#schema_settings)
3. [type_generation_settings](#type_generation_settings)
4. [query_settings](#query_settings)
5. [mutation_settings](#mutation_settings)
6. [subscription_settings](#subscription_settings)
7. [task_settings](#task_settings)
8. [performance_settings](#performance_settings)
9. [security_settings](#security_settings)
10. [middleware_settings](#middleware_settings)
11. [error_handling](#error_handling)
12. [custom_scalars](#custom_scalars)
13. [Multi-Schema](#multi-schema)

---

## General Structure

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": { ... },
    "type_generation_settings": { ... },
    "query_settings": { ... },
    "mutation_settings": { ... },
    "subscription_settings": { ... },
    "task_settings": { ... },
    "performance_settings": { ... },
    "security_settings": { ... },
    "middleware_settings": { ... },
    "error_handling": { ... },
    "custom_scalars": { ... },
    "monitoring_settings": { ... },
    "schema_registry": { ... },
}
```

---

## schema_settings

Global GraphQL schema configuration.

```python
"schema_settings": {
    # ─── Exclusions ───
    # Django apps to ignore during generation
    "excluded_apps": ["admin", "contenttypes", "sessions"],
    # Specific models to ignore ("app.Model" or "Model")
    "excluded_models": ["auth.Permission"],

    # ─── Schema Features ───
    # Allows the __schema / __type query
    "enable_introspection": True,
    # Enables the GraphiQL interface
    "enable_graphiql": True,
    # Restrict GraphiQL to superusers
    "graphiql_superuser_only": False,
    # Allowlist hosts that can access GraphiQL (empty = no restriction)
    "graphiql_allowed_hosts": [],
    # Rebuild schema after save/delete model (dev only)
    "auto_refresh_on_model_change": False,
    # Rebuild after migrations
    "auto_refresh_on_migration": True,
    # Build schema at startup
    "prebuild_on_startup": False,

    # ─── Authentication ───
    # Requires a valid JWT for all requests
    "authentication_required": True,
    # Disables login/register/logout mutations
    "disable_security_mutations": False,
    # Enables extension mutations (audit, health, etc.)
    "enable_extension_mutations": True,

    # ─── Pagination ───
    # Enables pagination fields (offset/limit)
    "enable_pagination": True,

    # ─── Naming ───
    # Converts names to camelCase (false = snake_case)
    "auto_camelcase": False,

    # ─── Metadata ───
    # Exposes metadata queries for dynamic UIs
    "show_metadata": False,

    # ─── Extensions ───
    # Additional Query classes (dotted path)
    "query_extensions": [
        "myapp.schema.CustomQuery",
    ],
    # Additional Mutation classes
    "mutation_extensions": [],

    # ─── Allowlists (optional) ───
    # If defined, only these root fields are exposed
    "query_field_allowlist": None,  # ["users", "products"]
    "mutation_field_allowlist": None,
    "subscription_field_allowlist": None,
}
```

---

## type_generation_settings

Controls GraphQL type generation.

```python
"type_generation_settings": {
    # Fields to exclude by model
    "exclude_fields": {
        "auth.User": ["password"],
        "store.Product": ["internal_notes"],
    },
    # Legacy alias
    "excluded_fields": {},

    # Fields to include (None = all)
    "include_fields": None,

    # Custom type mappings
    "custom_field_mappings": {
        # Django Field Class: Graphene Scalar
    },

    # Generates filtering inputs
    "generate_filters": True,
    "enable_filtering": True,  # Alias

    # Naming
    "auto_camelcase": False,

    # Uses model help_text as descriptions
    "generate_descriptions": True,
}
```

---

## query_settings

GraphQL query configuration.

```python
"query_settings": {
    # ─── Generation ───
    "generate_filters": True,
    "generate_ordering": True,
    "generate_pagination": True,

    # ─── Execution ───
    "enable_pagination": True,
    "enable_ordering": True,

    # ─── Style ───
    # Uses Relay connections instead of lists
    "use_relay": False,

    # ─── Pagination ───
    "default_page_size": 20,
    "max_page_size": 100,

    # ─── Grouping ───
    "max_grouping_buckets": 200,

    # ─── Property Ordering ───
    # Limits results when sorting by Python property
    "max_property_ordering_results": 2000,

    # ─── Additional Lookups ───
    # Allows fetching by fields other than ID
    "additional_lookup_fields": {
        "store.Product": ["sku", "slug"],
        "auth.User": ["username", "email"],
    },

    # ─── Permissions ───
    "require_model_permissions": True,
    "model_permission_codename": "view",
}
```

---

## mutation_settings

GraphQL mutation configuration.

```python
"mutation_settings": {
    # ─── Generation ───
    "generate_create": True,
    "generate_update": True,
    "generate_delete": True,
    "generate_bulk": False,

    # ─── Execution ───
    "enable_create": True,
    "enable_update": True,
    "enable_delete": True,
    "enable_bulk_operations": False,

    # ─── Methods ───
    # Exposes model methods as mutations
    "enable_method_mutations": True,

    # ─── Permissions ───
    "require_model_permissions": True,
    "model_permission_codenames": {
        "create": "add",
        "update": "change",
        "delete": "delete",
    },

    # ─── Bulk ───
    "bulk_batch_size": 100,

    # ─── Required Fields ───
    "required_update_fields": {},

    # ─── Nested Relationships ───
    "enable_nested_relations": True,
    "nested_relations_config": {},
    "nested_field_config": {},
}
```

---

## subscription_settings

Real-time subscription configuration.

```python
"subscription_settings": {
    # Enables subscription generation
    "enable_subscriptions": True,

    # Event types
    "enable_create": True,
    "enable_update": True,
    "enable_delete": True,

    # Enables filters on subscriptions
    "enable_filters": True,

    # Allowlist/Blocklist of models
    "include_models": [],  # Empty = all
    "exclude_models": ["audit.AuditEvent"],
}
```

---

## task_settings

Background task orchestration.

```python
"task_settings": {
    "enabled": False,
    "backend": "thread",  # thread, sync, celery, dramatiq, django_q
    "default_queue": "default",
    "result_ttl_seconds": 86400,
    "max_retries": 3,
    "retry_backoff": True,
    "track_in_database": True,
    "emit_subscriptions": True,
}
```

---

## performance_settings

Performance optimization.

```python
"performance_settings": {
    # ─── QuerySet Optimization ───
    "enable_query_optimization": True,
    "enable_select_related": True,
    "enable_prefetch_related": True,
    "enable_only_fields": True,
    "enable_defer_fields": False,

    # ─── DataLoader ───
    "enable_dataloader": True,
    "dataloader_batch_size": 100,

    # ─── Limits ───
    "max_query_depth": 10,
    "max_query_complexity": 1000,

    # ─── Cost ───
    "enable_query_cost_analysis": False,

    # ─── Timeout ───
    "query_timeout": 30,
}
```

---

## security_settings

Security configuration.

```python
"security_settings": {
    # ─── Auth ───
    "enable_authentication": True,
    "enable_authorization": True,

    # ─── Policy Engine ───
    "enable_policy_engine": True,

    # ─── Permission Cache ───
    "enable_permission_cache": True,
    "permission_cache_ttl_seconds": 300,

    # ─── Permission Audit ───
    "enable_permission_audit": False,
    "permission_audit_log_all": False,
    "permission_audit_log_denies": True,

    # ─── Rate Limiting ───
    "enable_rate_limiting": False,
    "rate_limit_requests_per_minute": 60,
    "rate_limit_requests_per_hour": 1000,

    # ─── Depth Limiting ───
    "enable_query_depth_limiting": True,

    # ─── CORS ───
    "allowed_origins": ["*"],
    "enable_csrf_protection": True,
    "enable_cors": True,

    # ─── Field Permissions ───
    "enable_field_permissions": True,
    "field_permission_input_mode": "reject",  # or "strip"
    "enable_object_permissions": True,

    # ─── Input Validation ───
    "enable_input_validation": True,
    "enable_sql_injection_protection": True,
    "enable_xss_protection": True,

    # ─── HTML in Inputs ───
    "input_allow_html": False,
    "input_allowed_html_tags": ["p", "br", "strong", "em", ...],
    "input_allowed_html_attributes": {"*": ["class"], "a": ["href"], ...},

    # ─── String Limits ───
    "input_max_string_length": None,
    "input_truncate_long_strings": False,
    "input_failure_severity": "high",
    "input_pattern_scan_limit": 10000,

    # ─── Session ───
    "session_timeout_minutes": 30,

    # ─── Upload ───
    "max_file_upload_size": 10 * 1024 * 1024,  # 10MB
    "allowed_file_types": [".jpg", ".jpeg", ".png", ".pdf", ".txt"],
}
```

---

## middleware_settings

GraphQL middleware configuration.

```python
"middleware_settings": {
    # ─── Activation ───
    "enable_authentication_middleware": True,
    "enable_logging_middleware": True,
    "enable_performance_middleware": True,
    "enable_error_handling_middleware": True,
    "enable_rate_limiting_middleware": True,
    "enable_validation_middleware": True,
    "enable_field_permission_middleware": True,
    "enable_cors_middleware": True,
    "enable_query_complexity_middleware": True,

    # ─── Logging ───
    "log_queries": True,
    "log_mutations": True,
    "log_introspection": False,
    "log_errors": True,

    # ─── Performance ───
    "log_performance": True,
    "performance_threshold_ms": 1000,
}
```

---

## error_handling

Error handling.

```python
"error_handling": {
    # Includes error details
    "enable_detailed_errors": False,  # True in dev

    # Logging
    "enable_error_logging": True,
    "enable_error_reporting": True,

    # Sentry
    "enable_sentry_integration": False,

    # Masking
    "mask_internal_errors": True,
    "include_stack_trace": False,

    # Format
    "error_code_prefix": "RAIL_GQL",
    "max_error_message_length": 500,

    # Categorization
    "enable_error_categorization": True,
    "enable_error_metrics": True,

    # Log Level
    "log_level": "ERROR",
}
```

---

## custom_scalars

Custom GraphQL scalars.

```python
"custom_scalars": {
    "DateTime": {"enabled": True},
    "Date": {"enabled": True},
    "Time": {"enabled": True},
    "JSON": {"enabled": True},
    "UUID": {"enabled": True},
    "Email": {"enabled": True},
    "URL": {"enabled": True},
    "Phone": {"enabled": True},
    "Decimal": {"enabled": True},
    "Binary": {"enabled": True},
}
```

---

## Multi-Schema

Multiple schema configuration.

```python
# Distinct schemas with different configurations
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    # Authentication schema (public)
    "auth": {
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False,
            "query_field_allowlist": ["me"],
            "mutation_field_allowlist": ["login", "register", "refresh_token"],
        },
        "mutation_settings": {
            "generate_create": False,
            "generate_update": False,
        },
    },

    # Main schema (authenticated)
    "default": {
        "schema_settings": {
            "authentication_required": True,
        },
    },

    # Admin schema (privileged)
    "admin": {
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": True,
        },
        "mutation_settings": {
            "enable_bulk_operations": True,
        },
    },
}
```

### Generated Endpoints

- `/graphql/auth/` - Auth schema
- `/graphql/gql/` - Default schema
- `/graphql/admin/` - Admin schema

### Schema Registration

Schemas are registered from two sources:

1. **Automatic discovery**: `schemas.py`, `graphql_schema.py` modules with `register_schema()`
2. **Settings fallback**: Entries in `RAIL_DJANGO_GRAPHQL_SCHEMAS`

### Disabling a Schema

```python
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "admin": {
        "enabled": False,  # Disabled
    },
}
```

---

## Environment Variables

| Variable                      | Description                   | Default                    |
| ----------------------------- | ----------------------------- | -------------------------- |
| `DJANGO_SETTINGS_MODULE`      | Settings module               | `root.settings.dev`        |
| `DJANGO_SECRET_KEY`           | Django secret key             | (required)                 |
| `DATABASE_URL`                | DB connection URL             | (required)                 |
| `REDIS_URL`                   | Redis URL (cache, rate limit) | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY`              | JWT signing key               | `DJANGO_SECRET_KEY`        |
| `GRAPHQL_PERFORMANCE_ENABLED` | Enables perf metrics          | `False`                    |
| `GRAPHQL_PERFORMANCE_HEADERS` | Adds perf headers             | `False`                    |

---

## See Also

- [Queries](./queries.md) - Using query_settings
- [Mutations](./mutations.md) - Using mutation_settings
- [Permissions](../security/permissions.md) - Using security_settings
- [Deployment](../deployment/production.md) - Production configuration

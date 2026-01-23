# Complete Configuration Reference

This document contains all configuration options available in Rail Django, organized by category.

## Configuration Structure

Rail Django uses a hierarchical configuration system:

```python
# settings.py

# 1. Global settings (apply to all schemas)
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {...},
    "query_settings": {...},
    "mutation_settings": {...},
    # ... more settings
}

# 2. Per-schema overrides
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "default": {
        # Overrides for default schema
    },
    "admin": {
        # Overrides for admin schema
    }
}
```

---

## Schema Settings

Control overall schema behavior:

```python
"schema_settings": {
    # App and model exclusions
    "excluded_apps": [],              # App labels to skip
    "excluded_models": [],            # Model names to skip

    # GraphQL features
    "enable_introspection": True,     # Allow introspection queries
    "enable_graphiql": True,          # Enable GraphiQL UI
    "graphiql_superuser_only": False, # Restrict GraphiQL to superusers
    "graphiql_allowed_hosts": [],     # Allowed hosts for GraphiQL

    # Schema lifecycle
    "auto_refresh_on_model_change": False,  # Rebuild on model save
    "auto_refresh_on_migration": True,      # Rebuild after migration
    "prebuild_on_startup": False,           # Build schema at startup

    # Security
    "authentication_required": True,   # Require auth for all operations
    "disable_security_mutations": False,  # Disable login/register

    # Features
    "enable_pagination": True,
    "auto_camelcase": True,           # Convert snake_case to camelCase
    "enable_extension_mutations": True,
    "show_metadata": False,           # Enable metadata introspection

    # Extensions
    "query_extensions": [],           # Additional query classes
    "mutation_extensions": [],        # Additional mutation classes

    # Field allowlists (null = allow all)
    "query_field_allowlist": None,
    "mutation_field_allowlist": None,
    "subscription_field_allowlist": None,
}
```

---

## Type Generation Settings

Control GraphQL type generation:

```python
"type_generation_settings": {
    # Field exclusions
    "exclude_fields": {},             # {"Model": ["field1", "field2"]}
    "excluded_fields": {},            # Alias for exclude_fields

    # Field inclusions (whitelist)
    "include_fields": None,           # {"Model": ["field1"]} or None

    # Custom mappings
    "custom_field_mappings": {},      # {DjangoField: GrapheneType}

    # Generation options
    "generate_filters": True,         # Generate filter inputs
    "enable_filtering": True,         # Alias
    "auto_camelcase": True,
    "generate_descriptions": True,    # Use help_text as descriptions
}
```

---

## Query Settings

Control query generation and behavior:

```python
"query_settings": {
    # Generation toggles
    "generate_filters": True,
    "generate_ordering": True,
    "generate_pagination": True,

    # Execution toggles
    "enable_pagination": True,
    "enable_ordering": True,
    "use_relay": False,              # Use Relay connections

    # Pagination
    "default_page_size": 20,
    "max_page_size": 100,

    # Grouping
    "max_grouping_buckets": 200,

    # Property ordering
    "max_property_ordering_results": 2000,

    # Lookup fields
    "additional_lookup_fields": {},   # {"Product": ["slug", "sku"]}

    # Permissions
    "require_model_permissions": True,
    "model_permission_codename": "view",
}
```

---

## Mutation Settings

Control mutation generation and behavior:

```python
"mutation_settings": {
    # Generation toggles
    "generate_create": True,
    "generate_update": True,
    "generate_delete": True,
    "generate_bulk": False,

    # Execution toggles
    "enable_create": True,
    "enable_update": True,
    "enable_delete": True,
    "enable_bulk_operations": True,
    "enable_method_mutations": True,

    # Permissions
    "require_model_permissions": True,
    "model_permission_codenames": {
        "create": "add",
        "update": "change",
        "delete": "delete",
    },

    # Bulk operations
    "bulk_batch_size": 100,
    "bulk_include_models": [],
    "bulk_exclude_models": [],

    # Required fields
    "required_update_fields": {},     # {"Model": ["field1"]}

    # Nested relations
    "enable_nested_relations": True,
    "nested_relations_config": {},    # {"Model": True/False}
    "nested_field_config": {},        # {"Model.field": True/False}
}
```

---

## Subscription Settings

Control real-time subscriptions:

```python
"subscription_settings": {
    "enable_subscriptions": True,
    "enable_create": True,            # Send create events
    "enable_update": True,            # Send update events
    "enable_delete": True,            # Send delete events
    "enable_filters": True,           # Allow filtering subscriptions
    "include_models": [],             # Whitelist models
    "exclude_models": [],             # Blacklist models
}
```

---

## Performance Settings

Control query optimization:

```python
"performance_settings": {
    # Query optimization
    "enable_query_optimization": True,
    "enable_select_related": True,
    "enable_prefetch_related": True,
    "enable_only_fields": True,
    "enable_defer_fields": False,

    # DataLoader
    "enable_dataloader": True,
    "dataloader_batch_size": 100,

    # Query limits
    "max_query_depth": 10,
    "max_query_complexity": 1000,
    "enable_query_cost_analysis": False,
    "query_timeout": 30,              # Seconds
}
```

---

## Security Settings

Control authentication, authorization, and input validation:

```python
"security_settings": {
    # Authentication
    "enable_authentication": True,
    "session_timeout_minutes": 30,

    # Authorization
    "enable_authorization": True,
    "enable_policy_engine": True,
    "enable_permission_cache": True,
    "permission_cache_ttl_seconds": 300,

    # Permission auditing
    "enable_permission_audit": False,
    "permission_audit_log_all": False,
    "permission_audit_log_denies": True,

    # Rate limiting
    "enable_rate_limiting": False,
    "rate_limit_requests_per_minute": 60,
    "rate_limit_requests_per_hour": 1000,

    # Query protection
    "enable_query_depth_limiting": True,

    # CORS/CSRF
    "allowed_origins": ["*"],
    "enable_csrf_protection": True,
    "enable_cors": True,

    # Field permissions
    "enable_field_permissions": True,
    "field_permission_input_mode": "reject",  # or "strip"
    "enable_object_permissions": True,

    # Input validation
    "enable_input_validation": True,
    "enable_sql_injection_protection": True,
    "enable_xss_protection": True,
    "input_allow_html": False,
    "input_allowed_html_tags": [
        "p", "br", "strong", "em", "u",
        "ol", "ul", "li", "h1", "h2", "h3"
    ],
    "input_allowed_html_attributes": {
        "*": ["class"],
        "a": ["href", "title"],
        "img": ["src", "alt", "width", "height"],
    },
    "input_max_string_length": None,
    "input_truncate_long_strings": False,
    "input_failure_severity": "high",
    "input_pattern_scan_limit": 10000,

    # File uploads
    "max_file_upload_size": 10485760,  # 10MB
    "allowed_file_types": [".jpg", ".jpeg", ".png", ".pdf", ".txt"],
}
```

---

## Middleware Settings

Control GraphQL middleware:

```python
"middleware_settings": {
    # Middleware toggles
    "enable_authentication_middleware": True,
    "enable_logging_middleware": True,
    "enable_performance_middleware": True,
    "enable_error_handling_middleware": True,
    "enable_rate_limiting_middleware": True,
    "enable_validation_middleware": True,
    "enable_field_permission_middleware": True,
    "enable_cors_middleware": True,
    "enable_query_complexity_middleware": True,

    # Logging
    "log_queries": True,
    "log_mutations": True,
    "log_introspection": False,
    "log_errors": True,
    "log_performance": True,

    # Performance
    "performance_threshold_ms": 1000,
}
```

---

## Error Handling

Control error responses:

```python
"error_handling": {
    "enable_detailed_errors": False,  # Show details in dev
    "enable_error_logging": True,
    "enable_error_reporting": True,
    "enable_sentry_integration": False,

    # Error formatting
    "mask_internal_errors": True,
    "include_stack_trace": False,
    "error_code_prefix": "RAIL_GQL",
    "max_error_message_length": 500,
    "enable_error_categorization": True,
    "enable_error_metrics": True,
    "log_level": "ERROR",
}
```

---

## Custom Scalars

Enable custom GraphQL scalars:

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

## JWT Configuration

Separate Django settings for JWT:

```python
# JWT Settings (separate from RAIL_DJANGO_GRAPHQL)
JWT_ALGORITHM = "HS256"
JWT_SECRET_KEY = SECRET_KEY
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
JWT_REFRESH_TOKEN_LIFETIME = timedelta(days=7)

# Cookie-based JWT
JWT_ALLOW_COOKIE_AUTH = False
JWT_ENFORCE_CSRF = True
JWT_COOKIE_NAME = "access_token"
JWT_COOKIE_SECURE = True
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SAMESITE = "Lax"
```

---

## Export Settings

Data export configuration:

```python
RAIL_DJANGO_EXPORT = {
    "enabled": True,

    # Security
    "model_allowlist": [],            # ["store.Product", "store.Order"]
    "require_authentication": True,
    "require_permission": "export_data",

    # Limits
    "max_rows": 10000,
    "max_fields": 50,
    "max_filter_complexity": 10,

    # Rate limiting
    "rate_limit_enabled": True,
    "rate_limit_requests_per_minute": 5,

    # Async exports
    "async_enabled": True,
    "async_threshold_rows": 1000,

    # Storage
    "storage_backend": "file",        # "file" or "s3"
    "storage_path": "/tmp/exports",
    "retention_hours": 24,

    # Streaming
    "stream_csv": True,
    "chunk_size": 1000,
}
```

---

## Templating Settings

PDF generation configuration:

```python
RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    "enabled": True,

    # Rendering
    "renderer": "weasyprint",         # "weasyprint" or "wkhtmltopdf"
    "default_template_config": {
        "page_size": "A4",
        "margin": "2cm",
        "font_family": "Helvetica",
    },

    # Security
    "require_authentication": True,
    "url_fetcher_allowlist": [],

    # Rate limiting
    "rate_limit_enabled": True,
    "rate_limit_requests_per_minute": 10,

    # Async jobs
    "async_jobs": {
        "enable": False,
        "backend": "thread",
        "result_ttl_seconds": 3600,
    },

    # Features
    "enable_preview": False,          # HTML preview endpoint
    "enable_catalog": True,           # Template catalog endpoint

    # Post-processing
    "watermark": {
        "enable": False,
        "text": "CONFIDENTIAL",
    },
    "encryption": {
        "enable": False,
        "user_password": None,
        "owner_password": None,
    },
}
```

---

## Webhook Settings

Webhook configuration:

```python
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,

    "endpoints": [
        {
            "name": "orders",
            "url": "https://api.example.com/webhooks/orders",
            "include_models": ["store.Order", "store.OrderItem"],
            "events": ["created", "updated", "deleted"],
            "headers": {
                "X-API-Key": "secret-key"
            },
        },
    ],

    # Delivery settings
    "timeout_seconds": 30,
    "max_retries": 3,
    "retry_backoff": True,

    # Payload
    "include_full_object": True,
    "include_changes": True,
}
```

---

## Task Settings

Background task configuration:

```python
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        "enabled": True,
        "backend": "thread",          # thread, sync, celery, dramatiq, django_q
        "default_queue": "default",
        "result_ttl_seconds": 86400,
        "max_retries": 3,
        "retry_backoff": True,
        "track_in_database": True,
        "emit_subscriptions": True,
    }
}
```

---

## Environment Variables

Common environment variables:

```bash
# Django
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
DJANGO_SETTINGS_MODULE=root.settings.production

# Database
DATABASE_URL=postgres://user:pass@host:5432/dbname

# JWT
JWT_SECRET_KEY=jwt-secret-key

# Cache
CACHE_URL=redis://localhost:6379/0

# Sentry (optional)
SENTRY_DSN=https://key@sentry.io/project

# Export
EXPORT_MAX_ROWS=10000
EXPORT_STORAGE_PATH=/var/exports

# GraphQL
GRAPHQL_DEBUG=False
GRAPHQL_PERFORMANCE_ENABLED=True
```

---

## Multi-Schema Example

Complete multi-schema configuration:

```python
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "public": {
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False,
            "enable_introspection": False,
            "query_field_allowlist": [
                "products", "product", "categories", "category"
            ],
            "mutation_field_allowlist": [],
        },
        "mutation_settings": {
            "enable_create": False,
            "enable_update": False,
            "enable_delete": False,
        },
    },
    "api": {
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": False,
        },
    },
    "admin": {
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": True,
            "graphiql_superuser_only": True,
        },
        "mutation_settings": {
            "enable_bulk_operations": True,
            "generate_bulk": True,
        },
    },
}
```

---

## Development vs Production

### Development

```python
# settings/development.py
DEBUG = True

RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_introspection": True,
        "enable_graphiql": True,
        "authentication_required": False,
    },
    "error_handling": {
        "enable_detailed_errors": True,
        "include_stack_trace": True,
    },
}
```

### Production

```python
# settings/production.py
DEBUG = False

RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_introspection": False,
        "enable_graphiql": False,
        "graphiql_superuser_only": True,
        "authentication_required": True,
    },
    "security_settings": {
        "enable_rate_limiting": True,
        "enable_query_depth_limiting": True,
    },
    "error_handling": {
        "enable_detailed_errors": False,
        "mask_internal_errors": True,
        "enable_sentry_integration": True,
    },
}
```

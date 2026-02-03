# Rail Django: The Complete Guide

Welcome to the definitive documentation for **Rail Django**, the production-grade framework for building enterprise GraphQL APIs with Django.

This guide is designed to take you from a fresh installation to deploying a complex, secured, and high-performance API system.

---

## 📑 Table of Contents

1.  [Introduction & Philosophy](#1-introduction--philosophy)
2.  [Installation & Setup](#2-installation--setup)
    - [Prerequisites](#prerequisites)
    - [Quick Start](#quick-start)
    - [Project Structure](#project-structure)
3.  [Core Architecture](#3-core-architecture)
    - [Auto-Schema Generation](#auto-schema-generation)
    - [The Registry System](#the-registry-system)
    - [Resolvers & Mutations](#resolvers--mutations)
4.  [Configuration Guide](#4-configuration-guide)
    - [Global Settings](#global-settings)
    - [Multi-Schema Configuration](#multi-schema-configuration)
    - [Environment Variables](#environment-variables)
5.  [Data Modeling & API Design](#5-data-modeling--api-design)
    - [Defining Models](#defining-models)
    - [Customizing GraphQL Types](#customizing-graphql-types)
    - [The `graphql_meta` Class](#the-graphql_meta-class)
6.  [Querying & Filtering](#6-querying--filtering)
    - [Advanced Filtering](#advanced-filtering)
    - [Pagination Strategies](#pagination-strategies)
    - [Ordering & Sorting](#ordering--sorting)
7.  [Mutations & Operations](#7-mutations--operations)
    - [Auto-CRUD Mutations](#auto-crud-mutations)
    - [Custom Mutations](#custom-mutations)
    - [Bulk Operations](#bulk-operations)
8.  [Security & Permissions](#8-security--permissions)
    - [Authentication Flow (JWT)](#authentication-flow-jwt)
    - [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
    - [Field-Level Security](#field-level-security)
    - [Input Sanitization](#input-sanitization)
9.  [Extensions System](#9-extensions-system)
    - [Audit Logging](#audit-logging)
    - [Webhooks](#webhooks)
    - [Data Exporting (Excel/CSV)](#data-exporting-excelcsv)
    - [Background Tasks](#background-tasks)
    - [Health Monitoring](#health-monitoring)
    - [Subscriptions (Real-time)](#subscriptions-real-time)
    - [Multi-Factor Authentication (MFA)](#multi-factor-authentication-mfa)
    - [PDF Templating Engine](#pdf-templating-engine)
    - [Model Schema Introspection (Metadata V2)](#model-schema-introspection-metadata-v2)
10. [Performance Tuning](#10-performance-tuning)
    - [Query Optimization](#query-optimization)
    - [DataLoader & N+1 Problem](#dataloader--n1-problem)
    - [Complexity Limiting](#complexity-limiting)
11. [Deployment & DevOps](#11-deployment--devops)
    - [Docker Configuration](#docker-configuration)
    - [Production Checklist](#production-checklist)
    - [Troubleshooting](#troubleshooting)
12. [Manual Deployment Guide](#12-manual-deployment-guide)

---

## 1. Introduction & Philosophy

Rail Django exists to solve the "boilerplate fatigue" associated with Graphene-Django. While Graphene is powerful, building a standard CRUD API often requires writing hundreds of lines of repetitive `ObjectType`, `DjangoFilterConnectionField`, and `Mutation` classes.

**Our Philosophy:**

1.  **Convention over Configuration:** If you define a Django model, you should get a working API immediately.
2.  **Security by Design:** Permissions, depths limits, and input validation should be on by default.
3.  **Battery Included:** Audit logs, exports, and health checks are requirements, not "nice-to-haves".

---

## 2. Installation & Setup

### Prerequisites

- Python 3.11 or higher
- pip (Python Package Installer)
- (Optional) Docker & Docker Compose for containerized development

### Quick Start

1.  **Install the library:**

    ```bash
    pip install rail-django
    # OR directly from source
    pip install git+https://github.com/raillogistic/rail-django.git
    ```

2.  **Bootstrap your project:**
    The `rail-admin` CLI tool sets up the perfect directory structure.

    ```bash
    rail-admin startproject my_platform
    cd my_platform
    ```

3.  **Initialize the Database:**

    ```bash
    python manage.py migrate
    ```

4.  **Create an Admin User:**

    ```bash
    python manage.py createsuperuser
    ```

5.  **Run the Server:**
    ```bash
    python manage.py runserver
    ```
    Access GraphiQL at: `http://localhost:8000/graphql/`. In production,
    GraphiQL is superuser-only; log in and use the auth cookies set by the
    `login` mutation for requests.

### Dependency Management

Rail Django uses a split requirements system to separate development and production dependencies.

- `requirements/base.txt`: Core dependencies required for the application to run.
- `requirements/dev.txt`: Extends `base.txt` with development tools (e.g., `black`) and installs `rail-django` from PyPI or locally.
- `requirements/prod.txt`: Extends `base.txt` with production-specific settings.
- `requirements/rail-django.txt`: Installs `rail-django` directly from the official GitHub repository (keep separate for frequent updates).

To install dependencies for development:

```bash
pip install -r requirements/dev.txt
```

To install dependencies for production (non-Docker):

```bash
pip install -r requirements/prod.txt
pip install --upgrade --no-cache-dir -r requirements/rail-django.txt
```

### Project Structure

Rail Django enforces a clean architecture to keep your codebase scalable.

```
my_platform/
├── manage.py           # Django entry point
├── root/               # Core configuration (formerly 'project_name')
│   ├── settings/       # Split settings (base, dev, prod)
│   ├── urls.py         # Global URL routing
│   └── wsgi.py         # WSGI entry point
├── apps/               # Directory for your Django apps
│   └── store/          # Example storefront app
├── requirements/       # Project dependencies (base, dev, prod)
└── Dockerfile          # Production-ready Docker build
```

---

## 3. Core Architecture

### Auto-Schema Generation

At startup, Rail Django scans your `INSTALLED_APPS`. For every `models.Model` it finds, it:

1.  Creates a `DjangoObjectType`.
2.  Generates a `FilterSet` for advanced querying.
3.  Registers `list` and `retrieve` queries.
4.  Generates `create`, `update`, and `delete` mutations (if enabled).

### The Registry System

The `SchemaRegistry` is the brain of the framework. It holds references to all generated types and resolvers. You rarely interact with it directly, but it ensures that circular dependencies between models (e.g., User <-> Group) are resolved gracefully.

### Resolvers & Mutations

- **Queries** use standard Django QuerySets. The framework automatically injects `select_related` and `prefetch_related` based on the requested fields to optimize performance.
- **Mutations** wrap the Django Model `save()` method, ensuring signals (`pre_save`, `post_save`) are fired correctly. They also automatically handle input validation.

---

## 4. Configuration Guide

Your project is configured via `root/settings/base.py`. The primary configuration object is `RAIL_DJANGO_GRAPHQL`.

### Global Settings (`RAIL_DJANGO_GRAPHQL`)

RAIL_DJANGO_GRAPHQL is the global default configuration for all schemas. The
list below shows every supported key with defaults and short clarifications.

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        # App labels to skip (e.g. ["admin"])
        "excluded_apps": [],
        # Model names or "app.Model" labels to skip
        "excluded_models": [],
        # Disable in production to hide schema details
        "enable_introspection": True,
        # Disable in production to remove the UI
        "enable_graphiql": True,
        # Restrict GraphiQL to superusers
        "graphiql_superuser_only": False,
        # Allowlist hosts for GraphiQL (empty = any host)
        "graphiql_allowed_hosts": [],
        # Auto-rebuild on model saves/deletes (dev only)
        "auto_refresh_on_model_change": False,
        # Rebuild schema after migrations
        "auto_refresh_on_migration": True,
        # Build schema at startup
        "prebuild_on_startup": False,
        # Require JWT by default
        "authentication_required": True,
        # Master toggle for pagination fields
        "enable_pagination": True,
        # Use camelCase names when True
        "auto_camelcase": True,
        # Disable login/register/etc mutations
        "disable_security_mutations": False,
        # Enable built-in health/audit mutations
        "enable_extension_mutations": True,
        # Expose model metadata queries for UI builders
        "show_metadata": False,
        # Dotted paths to extra Query classes
        "query_extensions": [],
        # Dotted paths to extra Mutation classes
        "mutation_extensions": [],
        # Allowlist root query fields (None = no filtering)
        "query_field_allowlist": None,
        # Allowlist root mutation fields (None = no filtering)
        "mutation_field_allowlist": None,
        # Allowlist root subscription fields (None = no filtering)
        "subscription_field_allowlist": None,
    },
    "type_generation_settings": {
        # {"app.Model": ["field_a", "field_b"]}
        "exclude_fields": {},
        # Legacy alias for exclude_fields
        "excluded_fields": {},
        # {"app.Model": ["field_a"]} or None for all
        "include_fields": None,
        # {DjangoFieldClass: GrapheneScalar}
        "custom_field_mappings": {},
        # Build filter inputs for types
        "generate_filters": True,
        # Alias for generate_filters
        "enable_filtering": True,
        # CamelCase type field names
        "auto_camelcase": True,
        # Use model help_text as descriptions
        "generate_descriptions": True,
    },
    "query_settings": {
        # Add filter args to list queries
        "generate_filters": True,
        # Add ordering args to list queries
        "generate_ordering": True,
        # Add pagination args to list queries
        "generate_pagination": True,
        # Enable pagination resolver logic
        "enable_pagination": True,
        # Enable ordering resolver logic
        "enable_ordering": True,
        # Use Relay connections instead of lists
        "use_relay": False,
        # Default page size for paginated queries
        "default_page_size": 20,
        # Maximum page size allowed
        "max_page_size": 100,
        # Max buckets for grouping queries
        "max_grouping_buckets": 200,
        # Cap for ordering on Python properties
        "max_property_ordering_results": 2000,
        # {"app.Model": ["slug", "uuid"]}
        "additional_lookup_fields": {},
        # Require Django model permissions for autogenerated queries
        "require_model_permissions": True,
        # Permission codename required to query a model
        "model_permission_codename": "view",
    },
    "mutation_settings": {
        # Auto-generate create mutations
        "generate_create": True,
        # Auto-generate update mutations
        "generate_update": True,
        # Auto-generate delete mutations
        "generate_delete": True,
        # Auto-generate bulk mutations
        "generate_bulk": False,
        # Enable create execution
        "enable_create": True,
        # Enable update execution
        "enable_update": True,
        # Enable delete execution
        "enable_delete": True,
        # Enable bulk execution
        "enable_bulk_operations": True,
        # Expose custom model method mutations
        "enable_method_mutations": True,
        # Require Django model permissions for autogenerated mutations
        "require_model_permissions": True,
        # Permission codenames required per mutation operation
        "model_permission_codenames": {
            "create": "add",
            "update": "change",
            "delete": "delete",
        },
        # Items per bulk operation
        "bulk_batch_size": 100,
        "bulk_include_models": [],
        "bulk_exclude_models": [],
        # {"app.Model": ["field_a"]}
        "required_update_fields": {},
        # Allow nested relation writes
        "enable_nested_relations": True,
        # Per-model nested relation config
        "nested_relations_config": {},
        # Per-field nested relation config
        "nested_field_config": {},
    },
    "subscription_settings": {
        # Enable auto-generated subscriptions
        "enable_subscriptions": True,
        # Toggle model create/update/delete events
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        # Enable filters argument on subscription fields
        "enable_filters": True,
        # Optional allowlist of models for subscriptions
        "include_models": [],
        # Optional blocklist of models for subscriptions
        "exclude_models": [],
    },
    "performance_settings": {
        # Apply select_related/prefetch_related
        "enable_query_optimization": True,
        # Use select_related when possible
        "enable_select_related": True,
        # Use prefetch_related when possible
        "enable_prefetch_related": True,
        # Use .only() to trim columns
        "enable_only_fields": True,
        # Use .defer() for large fields
        "enable_defer_fields": False,
        # Enable DataLoader batching
        "enable_dataloader": True,
        # Batch size for DataLoader
        "dataloader_batch_size": 100,
        # Max allowed query depth
        "max_query_depth": 10,
        # Max allowed query complexity
        "max_query_complexity": 1000,
        # Pre-calc query cost
        "enable_query_cost_analysis": False,
        # Timeout in seconds
        "query_timeout": 30,
    },
    "security_settings": {
        # Enforce auth checks
        "enable_authentication": True,
        # Enforce permission checks
        "enable_authorization": True,
        # Enable allow/deny policy engine
        "enable_policy_engine": True,
        # Cache permission checks per user/context
        "enable_permission_cache": True,
        # Permission cache TTL in seconds
        "permission_cache_ttl_seconds": 300,
        # Emit audit events for permission checks
        "enable_permission_audit": False,
        # Log all permission checks
        "permission_audit_log_all": False,
        # Log deny decisions when audit is enabled
        "permission_audit_log_denies": True,
        # Enable rate limiter
        "enable_rate_limiting": False,
        # Per-minute limit
        "rate_limit_requests_per_minute": 60,
        # Per-hour limit
        "rate_limit_requests_per_hour": 1000,
        # Enforce depth limiting
        "enable_query_depth_limiting": True,
        # Allowlist for security middleware/CORS
        "allowed_origins": ["*"],
        # Enforce CSRF for cookie auth
        "enable_csrf_protection": True,
        # Emit CORS headers
        "enable_cors": True,
        # Enforce field-level permissions
        "enable_field_permissions": True,
        # Reject or strip input fields when write access is missing
        "field_permission_input_mode": "reject",
        # Enforce object-level permissions
        "enable_object_permissions": True,
        # Enable input sanitizer
        "enable_input_validation": True,
        # Enable SQLi detection
        "enable_sql_injection_protection": True,
        # Enable XSS detection
        "enable_xss_protection": True,
        # Allow HTML in inputs
        "input_allow_html": False,
        "input_allowed_html_tags": [
            "p",
            "br",
            "strong",
            "em",
            "u",
            "ol",
            "ul",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
        ],
        "input_allowed_html_attributes": {
            "*": ["class"],
            "a": ["href", "title"],
            "img": ["src", "alt", "width", "height"],
        },
        # None disables length cap
        "input_max_string_length": None,
        # Trim oversized strings instead of erroring
        "input_truncate_long_strings": False,
        # Severity for validation errors
        "input_failure_severity": "high",
        # Max chars to scan
        "input_pattern_scan_limit": 10000,
        # Session timeout in minutes
        "session_timeout_minutes": 30,
        # 10MB
        "max_file_upload_size": 10 * 1024 * 1024,
        "allowed_file_types": [".jpg", ".jpeg", ".png", ".pdf", ".txt"],
    },
    "middleware_settings": {
        # Auth middleware on/off
        "enable_authentication_middleware": True,
        # Log requests
        "enable_logging_middleware": True,
        # Track performance
        "enable_performance_middleware": True,
        # Error handler middleware
        "enable_error_handling_middleware": True,
        # Rate limiter middleware
        "enable_rate_limiting_middleware": True,
        # Input validation middleware
        "enable_validation_middleware": True,
        # Field permission middleware
        "enable_field_permission_middleware": True,
        # CORS middleware
        "enable_cors_middleware": True,
        # Log GraphQL queries
        "log_queries": True,
        # Log GraphQL mutations
        "log_mutations": True,
        # Log non-root field resolutions (very verbose)
        "log_field_level": False,
        # Log introspection fields (__schema, __type, __typename)
        "log_introspection": False,
        # Log GraphQL errors
        "log_errors": True,
        # Log performance data
        "log_performance": True,
        # Slow query threshold
        "performance_threshold_ms": 1000,
        # Enforce complexity
        "enable_query_complexity_middleware": True,
    },
    "error_handling": {
        # Include detailed errors
        "enable_detailed_errors": False,
        # Log errors
        "enable_error_logging": True,
        # Report errors to external services
        "enable_error_reporting": True,
        # Sentry integration toggle
        "enable_sentry_integration": False,
        # Hide internal details from clients
        "mask_internal_errors": True,
        # Include stack traces
        "include_stack_trace": False,
        # Prefix for error codes
        "error_code_prefix": "RAIL_GQL",
        # Max error message length
        "max_error_message_length": 500,
        # Categorize errors
        "enable_error_categorization": True,
        # Track error metrics
        "enable_error_metrics": True,
        # Log level for error events
        "log_level": "ERROR",
    },
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
    },
    "monitoring_settings": {
        # Toggle metrics collection
        "enable_metrics": False,
        # Metrics backend name
        "metrics_backend": "prometheus",
    },
    "schema_registry": {
        # Enable schema registry discovery
        "enable_registry": False,
        # Python packages to scan for schemas
        "auto_discover_packages": [],
    },
}
```

### Schema Management API

The REST endpoints under `/api/v1/` require a JWT access token and admin
permissions.

```python
GRAPHQL_SCHEMA_API_REQUIRED_PERMISSIONS = ["rail_django.manage_schema"]
GRAPHQL_SCHEMA_API_RATE_LIMIT = {
    "enable": True,
    "window_seconds": 60,
    "max_requests": 60,
}
```

### Multi-Schema Configuration

For complex apps, you often need different APIs for different consumers (e.g., Public Auth, Mobile App, Admin Panel).

```python
# settings.py

RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "auth": {
        # Public endpoint for login/register
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False,
            "query_field_allowlist": ["me"],
            "mutation_field_allowlist": ["login", "register"],
        },
        # Disable unrelated mutations
        "mutation_settings": {
            "generate_create": False,
            "generate_update": False,
        }
    },
    "default": {
        # Main API for authenticated users
        "schema_settings": {
            "authentication_required": True,
        }
    },
    "admin": {
        # Internal tools API
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": True, # Allow admins to explore
        },
        "mutation_settings": {
            "enable_bulk_operations": True,
        }
    }
}
```

This creates distinct endpoints (configured in `urls.py` automatically):

- `/graphql/auth/`
- `/graphql/gql/`
- `/graphql/admin/`

#### How schemas are registered

Rail Django registers schemas from two sources, in this order:

1.  App discovery: each installed app is scanned for `schemas.py`,
    `graphql_schema.py`, `schema.py`, or `graphql/schema.py`. If a module exposes
    `register_schema(registry)`, it is called.
2.  Settings fallback: any entries in `RAIL_DJANGO_GRAPHQL_SCHEMAS` that are not
    already registered are added automatically.

By default, the starter template registers schemas only from
`RAIL_DJANGO_GRAPHQL_SCHEMAS`. The `schemas.py` and `graphql_schema.py` files
ship as no-op stubs unless you add `register_schema(...)` yourself. Schemas can
still appear even if `register_schema(...)` is empty, as long as they exist in
`RAIL_DJANGO_GRAPHQL_SCHEMAS`.

To disable a schema:

- Remove the schema key from `RAIL_DJANGO_GRAPHQL_SCHEMAS`, or set
  `"enabled": False`.
- If you also register it in `schemas.py`, remove it there too.

The registry is cached once per process. Restart the server (or call
`schema_registry.clear()` in a Django shell) to pick up changes.

---

## 5. Data Modeling & API Design

### Defining Models

Write standard Django models. Rail Django does the rest.

```python
# apps/store/models.py
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
```

### The `graphql_meta` Class

To customize how a specific model appears in the API, define an inner
`GraphQLMeta` (or legacy `GraphqlMeta`) class on the model. This is the most
direct way to control field exposure, filtering, ordering, and access guards.

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    # ... fields ...

    # Use GraphQLMeta or GraphqlMeta as the inner class name.
    class GraphqlMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            exclude=["cost_price", "supplier_notes"],
            read_only=["sku"],
        )
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={
                "price": GraphQLMetaConfig.FilterField(lookups=["gt", "lt", "between"]),
                "name": GraphQLMetaConfig.FilterField(
                    lookups=["icontains", "istarts_with"]
                ),
            },
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price"],
            default=["-price"],
        )
```

You can also tag data classifications and reuse policy bundles:

```python
class Customer(models.Model):
    email = models.EmailField()
    salary = models.DecimalField(max_digits=10, decimal_places=2)

    class GraphQLMeta(GraphQLMetaConfig):
        classifications = GraphQLMetaConfig.Classification(
            model=["pii"],
            fields={"salary": ["financial"]},
        )
```

---

## 6. Querying & Filtering

### Standard Queries

Rail Django generates plural (list) and singular (retrieve) fields.

**Request:**

```graphql
query {
  products(first: 10) {
    id
    name
    price
  }
  product(id: "123") {
    name
  }
}
```

### Advanced Filtering

Rail Django uses a nested filter syntax (Prisma/Hasura style) with typed
per-field inputs.

**Exact Match:**
`products(where: { isActive: { eq: true } })`

**String Search (Case-Insensitive):**
`products(where: { name: { icontains: "phone" } })`

**Range Filters:**
`products(where: { price: { between: [100, 500] } })`

**Related Fields:**
`products(where: { categoryRel: { name: { icontains: "Electronics" } } })`

### Pagination Strategies

By default, Rail Django uses Offset Pagination (limit/offset) which is simpler for most frontend frameworks.

**Request:**

```graphql
query {
  products(offset: 0, limit: 20) {
    id
    name
  }
}
```

_To enable Relay-style (Cursor) pagination, update `query_settings` in `settings.py`:_

```python
"query_settings": {
    "use_relay": True,
}
```

### Ordering

Sort results by any field.
`products(orderBy: ["-price", "name"])` (High to low price, then A-Z)

---

## 7. Mutations & Operations

### Auto-CRUD Mutations

Enabled by default.

**Create:**

```graphql
mutation {
  createProduct(input: { name: "New Item", price: 99.99 }) {
    ok
    product {
      id
      name
    }
    errors
  }
}
```

**Update:**

```graphql
mutation {
  updateProduct(id: "123", input: { price: 89.99 }) {
    ok
    product {
      price
    }
  }
}
```

Note: `id` is required as the top-level mutation argument. `input.id` is optional
and kept for backwards compatibility.

**Delete:**

```graphql
mutation {
  deleteProduct(id: "123") {
    ok
  }
}
```

### Custom Mutations

When you need logic beyond CRUD, define a method on your model and expose it.

**Model:**

```python
class Product(models.Model):
    # ...
    def apply_discount(self, percentage):
        self.price = self.price * (1 - percentage / 100)
        self.save()
        return self
```

**Settings/Meta:**
(Currently, custom mutation logic usually requires writing a manual Graphene mutation or using specific Rail Django decorators if available in your version. Check `rail_django.generators.mutations` for advanced method mapping).

### Bulk Operations

Enable `generate_bulk: True` in `mutation_settings`.

```graphql
mutation {
  bulkDeleteProduct(ids: ["1", "2", "3"]) {
    count
  }
}
```

---

## 8. Security & Permissions

### Authentication Flow (JWT)

Rail Django includes a full JWT implementation.

1.  **Login:**
    POST to `/api/auth/` (if configured) or your main endpoint:

    ```graphql
    mutation {
      login(username: "user", password: "pwd") {
        token
        refreshToken
        user {
          username
        }
      }
    }
    ```

2.  **Authenticate Requests:**
    Add header: `Authorization: Bearer <your_token>`

    If you use cookie-based JWTs, keep CSRF protection enabled and set:
    `JWT_ALLOW_COOKIE_AUTH=True`, `JWT_ENFORCE_CSRF=True`.

3.  **Refresh Token:**
    ```graphql
    mutation {
      refreshToken(refreshToken: "<refresh_token>") {
        token
      }
    }
    ```

### Role-Based Access Control (RBAC)

Define roles and assign them to users.

**Usage in Code:**

```python
from rail_django.security import require_role

@require_role("manager")
def resolve_financial_report(root, info):
    return generate_report()
```

For contextual permissions (`*_own`, `*_assigned`), ensure the check has object context:

```python
from rail_django.security import PermissionContext, role_manager

context = PermissionContext(user=request.user, object_instance=project)
role_manager.has_permission(request.user, "project.update_own", context)
```

You can also define role definitions per app in `meta.yaml` (created by
`startapp`, with `meta.json` still supported). The loader scans installed apps
at startup and registers roles alongside code-defined RBAC.

**Detailed example (`apps/store/meta.yaml`):**

```yaml
roles:
  catalog_viewer:
    description: Read-only access to the catalog.
    role_type: functional
    permissions:
      - store.view_product
      - store.view_category
  catalog_editor:
    description: Create and update catalog entries.
    role_type: business
    permissions:
      - store.view_product
      - store.add_product
      - store.change_product
    parent_roles:
      - catalog_viewer
  catalog_admin:
    description: Full control over catalog data.
    role_type: system
    permissions:
      - store.*
    parent_roles:
      - catalog_editor
    is_system_role: true
    max_users: 5
models: {}
```

Notes:

- Place the file at the app root (for example `apps/store/meta.yaml`).
- The loader runs on startup; restart the server to pick up changes.
- Roles are additive and do not override built-in system roles or GraphQLMeta roles with the same name.

You can also declare full GraphQLMeta configuration in `meta.yaml` per app.
This mirrors the code-based GraphQLMeta API, including filtering, field
exposure, ordering, resolvers, access guards, and classifications.

Example (`apps/store/meta.yaml`):

```yaml
models:
  Product:
    fields:
      exclude:
        - internal_notes
      read_only:
        - created_at
    filtering:
      quick:
        - name
        - category__name
      fields:
        status:
          lookups:
            - eq
            - in
          choices:
            - draft
            - active
        created_at:
          - gte
          - lte
    ordering:
      allowed:
        - name
        - created_at
      default:
        - -created_at
    access:
      operations:
        list:
          roles:
            - catalog_viewer
        update:
          roles:
            - catalog_admin
      fields:
        - field: cost_price
          access: read
          visibility: hidden
          roles:
            - catalog_admin
```

Notes:

- Use `models` to map model names (or `app_label.Model`) to configs.
- Dotted paths in resolver or guard condition values are imported as callables.
- If a model defines `GraphQLMeta` in code, it takes precedence over JSON.

### Field-Level Security

You can hide fields dynamically based on who is asking.

**Example: Masking Emails**
In `graphql_meta`:

```python
field_permissions={
    "email": {
        "roles": ["support"],
        "visibility": "masked",
        "mask_value": "user@***.com"
    }
}
```

A generic user will see `null` or receive a permission error. A support user sees the masked value. An admin sees the full value.

Field permission enforcement runs in Graphene middleware. Enable it and decide how to handle disallowed inputs:

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

### Policy Engine and Explain API

The policy engine lets you define explicit allow/deny rules with precedence. Deny wins when priorities tie.

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
    )
)
```

Use the explain query to debug decisions (and wire audit logging if needed):

```graphql
query {
  explainPermission(
    permission: "project.update_own"
    modelName: "store.Product"
    objectId: "123"
  ) {
    allowed
    reason
    policyDecision {
      name
      effect
      priority
      reason
    }
  }
}
```

### Input Sanitization

The library automatically sanitizes inputs to prevent XSS. It strips dangerous tags (`<script>`, `<iframe>`) from string inputs before they reach your resolvers.

---

## 9. Extensions System

### Audit Logging

Tracks who did what.

**Events Logged:**

- Login/Logout
- Failed Login (Brute force detection)
- Password Changes
- Permission Denials

**Querying Logs:**
The logs are stored in `AuditEventModel`. You can query them using standard Django ORM:

```python
from rail_django.extensions.audit.models import get_audit_event_model
AuditEvent = get_audit_event_model()
events = AuditEvent.objects.filter(event_type="auth.login.failure")
```

### Webhooks

Send model create/update/delete events to external systems.

Configuration lives in `root/webhooks.py` and is wired into
`RAIL_DJANGO_GRAPHQL["webhook_settings"]`.

```python
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    "endpoints": [
        {
            "name": "orders",
            "url": "https://example.com/webhooks/orders",
            "include_models": ["store.Order"],
        },
        {
            "name": "customers",
            "url": "https://example.com/webhooks/customers",
            "include_models": ["crm.Customer"],
            "auth_token_path": "rail_django.webhooks.auth.fetch_auth_token",
            "auth_url": "https://example.com/oauth/token",
            "auth_payload": {"client_id": "id", "client_secret": "secret"},
        },
    ],
    "events": {"created": True, "updated": True, "deleted": True},
}
```

Use `include_models`/`exclude_models` on each endpoint to route specific models.

### Data Exporting (Excel/CSV)

Don't write CSV writers manually. Use the export endpoint.

**Endpoint:** `POST /api/v1/export/`
**Payload:**

```json
{
  "app_name": "store",
  "model_name": "Product",
  "file_extension": "xlsx",
  "fields": [
    "name",
    "category.name",
    { "accessor": "price", "title": "Unit Price" }
  ],
  "max_rows": 10000,
  "variables": { "is_active": true }
}
```

This returns a binary stream of the generated Excel file.

Guardrails (default-deny allowlists, row caps, filter/order limits, rate limiting)
are configured via `RAIL_DJANGO_EXPORT` in settings. Async jobs and export templates
are also configured there. Use a shared cache backend when async exports are enabled.

### BI Reporting & Dashboards

Turn your Django models into analytical datasets without writing SQL or Graphene resolvers.

1.  **Define a Dataset:**
    Create a `ReportingDataset` via the Django Admin or code.

    ```python
    from rail_django.extensions.reporting import ReportingDataset

    ReportingDataset.objects.create(
        code="sales_overview",
        title="Monthly Sales",
        source_app_label="store",
        source_model="Order",
        dimensions=[
            {"field": "created_at", "transform": "trunc:month", "name": "month"},
            {"field": "customer__country", "name": "country"}
        ],
        metrics=[
            {"field": "total_amount", "aggregation": "sum", "name": "revenue"},
            {"field": "id", "aggregation": "count", "name": "order_count"}
        ]
    )
    ```

2.  **Query via GraphQL:**
    The framework exposes `reportingDataset(code: "sales_overview")` query.

    ```graphql
    query {
      reportingDataset(code: "sales_overview") {
        preview(limit: 100)
      }
    }
    ```

3.  **Postgres Accelerators:**
    If you use PostgreSQL, the engine automatically unlocks advanced aggregations:
    - `list`: Returns a list of values (`ArrayAgg`).
    - `concat`: Returns a comma-separated string.
    - `percentile:0.95`: Calculates the 95th percentile.
    - `stddev` / `variance`: Statistical analysis.
    - **Full Text Search:** The "quick search" box uses native Postgres vector search instead of slow `LIKE` queries.

### Health Monitoring

Expose a health check for Kubernetes or Load Balancers.

**Query:**

```graphql
query {
  health {
    healthStatus {
      overallStatus # "healthy", "degraded", "unhealthy"
      components {
        databases {
          status
          message
        }
      }
      systemMetrics {
        cpuUsagePercent
        memoryUsagePercent
      }
    }
  }
}
```

### Background Tasks

Run long-running mutations asynchronously and track their status.

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

GraphQL example:

```graphql
mutation {
  generateReport(datasetId: "123") {
    taskId
    status
  }
}

query {
  task(id: "abc-123") {
    status
    progress
    result
    error
  }
}
```

REST polling:

`GET /api/v1/tasks/<uuid>/`

### Subscriptions (Real-time)

Auto-generate GraphQL subscriptions for per-model create/update/delete events.

1.  **Install dependencies:**
    `pip install -r requirements/base.txt`

2.  **Backend config (already included in the template):**

    ```python
    INSTALLED_APPS = [
        "daphne",
        "channels",
        # ...
    ]

    ASGI_APPLICATION = "root.asgi.application"
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }

    RAIL_DJANGO_GRAPHQL = {
        "subscription_settings": {
            "enable_subscriptions": True,
            "enable_create": True,
            "enable_update": True,
            "enable_delete": True,
            "enable_filters": True,
            "include_models": [],
            "exclude_models": [],
        },
    }
    ```

3.  **WebSocket routing (already included in the template):**
    Use the same schema name you expose at `/graphql/` (default: `gql`).

    ```python
    # root/asgi.py
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter
    from django.core.asgi import get_asgi_application
    from django.urls import path
    from rail_django.extensions.subscriptions import get_subscription_consumer

    django_asgi_app = get_asgi_application()

    application = ProtocolTypeRouter({
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter([
            path("graphql/", get_subscription_consumer("gql")),
            path("graphql/graphiql/", get_subscription_consumer("gql")),
        ])),
    })
    ```

4.  **Production note:**
    In-memory channel layers are per-process. If you run multiple workers, use a
    channel layer that supports multi-process messaging.

5.  **Subscribe from GraphQL:**
    Subscription field names are camelCase (for example `categoryCreated`).

    ```graphql
    subscription {
      categoryCreated(filters: { name: { icontains: "book" } }) {
        event
        id
        node {
          id
          name
        }
      }
    }
    ```

6.  **Apollo React client example:**

    ```tsx
    import {
      ApolloClient,
      InMemoryCache,
      HttpLink,
      split,
    } from "@apollo/client";
    import { WebSocketLink } from "@apollo/client/link/ws";
    import { getMainDefinition } from "@apollo/client/utilities";

    const httpLink = new HttpLink({ uri: "/graphql/gql/" });
    const wsLink = new WebSocketLink({
      uri: "ws://localhost:8000/graphql/",
      options: { reconnect: true },
    });

    const link = split(
      ({ query }) => {
        const def = getMainDefinition(query);
        return (
          def.kind === "OperationDefinition" && def.operation === "subscription"
        );
      },
      wsLink,
      httpLink
    );

    export const client = new ApolloClient({
      link,
      cache: new InMemoryCache(),
    });
    ```

### Multi-Factor Authentication (MFA)

Secure your high-value users.

1.  **Setup:**
    `setupTotp(deviceName: "My iPhone")` -> Returns QR Code URL.
2.  **Verify:**
    `verifyTotp(deviceId: 1, token: "123456")` -> Activates device.
3.  **Enforce:**
    Middleware checks `user.mfa_devices.exists()`. If enforced, it blocks other mutations until verified.

### PDF Templating Engine

Turn Django models into PDFs using HTML/CSS templates.

1.  **Create Template:** `templates/pdf/invoice.html`
2.  **Decorate Model:**

    ```python
    from rail_django.extensions.templating import model_pdf_template

    class Order(models.Model):
        @model_pdf_template(content="pdf/invoice.html")
        def download_invoice(self):
            return {"items": self.items.all()}
    ```

3.  **Download:** `GET /api/templates/store/order/download_invoice/<pk>/`
4.  **Function-based Template (optional):**

    ```python
    from rail_django.extensions.templating import pdf_template

    @pdf_template(content="pdf/invoice.html", url="invoices/print")
    def invoice_pdf(request, order_id):
        return {"order_id": order_id}
    ```

    Ensure the module is imported at startup (e.g., in `apps.py` ready) so the
    decorator runs and registers the template.

5.  **Async Jobs (optional):**
    `GET /api/templates/.../<pk>/?async=true` returns `job_id`, `status_url`, `download_url`.
    Enable via `RAIL_DJANGO_GRAPHQL_TEMPLATING["async_jobs"]["enable"] = True`.
6.  **Catalog Endpoint:**
    `GET /api/templates/catalog/` lists available templates + metadata.
7.  **Preview Endpoint (dev):**
    `GET /api/templates/preview/<template_path>/<pk>/` returns HTML.
    Enable via `RAIL_DJANGO_GRAPHQL_TEMPLATING["enable_preview"] = True`.
8.  **Management Command:**
    `python manage.py render_pdf <template_path> --pk <pk> --output out.pdf`
9.  **Low-level Helpers:**
    `render_pdf(...)` or `PdfBuilder()` for programmatic rendering.

**Configuration (`RAIL_DJANGO_GRAPHQL_TEMPLATING`):**
Use CSS to style your PDFs (page size, margins).

```python
"default_template_config": {
    "page_size": "A4",
    "margin": "2cm",
    "font_family": "Helvetica"
}
```

Additional controls include renderer selection, URL fetcher allowlists, rate limiting,
async job storage, post-processing (watermarks, page stamps, encryption, signatures),
and catalog/preview toggles.

Optional dependencies:

- `pypdf` for watermark overlays and encryption.
- `pyhanko` for digital signatures.
- `wkhtmltopdf` binary for the wkhtml renderer.

---

### Model Schema Introspection (Metadata V2)

Enable frontends to automatically generate forms, tables, and detail views using rich model metadata exposed via GraphQL.

**Enable in settings:**

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "show_metadata": True,  # Enables both v1 and v2 metadata queries
    }
}
```

#### Available Queries

**1. Get Complete Model Schema:**

```graphql
query {
  modelSchema(app: "store", model: "Product") {
    app
    model
    verboseName
    verboseNamePlural
    primaryKey
    ordering

    # All fields with rich classification
    fields {
      name
      verboseName
      fieldType # CharField, IntegerField, ForeignKey, etc.
      graphqlType # String, Int, ID, etc.
      required
      nullable
      editable
      unique
      maxLength
      choices {
        value
        label
      }

      # Classification flags for frontend widget selection
      isDate
      isDatetime
      isNumeric
      isBoolean
      isText
      isRichText # TextField - frontend can use rich editor
      isFile
      isImage
      isJson
      isFsmField # django-fsm state field
      # FSM transitions (if isFsmField)
      fsmTransitions {
        name # Method name to call
        source # Source states ["pending", "confirmed"]
        target # Target state
        label # Human-readable action name
      }

      # Permissions for current user
      readable
      writable
      visibility # VISIBLE, MASKED, HIDDEN
    }

    # Relationships
    relationships {
      name
      relatedApp
      relatedModel
      relationType # FOREIGN_KEY, MANY_TO_MANY, REVERSE_FK, etc.
      isReverse
      isToOne # FK or O2O
      isToMany # M2M or reverse
      required
      readable
      writable
    }

    # Available filters
    filters {
      fieldName
      fieldLabel
      isNested
      relatedModel
      options {
        name # Filter operator name (e.g., "gte")
        lookup # Lookup type (e.g., "gte")
        helpText # French help text
        choices {
          value
          label
        }
      }
    }

    # Available mutations
    mutations {
      name # e.g., "createProduct"
      operation # CREATE, UPDATE, DELETE, METHOD
      allowed # Permission check result
      requiredPermissions
    }

    # Model-level permissions
    permissions {
      canList
      canCreate
      canUpdate
      canDelete
      canExport
    }

    # Optional field grouping hints (from GraphQLMeta)
    fieldGroups {
      key
      label
      fields
    }

    # PDF templates (from @model_pdf_template)
    templates {
      key
      title
      endpoint
    }

    metadataVersion
    customMetadata
  }
}
```

**2. List Available Models:**

```graphql
query {
  availableModelsV2(app: "store") {
    app
    model
    verboseName
    verboseNamePlural
  }
}
```

**3. Get All Schemas for an App:**

```graphql
query {
  appSchemas(app: "store") {
    model
    verboseName
    fields {
      name
      fieldType
    }
  }
}
```

#### Frontend Integration Example

The frontend receives rich data and decides how to render:

```typescript
// TypeScript example
interface FieldSchema {
  name: string;
  verboseName: string;
  fieldType: string;
  required: boolean;
  isDate: boolean;
  isNumeric: boolean;
  isRichText: boolean;
  isFsmField: boolean;
  choices?: { value: string; label: string }[];
  fsmTransitions?: { name: string; label: string; target: string }[];
}

function selectWidget(field: FieldSchema): string {
  if (field.choices?.length) return "select";
  if (field.isFsmField) return "state-badge";
  if (field.isRichText) return "rich-text-editor";
  if (field.isDate) return "date-picker";
  if (field.isNumeric) return "number-input";
  return "text-input";
}

function buildForm(schema: ModelSchema) {
  return schema.fields
    .filter((f) => f.editable && f.writable)
    .map((field) => ({
      name: field.name,
      label: field.verboseName,
      widget: selectWidget(field),
      required: field.required,
      choices: field.choices,
    }));
}
```

#### Customizing Metadata via GraphQLMeta

Add hints for the frontend in your model:

```python
class Order(models.Model):
    reference = models.CharField(max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    notes = models.TextField(blank=True)

    class GraphQLMeta:
        # Group fields for frontend organization
        field_groups = [
            {"key": "main", "label": "Informations principales", "fields": ["reference", "customer", "status"]},
            {"key": "details", "label": "Détails", "fields": ["notes"]},
        ]

        # Custom metadata passed through to frontend
        custom_metadata = {
            "icon": "shopping-cart",
            "color": "#4A90D9",
        }
```

#### Metadata V1 vs V2

| Feature              | V1 (`modelMetadata`) | V2 (`modelSchema`)            |
| -------------------- | -------------------- | ----------------------------- |
| Query count          | 3 separate queries   | 1 unified query               |
| Field classification | Limited              | 15+ boolean flags             |
| FSM transitions      | ❌                   | ✅ Full support               |
| Field groups         | ❌                   | ✅ Via GraphQLMeta            |
| Custom metadata      | ❌                   | ✅ Pass-through               |
| Relationship details | Basic                | Complete (on_delete, through) |

Both APIs remain available simultaneously for gradual migration.

---

## 10. Performance Tuning

### Query Optimization

The N+1 problem is the enemy of GraphQL.
Rail Django automatically uses `select_related` for ForeignKeys and `prefetch_related` for ManyToMany fields when you query nested data.

**Example:**
`query { products { category { name } } }`
The framework sees you asked for `category` and adds `.select_related('category')` to the underlying queryset automatically.

### DataLoader

For complex cases where auto-optimization fails (e.g. calculated properties or cross-service calls), enable DataLoaders in settings.
`"enable_dataloader": True`

### Performance Middleware

Enable request-level metrics with:
`GRAPHQL_PERFORMANCE_ENABLED=True`
Optional headers: `GRAPHQL_PERFORMANCE_HEADERS=True`

### Complexity Limiting

Prevent malicious users from crashing your server with massive queries.

**Settings:**

- `max_query_depth`: 10 (e.g., `author { posts { author { posts ... } } }`)
- `max_query_complexity`: 2000 points.
  - Simple field = 1 point
  - Relationship = 5 points
  - List = 10 points \* limit

---

## 11. Deployment & DevOps

### Docker Configuration

The project comes with a multi-stage `Dockerfile`.

**Structure:**

- **Builder Stage:** Compiles Python dependencies and wheels.
- **Final Stage:** Minimal slim image, copies wheels, installs runtime deps.

**Environment Variables:**
Ensure these are set in production (see `.env.example`):

- `DJANGO_SECRET_KEY`: Must be random and secret.
- `DJANGO_DEBUG`: **Must** be `False`.
- `DJANGO_ALLOWED_HOSTS`: List of valid domains.
- `DJANGO_SETTINGS_MODULE`: `root.settings.production`
- `DATABASE_URL`: Connection string for PostgreSQL.
- `CACHE_PATH`: Path for the shared cache backend (file-based).
- `LOG_PATH`: Host path for log files (absolute or relative to `deploy/docker/`).
- Optional: `JWT_ALLOW_COOKIE_AUTH`, `JWT_ENFORCE_CSRF` (if using cookie auth).
- Optional: `GRAPHQL_PERFORMANCE_ENABLED` (enable request metrics).
- Optional: `EXPORT_MAX_ROWS`, `EXPORT_STREAM_CSV` (if wiring export guardrails).
- Optional: `DEPLOY_REFRESH_DEPS` (force dependency rebuild on deploy).

### Production Checklist

1.  [ ] **HTTPS:** Ensure SSL is enabled (use the container Nginx or a load balancer).
2.  [ ] **Secrets:** Move `.env` vars to a secure secret manager.
3.  [ ] **Static Files:** Ensure `collectstatic` runs during build/deploy.
4.  [ ] **Migrations:** Run `migrate` on release.
5.  [ ] **MFA:** Enforce MFA for staff users.
6.  [ ] **Logging:** Configure Sentry or similar for error tracking.

### Troubleshooting

**Error: "Signature has expired"**

- **Cause:** JWT token is too old.
- **Fix:** Use `refreshToken` mutation or login again. Check `JWT_ACCESS_TOKEN_LIFETIME`.

**Error: "Field 'xyz' not found"**

- **Cause:** You might have excluded it in `graphql_meta` or `excluded_fields`.
- **Fix:** Check permissions and visibility settings.

**Performance is slow**

- **Check:** Are you querying a deep relationship without optimization?
- **Fix:** Inspect SQL queries using `django-debug-toolbar` (in dev) or enable `log_performance` middleware.

---

## 12. Manual Deployment Guide

This guide explains how to manually deploy your `rail-django` application using the provided Docker and Nginx configurations, connecting to your external database machine.

### Prerequisites

1.  **Docker & Docker Compose** installed on the application server.
2.  **External Database**: A PostgreSQL database running on a separate machine, accessible from your application server.
3.  **Domain Name / Internal DNS**: Configured to point to your VM's IP address (e.g., `app.internal.corp`).

### 1. Environment Configuration

Copy the `.env.example` file to `.env` in your project root and update the variables:

```bash
cp .env.example .env
nano .env
```

**Key variables to set:**

- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY`: A long, random string.
- `DATABASE_URL`: Pointing to your external machine (e.g., `postgres://user:pass@192.168.1.50:5432/my_db`). Also used by the backup service.
- `DJANGO_ALLOWED_HOSTS`: Your internal domain (e.g., `app.internal.corp`) or IP.
- `DJANGO_SETTINGS_MODULE`: `root.settings.production`
- `LOG_PATH`: Host path for log files (absolute or relative to `deploy/docker/`).
- Optional: `DEPLOY_REFRESH_DEPS` (force dependency rebuild on deploy).

### 2. Deployment Steps

Run these commands from your project root:

#### A. Build and Start Services

This will build the Python image and start the Web, Nginx, and Backup containers.

```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

#### B. Run Migrations

Apply database schema changes to your external database:

```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```

#### C. Collect Static Files

Prepare CSS, JS, and images for Nginx to serve:

```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py collectstatic --no-input
```

#### D. Create Superuser (Optional)

```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py createsuperuser
```

### 3. Directory Structure

- **`deploy/docker/`**: Contains the Dockerfile and Compose configuration.
- **`deploy/nginx/`**: Contains the Nginx reverse proxy configuration.
- **`backups/`**: Database backups will be stored here automatically every 24h (defined in `.env`).

### 4. Maintenance

#### Viewing Logs

```bash
docker-compose -f deploy/docker/docker-compose.yml logs -f
```
Log files are also written to `/home/app/web/logs` inside the container. If you
set `LOG_PATH`, read them directly on the host.

#### Stopping the Application

```bash
docker-compose -f deploy/docker/docker-compose.yml down
```

#### Updating the Application

1. Pull your latest code changes.
2. Re-run the build and migration steps:

```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```
Set `DEPLOY_REFRESH_DEPS=1` or use `deploy/deploy.sh --refresh-deps` when you
need to rebuild base dependencies. The `rail-django` Git install is refreshed
on every build.

### 5. Security Recommendations

1.  **SSL/TLS**: Mandatory. Use company-issued certificates or self-signed certs for internal traffic.
2.  **Firewall**: Configure `ufw` on your Ubuntu VM to allow traffic only from trusted internal subnets.
    ```bash
    ufw allow from 10.0.0.0/8 to any port 443
    ufw allow ssh
    ufw enable
    ```
3.  **Secrets**: Never commit your `.env` file to version control.
4.  **Updates**: Keep the VM OS updated (`apt update && apt upgrade`).

### 6. Setup HTTPS (Internal Network / Enterprise)

Since this server is inside a private company network, you cannot use standard Let's Encrypt challenges. Terminate TLS in the bundled Nginx container and mount your certificates into it.

#### Step 1: Obtain Certificates

You have two options:

**Option A: Official Company Certificate (Recommended)**
Ask your IT/Security team for the SSL certificate for your internal domain (e.g., `app.corp.local`). Place the files here:

- `deploy/nginx/certs/server.crt`
- `deploy/nginx/certs/server.key`

**Option B: Self-Signed Certificate (For Testing)**
If you don't have an official cert, generate a self-signed one:

```bash
mkdir -p deploy/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/nginx/certs/server.key \
  -out deploy/nginx/certs/server.crt \
  -subj "/CN=app.internal.corp"
```

#### Step 2: Configure Nginx

Update `deploy/nginx/default.conf` and set `server_name` to your internal domain or IP. The template already redirects HTTP to HTTPS and listens on port 443.

#### Step 3: Activate

```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

---

**Rail Django** - _Build faster, scale better._

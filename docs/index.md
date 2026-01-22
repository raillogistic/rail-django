# Rail Django Documentation

Welcome to the official documentation for **Rail Django**, a production-ready GraphQL framework for Django.

Rail Django wraps [Graphene-Django](https://docs.graphene-python.org/projects/django/en/latest/) to provide a battery-included experience with automatic schema generation, enhanced security, and enterprise-grade features.

## 📚 Table of Contents

### Getting Started
*   [**Installation**](getting-started/installation.md): Set up Rail Django in your environment.
*   [**Quickstart**](getting-started/quickstart.md): Build your first API in under 5 minutes.
*   [**Architecture**](getting-started/architecture.md): Understand how Rail Django works under the hood.

### Core Concepts
*   [**Models & Schema**](core/models-and-schema.md): How Django models map to GraphQL types.
*   [**Queries**](core/queries.md): Fetching data.
*   [**Filtering**](core/filtering.md): Deep dive into the `where` argument, operators, and searching.
*   [**Mutations**](core/mutations.md): Creating, updating, and deleting data.
*   [**Configuration**](core/configuration.md): Global settings and project configuration.
*   [**Performance**](core/performance.md): Optimization, caching, and N+1 prevention.

### Security
*   [**Authentication**](security/authentication.md): Identity verification strategies.
*   [**Permissions (RBAC)**](security/permissions.md): Role-based and field-level access control.
*   [**Validation**](security/validation.md): Input validation and data integrity.

### Extensions
*   [**Audit Logging**](extensions/audit-logging.md): Track who did what and when.
*   [**Webhooks**](extensions/webhooks.md): Event-driven architecture and webhooks.
*   [**Exporting**](extensions/exporting.md): Data export capabilities (Excel, CSV).
*   [**Templating**](extensions/templating.md): PDF and Excel generation.
*   [**Tasks**](extensions/tasks.md): Background task management.
*   [**Subscriptions**](extensions/subscriptions.md): Real-time events.
*   [**Multitenancy**](extensions/multitenancy.md): SaaS-ready data isolation.
*   [**Health Checks**](extensions/health-checks.md): System health monitoring.
*   [**Observability**](extensions/observability.md): Tracing and metrics with OpenTelemetry/Sentry.

### Operations
*   [**Deployment Guide**](operations/deployment.md): Production best practices.

### Reference
*   [**API Reference**](reference/api.md): Public API documentation.
*   [**CLI Reference**](reference/cli.md): `rail-admin` command usage.
*   [**GraphQLMeta**](reference/meta.md): The comprehensive guide to `class GraphQLMeta`.

## 📂 Project Structure

A standard Rail Django project follows a clean, production-ready structure:

```text
my_project/
├── .env                  # Environment variables (secrets, DB URL)
├── manage.py             # Django task runner entry point
├── apps/                 # Container for your custom Django apps
│   └── store/            # Example app
│       ├── meta.yaml     # Role & permission definitions
│       ├── models.py     # Database models
│       └── ...
├── root/                 # Project configuration root (formerly project_name)
│   ├── settings/         # Split settings environment
│   │   ├── base.py       # Core settings (RAIL_DJANGO_GRAPHQL config)
│   │   ├── dev.py        # Development overrides
│   │   └── prod.py       # Production security overrides
│   ├── graphql_schema.py # Custom schema definitions
│   ├── schemas.py        # Schema registration
│   ├── urls.py           # Global URL routing
│   ├── webhooks.py       # Webhook configuration
│   └── wsgi.py           # Server entry point
├── deploy/               # Deployment configuration
│   ├── docker/           # Docker Compose & Dockerfile
│   └── nginx/            # Nginx reverse proxy config
├── requirements/         # Dependency management
│   ├── base.txt          # Core libraries
│   ├── dev.txt           # Testing & linting tools
│   └── prod.txt          # Production servers (gunicorn)
└── logs/                 # Application log files
```

## 📦 Library Structure

For contributors and those curious about the framework internals (`rail_django/`):

```text
rail_django/
├── api/                  # REST API endpoints
│   └── views/            # Views for Schema Registry, Exports, and tasks
├── bin/                  # CLI Entry Points
│   └── rail_admin.py     # The `rail-admin` scaffolding tool
├── conf/                 # Configuration & Templates
│   ├── app_template/     # Template used by `startapp`
│   ├── project_template/ # Template used by `startproject`
│   └── framework_settings.py # Base settings imported by projects
├── core/                 # Core Framework Logic
│   ├── registry/         # Schema Registry (handles Model <-> Type mapping)
│   ├── settings/         # Settings parsing & configuration dataclasses
│   └── schema/           # Schema Builder, Versioning, and Snapshots
├── extensions/           # Pluggable Feature Modules
│   ├── audit/            # Audit Logging system
│   ├── auth/             # JWT Authentication & Security mutations
│   ├── exporting/        # Excel/CSV Export engine
│   ├── health/           # Health Check endpoints
│   ├── metadata_v2/      # Frontend Metadata Introspection API
│   ├── multitenancy/     # Tenant isolation logic
│   ├── tasks/            # Background Task orchestration
│   └── templating/       # PDF & Report Generation engine
├── generators/           # Auto-Generation Engine
│   ├── filters/          # FilterSet generation (advanced filtering)
│   ├── mutations/        # CRUD & Bulk Mutation generation
│   ├── queries/          # List/Retrieve Query generation
│   └── types/            # DjangoObjectType generation
├── middleware/           # GraphQL Middleware
│   ├── auth/             # JWT Authentication middleware
│   └── performance/      # Query complexity, cost analysis & timing
├── security/             # Security Engine
│   ├── rbac/             # Role-Based Access Control implementation
│   ├── validation/       # Input sanitization & validation rules
│   └── policies.py       # Policy Engine definitions
└── webhooks/             # Webhook System
    ├── dispatcher.py     # Event delivery logic
    └── signals.py        # Django signal handlers for events
```

## 🚀 Key Features

*   **Auto-CamelCase**: Automatic conversion of snake_case Python fields to camelCase GraphQL fields.
*   **Performance**: Automatic `select_related` and `prefetch_related` optimization to prevent N+1 queries.
*   **Security**: Built-in Rate Limiting, Query Depth Analysis, and Field-Level Permissions.
*   **Developer Experience**: Custom CLI for project scaffolding and clean architecture.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](https://github.com/raillogistic/rail-django/blob/main/CONTRIBUTING.md) for details.

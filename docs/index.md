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

## 🚀 Key Features

*   **Auto-CamelCase**: Automatic conversion of snake_case Python fields to camelCase GraphQL fields.
*   **Performance**: Automatic `select_related` and `prefetch_related` optimization to prevent N+1 queries.
*   **Security**: Built-in Rate Limiting, Query Depth Analysis, and Field-Level Permissions.
*   **Developer Experience**: Custom CLI for project scaffolding and clean architecture.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](https://github.com/raillogistic/rail-django/blob/main/CONTRIBUTING.md) for details.

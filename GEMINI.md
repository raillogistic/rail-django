# Project: Rail Django

## Overview

`rail-django` is a specialized wrapper framework built on top of Django and Graphene-Django. It aims to accelerate the development of production-ready GraphQL APIs by providing pre-configured settings, automatic schema generation, and built-in enterprise features like audit logging, RBAC, and health monitoring.

## Tech Stack

- **Language:** Python (3.11+)
- **Core Framework:** Django (>=4.2)
- **API Layer:** Graphene (GraphQL)
- **Database:** Django ORM (supports all Django backends)

## Key Features

- **Auto-Generation:** Automatically generates GraphQL Types, Queries, and Mutations from Django models.
- **Enhanced Security:** Built-in Field-level permissions, RBAC, and Input validation.
- **Enterprise Ready:** Includes Audit Logging, Health Checks, Performance Monitoring, and Observability (Sentry/OpenTelemetry).
- **Webhooks System:** Comprehensive event dispatching with signal bindings, payload signing, and async delivery.
- **Schema Management:** Registry with versioning, snapshots, diffing, and export capabilities (SDL, JSON, Markdown).
- **Project Scaffolding:** Custom CLI `rail-admin` to enforce clean architecture.

## Installation & Setup

1.  **Clone the repository**
2.  **Install in editable mode:**
    ```bash
    pip install -e .
    ```

## Development Workflow

### Creating a New Project

Use the bundled CLI tool to bootstrap a new project with the correct structure:

```bash
rail-admin startproject my_project
```

### Creating an App

Inside your project:

```bash
python manage.py startapp my_app
```

_Note: Apps are created inside an `apps/` directory by default._

## Codebase Structure

- `rail_django/api/`: REST API endpoints for schema management and discovery.
- `rail_django/bin/`: CLI entry points (`rail_admin`).
- `rail_django/conf/`: Framework configuration and project templates.
- `rail_django/core/`: Core logic (Registry, SettingsProxy, Schema building, Snapshots).
- `rail_django/generators/`: Logic for auto-generating GraphQL schemas from models with camelCase field names.
- `rail_django/extensions/`: Pluggable features (Auth, Audit, Health, Exporting, Observability, Subscriptions).
- `rail_django/security/`: Security implementations (RBAC, Validation).
- `rail_django/webhooks/`: Webhook dispatcher, configuration, and signal handling.

## Subsystems Details

- **Permissions:** A granular `PermissionManager` supports field-level, object-level, and operation-level checks. It integrates with Django permissions and custom `GraphQLMeta` guards.
- **Webhooks:** Triggered by Django signals (`post_save`, `post_delete`), supporting filtering, payload customization, and secure delivery with HMAC signing.
- **Schema Registry:** Stores schema configurations and snapshots (`SchemaSnapshotModel`). Provides REST endpoints (`/api/v1/schemas/...`) for history, diffs, and exports.
- **Observability:** `SentryIntegrationPlugin` and `OpenTelemetryIntegrationPlugin` hook into GraphQL execution for tracing and error reporting.

## Conventions

- **Configuration:** Uses a hierarchical settings system (`SettingsProxy`). Project settings inherit from `rail_django.conf.framework_settings`.
- **Schema Registry:** All schemas are registered via `rail_django.core.registry`.

## Dependencies

Defined in `setup.py` and `rail_django/conf/project_template/requirements/base.txt-tpl` (requirements.txt is deprecated). Key libs: `Django`, `graphene-django`, `django-filter`, `pyjwt`.

## Gemini Added Memories

- The rail_django framework's TypeGenerator automatically creates custom list fields for reverse relationships (e.g., user_set) to avoid Relay connections. It previously also added these to the exclude list, causing redundant configuration warnings in Graphene-Django. The fix was to stop excluding them since the custom field definition takes precedence.
- Optimized rail-django performance by implementing recursive GraphQL field extraction for nested select_related/prefetch_related, using prefetch cache in resolvers to avoid N+1 queries, and using field.attname for field masking to prevent unnecessary DB hits.
- Merged the content of 'rail_django/conf/project_template/deploy/USAGE.md' into 'rail_django/conf/project_template/USAGE.md' as section "12. Manual Deployment Guide", consolidating the project documentation.
- Analyzed the codebase and identified that **Webhooks**, **Permissions**, **Observability**, and **Schema Management** are well-implemented.
- Identified a gap in **Subscriptions**: The current implementation is minimal. Recommended **Subscription Enhancements** (Payload filtering, Authorization, Broadcasting) as the next key feature.

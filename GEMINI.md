# Project: Rail Django

## Overview
`rail-django` is a specialized wrapper framework built on top of Django and Graphene-Django. It aims to accelerate the development of production-ready GraphQL APIs by providing pre-configured settings, automatic schema generation, and built-in enterprise features like audit logging, RBAC, and health monitoring.

## Tech Stack
- **Language:** Python (3.8+)
- **Core Framework:** Django (>=4.2)
- **API Layer:** Graphene (GraphQL)
- **Database:** Django ORM (supports all Django backends)

## Key Features
- **Auto-Generation:** Automatically generates GraphQL Types, Queries, and Mutations from Django models.
- **Enhanced Security:** Built-in Field-level permissions, RBAC, and Input validation.
- **Enterprise Ready:** Includes Audit Logging, Health Checks, and Performance Monitoring.
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
*Note: Apps are created inside an `apps/` directory by default.*

## Codebase Structure
- `rail_django/bin/`: CLI entry points (`rail_admin`).
- `rail_django/conf/`: Framework configuration and project templates.
- `rail_django/core/`: Core logic (Registry, SettingsProxy, Schema building).
- `rail_django/generators/`: Logic for auto-generating GraphQL schemas from models.
- `rail_django/extensions/`: Pluggable features (Auth, Audit, Health, Exporting).
- `rail_django/security/`: Security implementations (RBAC, Validation).

## Conventions
- **Configuration:** Uses a hierarchical settings system (`SettingsProxy`). Project settings inherit from `rail_django.conf.framework_settings`.
- **Schema Registry:** All schemas are registered via `rail_django.core.registry`.

## Dependencies
Defined in `setup.py` and `requirements.txt`. Key libs: `Django`, `graphene-django`, `django-filter`, `pyjwt`.

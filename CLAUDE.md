# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Rail Django is a GraphQL framework for Django built on top of Graphene-Django. It provides automatic schema generation from Django models, built-in security (RBAC, query depth limits, input validation), and enterprise features (audit logging, health checks, webhooks, observability).

**Versions:** Python 3.11+, Django 4.2+, Graphene 3.3+

## Commands

```bash
# Install in editable mode
pip install -e .

# Run tests
pytest -m unit                    # Fast unit tests (no DB)
pytest -m integration             # DB-backed tests
pytest                            # All tests

# Django test runner (CI path)
DJANGO_SETTINGS_MODULE=rail_django.config.framework_settings python -m django test tests.unit

# Formatting
python -m black --check rail_django/

# Scaffold a new project
rail-admin startproject my_api

# Run a generated project
cd my_api && python manage.py migrate && python manage.py runserver
```

## Architecture

### Core Flow

1. **Schema Discovery**: `SchemaRegistry` scans apps for `schemas.py`, `graphql_schema.py`, `schema.py`, or `graphql/schema.py`
2. **Schema Build**: `SchemaBuilder` (multiton by name) resolves models and uses generators to build types/queries/mutations
3. **Schema Assembly**: Root Query/Mutation created dynamically; extensions (health, metadata) merged; plugin hooks run
4. **Execution**: `GraphQLView` or `MultiSchemaGraphQLView` executes with persisted query resolution and query optimization

### Key Components

- **`rail_django/core/registry.py`**: SchemaRegistry - source of truth for registered schemas
- **`rail_django/core/schema.py`**: SchemaBuilder - builds Graphene schema from models
- **`rail_django/generators/`**: TypeGenerator, QueryGenerator, MutationGenerator - auto-generate GraphQL from Django models
- **`rail_django/security/`**: Unified security system (Events, RBAC, Validation, Field Permissions, Anomaly Detection)
- **`rail_django/extensions/`**: Pluggable features (auth, audit, health, export, observability, subscriptions, webhooks)
- **`rail_django/plugins/`**: Plugin manager with pre/post hooks for schema build and execution
- **`rail_django/scaffolding/`**: Project/app templates for CLI scaffolder
- **`rail_django/config/`**: Framework settings used by CLI scaffolder and tests

### GraphQLMeta

Per-model configuration used by generators for field inclusion/exclusion, permissions, guards, ordering rules, and custom filters. See `rail_django/docs/reference/meta.md`.

### Middleware Layers

- **Django middleware**: `GraphQLAuthenticationMiddleware`, `GraphQLPerformanceMiddleware`, `GraphQLRateLimitMiddleware`, `PluginMiddleware`
- **Graphene middleware**: `GraphQLSecurityMiddleware`, `FieldPermissionMiddleware`

## Testing

Use pytest markers: `@pytest.mark.unit` and `@pytest.mark.integration`

Testing helpers in `rail_django.testing`:
- `build_schema(...)` - build schema with local registry
- `RailGraphQLTestClient` - execute GraphQL with request context
- `override_rail_settings(...)` - isolate settings in test scope

Test settings default to `rail_django.config.test_settings` (SQLite).

## Coding Conventions

- GraphQL fields are camelCase by default (`auto_camelcase = True`)
- Tests under `tests/unit/` and `tests/integration/`
- TypeGenerator auto-creates custom list fields for reverse relationships to avoid Relay connections

## Performance Notes

- Recursive GraphQL field extraction for nested select_related/prefetch_related
- Prefetch cache in resolvers to avoid N+1 queries
- Use `field.attname` for field masking to prevent unnecessary DB hits

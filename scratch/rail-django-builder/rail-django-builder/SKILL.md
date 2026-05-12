---
name: rail-django-builder
description: Guide for building, scaffolding, and securing applications using the rail-django framework. Use this skill when asked to create an app, define models with GraphQL schema exposure, write queries/mutations, configure security (RBAC/ABAC), or utilize Rail Django extensions like background tasks and webhooks.
---

# Rail Django Builder Skill

This skill provides workflows and documentation for building production-ready GraphQL APIs using the `rail-django` framework.

## Project & App Scaffolding

Rail Django includes a CLI tool (`rail-admin`) to scaffold a project with recommended directory structures and optimal defaults.

```bash
# Start a new project
rail-admin startproject my_api
cd my_api

# Create an app inside the project
python manage.py startapp store apps/store
```

## "Model-First" Workflow

Rail Django automatically generates GraphQL schemas (Types, Queries, Mutations) from standard Django models.

1. **Define Django Models**: Standard Django models in `models.py`.
2. **Configure `GraphQLMeta`**: Add a nested `GraphQLMeta` class inside the model to customize fields, filtering, ordering, and access control.
3. **Register App**: Ensure the app is in `INSTALLED_APPS`.
4. **Migrate**: `python manage.py makemigrations && python manage.py migrate`.

**Reference**: See [`references/models_and_schema.md`](references/models_and_schema.md) for detailed instructions on `GraphQLMeta`, relationships, N+1 prevention, and the `@field` decorator.

## Queries and Filtering

Rail Django generates `productList`, `productPage`, and `productGroup` queries automatically, supporting advanced Prisma-style filtering (`where`).

**Reference**: See [`references/queries.md`](references/queries.md) for syntax on relational filtering, logic operators (AND/OR), custom filters, ordering, and pagination.

## Mutations and Nested Operations

Rail Django generates Create, Update, and Delete (CUD) operations out of the box, as well as bulk operations. It uses "Unified Inputs" (`connect`, `create`, `update`, `disconnect`, `set`) for handling relationships in a single atomic payload.

**Reference**: See [`references/mutations.md`](references/mutations.md) for examples of nested operations, bulk actions, and creating custom method mutations using the `@mutation` decorator.

## Security, Auth, and Permissions

Rail Django is "Secure by Default". It enforces a hybrid authorization system.
- **RBAC**: Define and assign roles.
- **ABAC**: Define attribute-based rules (e.g., department matching).
- **Field-Level Guards**: Mask or hide sensitive fields via `GraphQLMeta`.

**Reference**: See [`references/security.md`](references/security.md) for configuring JWT Auth, registering roles via `role_manager`, declaring `abac_policies`, and using `OperationGuard`.

## Extensions and Enterprise Configuration

The framework includes advanced capabilities controlled centrally via `RAIL_DJANGO_GRAPHQL` in `settings.py`.

- **Background Tasks**: `@task_mutation`
- **Webhooks**: Automatic event dispatching
- **Form API**: Metadata for dynamic frontends
- **Templating**: Generate PDFs and Excels from models (See [`references/templating.md`](references/templating.md))

**Reference**: See [`references/extensions_and_config.md`](references/extensions_and_config.md) for setup and usage of the remaining features.

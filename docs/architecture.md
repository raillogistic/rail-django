# Architecture Internals

This document describes how Rail Django builds and serves GraphQL schemas.

## Core flow

1. **Schema discovery**
   - `SchemaRegistry` scans installed apps for `schemas.py`, `graphql_schema.py`,
     `schema.py`, or `graphql/schema.py` and registers schemas.
   - Apps may also call `register_schema(registry)` directly.

2. **Schema build**
   - `SchemaBuilder` is a multiton keyed by schema name.
   - It resolves models, then uses generators to build types, queries, and
     mutations.

3. **Schema assembly**
   - Root `Query` and `Mutation` classes are created dynamically.
   - Security mutations (login, refresh, logout) are added when enabled.
   - Extensions (health, metadata) are merged into the root query.
   - Plugin hooks can adjust the schema before and after build.
   - Schema snapshots can be recorded after a successful build.

4. **Execution**
   - `GraphQLView` or `MultiSchemaGraphQLView` executes the schema.
   - Persisted query resolution runs before execution when enabled.
   - Query optimization runs at resolver time.

## Key components

### SchemaRegistry (`rail_django.core.registry`)

- Source of truth for registered schemas.
- Stores per-schema settings and model lists.
- Manages schema builders and discovery hooks.
- Records schema snapshots when enabled.

### SchemaBuilder (`rail_django.core.schema`)

- Resolves models for the schema based on registry settings.
- Builds Graphene types with `TypeGenerator`.
- Builds queries and mutations with `QueryGenerator` and `MutationGenerator`.
- Rebuilds on `post_migrate` and optionally `post_save`.
- Runs plugin hooks for pre/post schema build.

### Plugins (`rail_django.plugins`)

- Plugin manager loads and executes optional hooks.
- Hooks can run before/after operations or during schema build.
- Execution hooks are opt-in via `plugin_settings.enable_execution_hooks`.

### Generators

- `TypeGenerator` maps Django fields to GraphQL types.
- `QueryGenerator` produces list, paginated, and grouping queries.
- `MutationGenerator` produces CRUD and bulk mutations.

### GraphQLMeta

- Per-model configuration used by generators for:
  - field inclusion/exclusion
  - permissions and guards
  - ordering rules
  - custom filters

## Request lifecycle

1. HTTP request hits Django.
2. `MultiSchemaGraphQLView` selects a schema based on URL segment.
3. Persisted queries resolve hashes to full documents (optional).
4. Graphene executes the schema and resolves fields.
5. Resolvers apply filters, ordering, permissions, and query optimization.
6. JSON response is returned.

## Middleware layers

- Django middleware: `GraphQLAuthenticationMiddleware`,
  `GraphQLPerformanceMiddleware`, `GraphQLRateLimitMiddleware`,
  `PluginMiddleware`.
- Graphene middleware: `GraphQLSecurityMiddleware` and custom middleware stack.

Note: Graphene middleware must be wired into the GraphQL execution layer to
have effect. Ensure your view passes the middleware list to Graphene.

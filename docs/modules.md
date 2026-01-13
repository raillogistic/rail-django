# Codebase Modules

This reference maps the main modules to their responsibilities.

## core

- `core/registry.py`: schema registry, discovery, and schema builders
- `core/schema.py`: schema build pipeline
- `core/settings.py`: dataclass-based settings models
- `core/middleware.py`: Graphene middleware stack definitions, including field permission enforcement
- `core/performance.py`: lightweight query optimization helpers
- `core/runtime_settings.py`: merged security + performance runtime settings
- `core/services.py`: service hooks for rate limiting, optimizers, and audit logging
- `core/schema_snapshots.py`: schema snapshots for diff/export endpoints

## generators

- `generators/types.py`: type generator entrypoint and shared helpers
- `generators/types_objects.py`: object type construction and relationship fields
- `generators/types_inputs.py`: input types for create/update mutations
- `generators/types_enums.py`: enum helpers for choice fields
- `generators/types_dataloaders.py`: DataLoader helpers for reverse relations
- `generators/queries.py`: query generator entrypoint and shared helpers
- `generators/queries_list.py`: single and list query builders
- `generators/queries_pagination.py`: paginated query builders
- `generators/queries_grouping.py`: grouping query builders
- `generators/queries_ordering.py`: ordering helpers for list and paginated queries
- `generators/mutations.py`: mutation generator entrypoint and shared helpers
- `generators/mutations_crud.py`: create/update/delete mutation builders
- `generators/mutations_bulk.py`: bulk mutation builders
- `generators/mutations_methods.py`: method mutation builders and audit helpers
- `generators/mutations_errors.py`: mutation error helpers
- `generators/mutations_limits.py`: nested input validation limits
- `generators/filters.py`: advanced filter input generation
- `generators/introspector.py`: model metadata inspection

## security

- `security/policies.py`: explicit allow/deny policy engine and classification bundles
- `security/rbac.py`: role definitions and permission resolution
- `security/graphql_security.py`: query depth and complexity analysis
- `security/input_validation.py`: unified input validation and sanitization pipeline
- `security/field_permissions.py`: field-level masking and visibility
- `security/signals.py`: permission cache invalidation hooks

## rate_limiting

- `rate_limiting.py`: centralized limiter shared across GraphQL, HTTP, and schema API

## views and URLs

- `views/graphql_views.py`: multi-schema GraphQL view
- `views/health_views.py`: health dashboard and API
- `api/views.py`: REST schema management endpoints
- `urls.py`: GraphQL and REST URL routing

## extensions

- `extensions/auth.py`: JWT login, refresh, user info
- `extensions/audit.py`: audit logging
- `extensions/exporting.py`: CSV/XLSX export endpoint
- `extensions/permissions.py`: permission helpers and explain API
- `extensions/validation.py`: validation query helpers and re-exports
- `extensions/templating.py`: PDF endpoints via decorator
- `extensions/health.py`: health checks
- `extensions/optimization.py`: selection-set driven query optimization
- `extensions/rate_limiting.py`: Graphene middleware backed by the shared limiter
- `extensions/virus_scanner.py`: ClamAV integration
- `extensions/persisted_queries.py`: APQ-style persisted query support
- `extensions/observability.py`: Sentry/OpenTelemetry plugin hooks
- `extensions/subscriptions.py`: Channels subscription helper

## plugins

- `plugins/base.py`: plugin interface and manager
- `plugins/hooks.py`: hook registry

## middleware

- `middleware/auth_middleware.py`: JWT auth and shared rate limiting
- `middleware/performance.py`: performance monitoring

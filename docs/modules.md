# Codebase Modules

This reference maps the main modules to their responsibilities.

## core

- `core/registry.py`: schema registry, discovery, and schema builders
- `core/schema.py`: schema build pipeline
- `core/settings.py`: dataclass-based settings models
- `core/middleware.py`: Graphene middleware stack definitions
- `core/performance.py`: lightweight query optimization helpers

## generators

- `generators/types.py`: Django field to GraphQL type mapping
- `generators/queries.py`: list, paginated, grouping queries
- `generators/mutations.py`: CRUD and bulk mutations
- `generators/filters.py`: advanced filter input generation
- `generators/introspector.py`: model metadata inspection

## security

- `security/rbac.py`: role definitions and permission resolution
- `security/graphql_security.py`: query depth and complexity analysis
- `security/input_validation.py`: unified input validation and sanitization pipeline
- `security/field_permissions.py`: field-level masking and visibility

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
- `extensions/validation.py`: validation query helpers and re-exports
- `extensions/templating.py`: PDF endpoints via decorator
- `extensions/health.py`: health checks
- `extensions/optimization.py`: selection-set driven query optimization
- `extensions/rate_limiting.py`: Graphene middleware backed by the shared limiter
- `extensions/virus_scanner.py`: ClamAV integration

## middleware

- `middleware/auth_middleware.py`: JWT auth and shared rate limiting
- `middleware/performance.py`: performance monitoring

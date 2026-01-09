# Extensions Guide

Rail Django ships with optional extensions. Most are enabled simply by
importing them in your schema build or including their URLs.

## Auth extension (`rail_django.extensions.auth`)

- JWT login, refresh, logout, and optional register mutations.
- `me` query returns current user with permissions and settings.

## Health extension (`rail_django.extensions.health`)

- System metrics, DB checks, cache checks, schema checks.
- URL helpers in `rail_django.views.health_views.get_health_urls()`.

## Exporting (`rail_django.extensions.exporting`)

- `POST /api/v1/export/` exports CSV or XLSX.
- Supports dot-notation field access and GraphQL filters.

## Templating / PDF (`rail_django.extensions.templating`)

- Decorator `@model_pdf_template` registers a PDF endpoint.
- Endpoint: `/api/templates/<template_path>/<pk>/`.

## Optimization (`rail_django.extensions.optimization`)

- Query analyzer for selection sets
- Automatic `select_related` and `prefetch_related`
- Performance monitor helpers

## Rate limiting (`rail_django.extensions.rate_limiting`)

- Graphene middleware that throttles GraphQL fields using the cache.

## MFA (`rail_django.extensions.mfa`)

- TOTP flows and MFA guards in GraphQL middleware.

## Permissions (`rail_django.extensions.permissions`)

- Operation-level permission checks and GraphQLMeta guards.
- Exposes `my_permissions` query for current user.

## Audit (`rail_django.extensions.audit`)

- Structured audit logs for auth and sensitive actions.
- Optional database, file, and webhook sinks.

## Performance metrics (`rail_django.extensions.performance_metrics`)

- Collects query timings and resource usage.
- Use alongside `GraphQLPerformanceMiddleware`.

## Virus scanning (`rail_django.extensions.virus_scanner`)

- ClamAV or mock scanner for uploaded files.
- Configure `VIRUS_SCANNING_ENABLED`, `CLAMAV_PATH`, and `QUARANTINE_PATH`.

## Metadata (`rail_django.extensions.metadata`)

- Exposes model metadata for frontends (forms, tables).
- Enable with `schema_settings.show_metadata = True`.

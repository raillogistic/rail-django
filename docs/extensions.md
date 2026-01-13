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
- Default-deny export schema with allowlisted accessors and filters.
- Optional async export jobs with status/download URLs.
- Supports export templates and field formatters.
- Export URLs require JWT auth decorators to be installed.

## Reporting / BI (`rail_django.extensions.reporting`)

- Datasets, visualizations, dashboards, and export jobs backed by Django models.
- Reusable semantic layer (dimensions, metrics, computed fields) with JSON specs.
- GraphQL auto schema exposes preview/query/describe actions on the models.
- See `docs/reporting.md` for setup, query specs, and security rules.

## Templating / PDF (`rail_django.extensions.templating`)

- Decorators `@model_pdf_template` and `@pdf_template` register PDF endpoints.
- Low-level helpers: `render_pdf(...)`, `PdfBuilder()`, and pluggable renderers.
- Endpoints: `/api/templates/<template_path>/<pk>/`, `/api/templates/catalog/`, `/api/templates/preview/...`,
  plus async job status/download endpoints under `/api/templates/jobs/...`.
- Optional post-processing for watermarks, page stamps, encryption, and signatures.
- Optional deps: `pypdf` (encryption/overlays), `pyhanko` (signatures), `wkhtmltopdf` binary.

## Optimization (`rail_django.extensions.optimization`)

- Query analyzer for selection sets
- Automatic `select_related` and `prefetch_related`
- Performance monitor helpers
- Optional query cache hooks when a backend is registered via
  `rail_django.core.services.set_query_cache_factory`

## Persisted queries (`rail_django.extensions.persisted_queries`)

- APQ-style persisted query resolution with optional allowlists.
- Supports `allow_unregistered` APQ registration when `enforce_allowlist` is false.
- Cache-backed storage for query hashes (opt-in).

## Observability (`rail_django.extensions.observability`)

- Optional plugin hooks for Sentry and OpenTelemetry.
- Activate via `GRAPHQL_SCHEMA_PLUGINS`.

## Subscriptions (`rail_django.extensions.subscriptions`)

- Lightweight helper to build a Channels consumer.
- Auto-generated subscriptions are enabled via `subscription_settings.enable_subscriptions`.
- Supports per-model created/updated/deleted events with filter args.
- Requires `channels-graphql-ws` (optional dependency).

## Rate limiting (`rail_django.extensions.rate_limiting`)

- Graphene middleware that applies request-level rate limiting at root fields.
- Uses the centralized limiter configuration (`RAIL_DJANGO_RATE_LIMITING`).

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
- Metadata is private and requires an authenticated user.
- In production, metadata is cached for the process lifetime by default; tune via `RAIL_DJANGO_GRAPHQL["METADATA"]`.

# Extensions

Rail Django comes with a suite of extensions to power-up your API.

## Core Extensions

*   [**Audit Logging**](audit-logging.md): Track user actions and sensitive data access.
*   [**Webhooks**](webhooks.md): Event-driven architecture with signed payloads.
*   [**Exporting**](exporting.md): Excel and CSV exports for any queryset.
*   [**Templating**](templating.md): Generate PDFs and Excel reports from models.
*   [**Tasks**](tasks.md): Background task management.
*   [**Subscriptions**](subscriptions.md): Real-time updates via WebSockets.
*   [**Multitenancy**](multitenancy.md): SaaS-ready data isolation.
*   [**Health Checks**](health-checks.md): Liveness and readiness probes.
*   [**Observability**](observability.md): Integration with Sentry and OpenTelemetry.
*   [**Form API**](form.md): Form configuration and data loading for dynamic forms.
*   [**Data Importing**](importing.md): Template-driven data import pipeline.

## Enabling Extensions

Most extensions are enabled by adding them to `INSTALLED_APPS` or configuring them in `RAIL_DJANGO_GRAPHQL` settings.

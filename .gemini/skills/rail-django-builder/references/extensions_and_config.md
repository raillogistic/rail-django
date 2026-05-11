# Extensions and Configuration Reference

Rail Django includes several optional extensions to add enterprise features.

## Main Configuration (`RAIL_DJANGO_GRAPHQL`)
All settings are grouped logically in `settings.py` under `RAIL_DJANGO_GRAPHQL`:
- `schema_settings`: Root behavior (camelCase, auth required, introspection).
- `query_settings`: Pagination defaults, permission defaults (`view`).
- `mutation_settings`: CUD toggles, bulk operations, nested relations toggles.
- `security_settings`: Auth, RBAC, ABAC, policy engine, input validation.
- `performance_settings`: N+1 optimization, query complexity/depth limits, caching.

## Background Tasks
Execute long-running operations asynchronously (supports Celery, Thread, etc.).
Configure under `task_settings`.

```python
from rail_django.extensions.tasks import task_mutation

@task_mutation(name="syncInventory", track_progress=True)
def sync_inventory_task(info, provider: str):
    task = info.context.task
    task.update_progress(50, "Working...")
    return {"status": "done"}
```

## Webhooks
Dispatch events to external services on model changes. Configure under `webhook_settings` or `webhooks.py`.
- Includes HMAC-SHA256 signatures (`X-Webhook-Signature`).
- Supports filtering by model and events.

## Form API Extension
Provides metadata for dynamic frontends to render forms based on Django models.
- Enabled by default. Configured via `RAIL_DJANGO_FORM` in settings.
- Exposes `modelFormContract`, `modelFormInitialData`, etc.

## Data Importing & Exporting
- **Importing**: Staged CSV/XLSX imports via GraphQL (`createModelImportBatch`, `updateModelImportBatch` with COMMIT/SIMULATE).
- **Exporting**: Programmatic or REST (`/export/`) exports to CSV/XLSX. Controlled via `RAIL_DJANGO_EXPORT`.

## Audit Logging
Records security and activity events. Configured via `GRAPHQL_ENABLE_AUDIT_LOGGING = True`.
Audits all mutations by default. Queries are audited if listed in `security_settings.audited_query_fields`.

## Observability & Health
- Integrates with Sentry, OpenTelemetry, and Prometheus.
- Exposes health endpoints (`/health/live/`, `/health/ready/`).

## Templating (PDF & Excel)
Generate PDFs (WeasyPrint) or Excel files from models.
```python
from rail_django.extensions.templating import model_pdf_template
class Order(models.Model):
    @model_pdf_template(content="pdf/invoice.html", title="Invoice")
    def invoice_pdf(self, request=None):
        return {"order": self}
```
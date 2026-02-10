# Extensions Module Reference

Rail Django extensions provide pluggable enterprise features. Each extension can be independently enabled or disabled.

## Extensions Overview

| Extension | Description | Documentation |
|-----------|-------------|---------------|
| [Audit](./audit.md) | Audit logging, security reports | REST API, tracking |
| [Authentication](./auth.md) | JWT tokens, login, MFA | Full auth system |
| [Data Export](./exporting.md) | Excel/CSV export | Async, streaming |
| [Templating](./templating.md) | PDF generation | HTML templates |
| [Health](./health.md) | System monitoring | K8s probes |
| [Metadata](./metadata.md) | Schema introspection | UI builders |
| [Form API](../../extensions/form.md) | Form configuration | Dynamic forms |
| [Data Import](../../extensions/importing.md) | Template-driven import | Staging, pipeline |
| [Reporting](./reporting.md) | BI dashboards | Aggregations |
| [Subscriptions](./subscriptions.md) | Real-time events | WebSocket |
| [Tasks](./tasks.md) | Background jobs | Multiple backends |
| [Webhooks](./webhooks.md) | Event dispatch | External systems |
| [Multitenancy](./multitenancy.md) | Tenant isolation | Row/schema level |

## Extension Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Extension System                              │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Extension Registry                       │  │
│  │  • Discovers extensions                                   │  │
│  │  • Manages lifecycle                                      │  │
│  │  • Provides hooks                                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Extension Hooks                         │  │
│  │  • pre_schema_build                                       │  │
│  │  • post_schema_build                                      │  │
│  │  • pre_execute                                            │  │
│  │  • post_execute                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│         ┌────────────────────┼────────────────────┐            │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│   ┌───────────┐       ┌───────────┐       ┌───────────┐       │
│   │   Auth    │       │  Export   │       │  Health   │       │
│   └───────────┘       └───────────┘       └───────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Enabling Extensions

Extensions are enabled via settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        # Enable built-in extension mutations
        "enable_extension_mutations": True,

        # Enable metadata queries
        "show_metadata": True,
    },

    "subscription_settings": {
        "enable_subscriptions": True,
    },
}

# Separate extension settings
RAIL_DJANGO_EXPORT = {
    "enabled": True,
    # ... export settings
}

RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    "enabled": True,
    # ... templating settings
}

RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    # ... webhook settings
}
```

## Extension URLs

Extensions that provide REST endpoints need URL configuration:

```python
# root/urls.py
from django.urls import path, include
from rail_django.http.views.audit import get_audit_urls

urlpatterns = [
    # GraphQL endpoints
    path("graphql/", include("rail_django.urls")),

    # Extension REST endpoints
    path("api/v1/", include(get_audit_urls())),  # Audit API
    path("api/v1/export/", include("rail_django.extensions.exporting.urls")),
    path("api/templates/", include("rail_django.extensions.templating.urls")),
    path("health/", include("rail_django.http.urls.health")),
]
```

## Quick Reference

### Audit Logging

```python
from rail_django.extensions.audit import audit_log

# Log security event
audit_log.security(
    event_name="SUSPICIOUS_ACTIVITY",
    user=request.user,
    request=request,
    metadata={"reason": "Multiple failed logins"},
    severity="warning"
)

# REST API endpoints (require admin access)
# GET /api/v1/audit/              - List events with filtering
# GET /api/v1/audit/stats/        - Statistics and aggregations
# GET /api/v1/audit/security-report/ - Threat analysis
# GET /api/v1/audit/event/<id>/   - Single event detail
# GET /api/v1/audit/meta/         - Available event types
```

### Authentication

```python
from rail_django.extensions.auth import jwt

# Generate tokens
access_token = jwt.generate_access_token(user)
refresh_token = jwt.generate_refresh_token(user)

# Verify token
user = jwt.verify_token(token)
```

### Data Export

```python
from rail_django.extensions.exporting import ExportJob

# Create export job
job = ExportJob.create(
    model="store.Product",
    fields=["name", "price", "category.name"],
    filters={"status": "active"},
    format="xlsx"
)

# Get result
url = job.get_download_url()
```

### PDF Generation

```python
from rail_django.extensions.templating import render_pdf

# Render PDF
pdf_bytes = render_pdf(
    template="invoices/invoice.html",
    context={"order": order}
)
```

### Health Checks

```python
from rail_django.extensions.health import health_check

# Get system status
status = health_check.get_status()
# {"overall": "healthy", "database": "healthy", ...}
```

### Webhooks

```python
from rail_django.webhooks import dispatch_event

# Send webhook
dispatch_event(
    event_type="order.created",
    payload={"order_id": order.id}
)
```

## Creating Custom Extensions

```python
from rail_django.plugins.base import BasePlugin

class MyExtension(BasePlugin):
    name = "my_extension"

    def pre_schema_build(self, builder):
        """Called before schema is built."""
        pass

    def post_schema_build(self, schema):
        """Called after schema is built."""
        pass

    def pre_execute(self, request, operation):
        """Called before query execution."""
        pass

    def post_execute(self, request, result):
        """Called after query execution."""
        pass

    def get_query_extensions(self):
        """Return additional query fields."""
        return {"myQuery": MyQueryField}

    def get_mutation_extensions(self):
        """Return additional mutation fields."""
        return {"myMutation": MyMutationField}
```

Register the extension:

```python
# myapp/apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    def ready(self):
        from rail_django.plugins import plugin_manager
        from .extensions import MyExtension

        plugin_manager.register(MyExtension())
```

## Related Documentation

- [Plugin System](../library/plugins/index.md) - Full plugin architecture
- [Configuration](../tutorials/configuration.md) - All settings

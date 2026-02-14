# Extensions module API

Rail Django extensions add optional runtime features on top of core schema
generation. This page maps extension modules to code-level integration points.

## Key extension packages

- `rail_django.extensions.auth`: JWT auth mutations and queries.
- `rail_django.extensions.mfa`: MFA device setup and verification.
- `rail_django.extensions.audit`: Audit model and frontend audit mutation.
- `rail_django.extensions.exporting`: CSV and XLSX model exports.
- `rail_django.extensions.excel`: Decorator-based Excel template endpoints.
- `rail_django.extensions.templating`: PDF and HTML template rendering.
- `rail_django.extensions.tasks`: Background task API and URL helpers.
- `rail_django.extensions.metadata`: Schema metadata for frontend generation.
- `rail_django.extensions.subscriptions`: Subscription integration.
- `rail_django.extensions.importing`: Import pipeline endpoints.

## Configuration entry points

Use `RAIL_DJANGO_GRAPHQL` for shared extension toggles.

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_extension_mutations": True,
        "show_metadata": True,
    },
    "subscription_settings": {
        "enable_subscriptions": True,
    },
}
```

Use extension-specific settings where required.

```python
RAIL_DJANGO_EXPORT = {
    "max_rows": 5000,
    "async_jobs": {"enable": True},
}

RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    "enabled": True,
}
```

## URL integration

Several extensions expose REST endpoints through helper functions.

```python
from rail_django.extensions.exporting import get_export_urls
from rail_django.extensions.tasks import get_task_urls
from rail_django.extensions.templating import template_urlpatterns
from rail_django.extensions.excel import excel_urlpatterns
from rail_django.extensions.importing.urls import importing_urlpatterns

urlpatterns = []
urlpatterns += get_export_urls()
urlpatterns += get_task_urls()
urlpatterns += template_urlpatterns()
urlpatterns += excel_urlpatterns()
urlpatterns += importing_urlpatterns()
```

## Next steps

- [Extensions guide](../../extensions/index.md)
- [Exporting](../../extensions/exporting.md)
- [Audit logging](../../extensions/audit-logging.md)
- [Templating](../../extensions/templating.md)

# Data exporting extension

The data exporting extension lets you export model data to CSV or XLSX through
a JWT-protected HTTP endpoint or programmatic APIs. This page documents the
current request contract and settings used by `rail-django`.

## Enable export routes

Expose export endpoints by appending `get_export_urls()` to your URL patterns.

```python
# urls.py
from rail_django.extensions.exporting import get_export_urls

urlpatterns = [
    # ... your URLs
] + get_export_urls()
```

By default, this provides:

- `POST /export/`
- `GET /export/jobs/<uuid:job_id>/`
- `GET /export/jobs/<uuid:job_id>/download/`

## Programmatic exports

Use the high-level helpers when you need exports in Python code.

```python
from rail_django.extensions.exporting import export_model_to_csv

csv_content = export_model_to_csv(
    "store",
    "Product",
    ["name", "price", "category.name"],
    variables={"where": {"isActive": True}},
    ordering=["-id"],
)
```

You can also use `ModelExporter` directly.

```python
from rail_django.extensions.exporting import ModelExporter

exporter = ModelExporter("store", "Product")
content = exporter.export_to_excel(
    ["name", "price"],
    variables={"where": {"isActive": True}},
)
```

## HTTP request contract

Send export requests as JSON to `POST /export/`.

Required fields:

- `app_name`
- `model_name`
- `file_extension` (`"csv"` or `"xlsx"`)
- `fields`

Optional fields:

- `filename`
- `variables`
- `ordering`
- `max_rows`
- `group_by` (`xlsx` only)
- `template`
- `schema_name`
- `presets`
- `distinct_on`
- `async`

Example:

```json
{
  "app_name": "store",
  "model_name": "Product",
  "file_extension": "xlsx",
  "fields": [
    "name",
    { "accessor": "category.name", "title": "Category" },
    "price"
  ],
  "variables": {
    "where": {
      "isActive": true
    }
  },
  "ordering": ["-id"],
  "async": true
}
```

## Export security and guardrails

Configure export controls with `RAIL_DJANGO_EXPORT`.

```python
RAIL_DJANGO_EXPORT = {
    "max_rows": 5000,
    "allowed_models": ["store.Product", "store.Order"],
    "export_fields": {
        "store.Product": ["id", "name", "price", "category.name"]
    },
    "export_exclude": {
        "store.Product": ["internal_notes"]
    },
    "filterable_fields": {
        "store.Product": ["name", "category.name", "is_active"]
    },
    "orderable_fields": {
        "store.Product": ["id", "name", "price"]
    },
    "require_model_permissions": True,
    "require_field_permissions": False,
    "required_permissions": [],
    "sanitize_formulas": True,
    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30
    },
    "async_jobs": {
        "enable": True,
        "backend": "thread",
        "expires_seconds": 3600,
        "track_progress": True
    }
}
```

## Excel template exports

Excel template endpoints are provided by the separate Excel extension.
Use decorators from `rail_django.extensions.excel`.

```python
from rail_django.extensions.excel import model_excel_template

class Product(models.Model):
    name = models.CharField(max_length=100)

    @model_excel_template(url="products/export", title="Product export")
    def export_products(self):
        products = Product.objects.all()
        return [["Name"], *[[p.name] for p in products]]
```

## Next steps

After configuring exports, validate behavior with
`python manage.py security_check --verbose` and review
[deployment guidance](../operations/deployment.md).

# Data Exporting

## Overview

Rail Django includes a powerful data export system supporting Excel (.xlsx) and CSV formats. It provides both a programmatic API for developers and a secure REST endpoint for client applications.

---

## Table of Contents

1. [Programmatic Usage](#programmatic-usage)
2. [REST API Endpoint](#rest-api-endpoint)
3. [Export Options](#export-options)
4. [Security and Allowlists](#security-and-allowlists)
5. [Asynchronous Exports](#asynchronous-exports)
6. [Excel Templates](#excel-templates)
7. [Best Practices](#best-practices)

---

## Programmatic Usage

You can use the `ModelExporter` or `Exporter` classes to generate reports.

### Basic Export

```python
from rail_django.extensions.exporting import ModelExporter

def export_users(request):
    queryset = User.objects.all()
    exporter = ModelExporter(
        queryset=queryset,
        fields=["username", "email", "date_joined"]
    )
    return exporter.to_csv_response(filename="users.csv")
```

### Advanced Export (Custom Columns)

```python
exporter = ModelExporter(
    queryset=Order.objects.all(),
    fields=[
        "id",
        ("customer__name", "Customer Name"), # Rename column
        ("total_amount", "Total"),
        ("get_status_display", "Status"),    # Call method
    ]
)
return exporter.to_excel_response(filename="orders.xlsx")
```

---

## REST API Endpoint

### POST /api/v1/export/

Creates a data export via a JSON request.

```bash
curl -X POST /api/v1/export/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "store",
    "model_name": "Product",
    "file_extension": "xlsx",
    "filters": { "is_active": true },
    "fields": ["id", "name", "price"]
  }'
```

### GET /api/v1/export/{id}/download/

Downloads the generated file.

---

## Export Options

| Parameter | Description |
|-----------|-------------|
| `filters` | Django ORM filter syntax (e.g., `{"status__in": ["active"]}`) |
| `fields` | List of fields to include, supports `__` for relationships |
| `exclude_fields` | Fields to specifically exclude |
| `orderBy` | List of fields for sorting |
| `limit` | Maximum number of records to export |

---

## Security and Allowlists

### Global Configuration

```python
RAIL_DJANGO_EXPORT = {
    "enabled": True,
    "require_authentication": True,
    "require_permission": True, # Requires export_<model> permission
    "allowlist": ["store.Product", "store.Order"],
    "blocklist": ["auth.User"],
    "max_records": 50000,
}
```

### Per-Model Configuration

```python
class Product(models.Model):
    class ExportMeta:
        allow_export = True
        exportable_fields = ["id", "name", "price"]
        permission = "store.export_product"
```

---

## Asynchronous Exports

For large datasets, Rail Django can process exports in the background using Celery.

```python
RAIL_DJANGO_EXPORT = {
    "async_threshold": 10000, # Exports > 10k records go async
    "async_backend": "celery",
    "notify_on_complete": True,
}
```

---

## Excel Templates

Predefine styles, column widths, and conditional formatting:

```python
from rail_django.extensions.export import ExcelTemplate

class ProductExportTemplate(ExcelTemplate):
    name = "product_catalog"
    header_style = {"font_bold": True, "bg_color": "#4472C4"}
    column_widths = {"name": 30, "price": 15}
```

---

## Best Practices

1. **Limit Record Counts**: Always set a `max_records` to prevent OOM issues.
2. **Use Filters**: Encourage users to filter data before exporting.
3. **Field Selection**: Only export the fields necessary for the report.
4. **Async for Large Data**: Enable async processing for any export likely to take more than a few seconds.
5. **Retention**: Configure `retention_days` to automatically clean up old export files.

# Data Export

## Overview

Rail Django includes a data export system supporting Excel (.xlsx) and CSV formats. This guide covers configuration, REST endpoint usage, export options, security, and best practices.

---

## Table of Contents

1. [Configuration](#configuration)
2. [REST Endpoint](#rest-endpoint)
3. [Export Options](#export-options)
4. [Security and Allowlists](#security-and-allowlists)
5. [Asynchronous Exports](#asynchronous-exports)
6. [Templates](#templates)
7. [Examples](#examples)
8. [Best Practices](#best-practices)

---

## Configuration

### Basic Configuration

```python
# root/settings/base.py
RAIL_DJANGO_EXPORT = {
    # Activation
    "enabled": True,

    # Default format
    "default_format": "xlsx",  # "xlsx" or "csv"

    # Limits
    "max_records": 50000,
    "max_file_size_mb": 50,

    # Security
    "require_authentication": True,
    "require_permission": True,  # Requires export_<model> permission

    # Storage
    "storage_backend": "local",  # "local", "s3", "azure"
    "storage_path": "/exports/",
    "retention_days": 7,

    # Allowed models
    "allowlist": None,  # None = all, or ["app.Model", ...]
    "blocklist": ["auth.User", "sessions.Session"],
}
```

---

## REST Endpoint

### POST /api/v1/export/

Creates a data export.

```bash
curl -X POST /api/v1/export/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "store",
    "model_name": "Product",
    "file_extension": "xlsx",
    "filters": {
      "is_active": true,
      "category__name__icontains": "Electronics"
    },
    "fields": ["id", "name", "sku", "price", "category__name"],
    "orderBy": ["-created_at"]
  }'
```

### Response

```json
{
  "status": "success",
  "export_id": "exp_abc123",
  "download_url": "/api/v1/export/exp_abc123/download/",
  "record_count": 1500,
  "file_size": "2.3 MB",
  "expires_at": "2026-01-23T12:00:00Z"
}
```

### GET /api/v1/export/{id}/download/

Downloads the exported file.

```bash
curl -O /api/v1/export/exp_abc123/download/ \
  -H "Authorization: Bearer <jwt>"
```

### GET /api/v1/export/{id}/status/

Checks export status (for async exports).

```json
{
  "status": "completed",
  "progress": 100,
  "record_count": 1500,
  "download_url": "/api/v1/export/exp_abc123/download/"
}
```

---

## Export Options

### Available Fields

| Parameter         | Type    | Description                      |
| ----------------- | ------- | -------------------------------- |
| `app_name`        | string  | Django application name          |
| `model_name`      | string  | Model name                       |
| `file_extension`  | string  | Format: "xlsx" or "csv"          |
| `filters`         | object  | Django ORM filters               |
| `fields`          | array   | Fields to include (default: all) |
| `exclude_fields`  | array   | Fields to exclude                |
| `orderBy`        | array   | Sorting                          |
| `limit`           | integer | Maximum records                  |
| `offset`          | integer | Starting offset                  |
| `include_headers` | boolean | Include headers (CSV)            |
| `date_format`     | string  | Date format (default: ISO 8601)  |
| `decimal_places`  | integer | Decimal precision                |
| `template_id`     | string  | Excel template ID                |

### Filters

Uses Django ORM filter syntax:

```json
{
  "filters": {
    "status__in": ["active", "pending"],
    "created_at__gte": "2026-01-01",
    "price__range": [100, 500],
    "category__name__icontains": "electronics"
  }
}
```

### Relationship Fields

Include relationship fields using double underscores:

```json
{
  "fields": [
    "id",
    "name",
    "category__name",
    "supplier__company_name",
    "supplier__contact__email"
  ]
}
```

---

## Security and Allowlists

### Allowlist Configuration

```python
RAIL_DJANGO_EXPORT = {
    # Only these models can be exported
    "allowlist": [
        "store.Product",
        "store.Category",
        "store.Order",
    ],

    # These models are never exported
    "blocklist": [
        "auth.User",
        "auth.Permission",
        "sessions.Session",
    ],
}
```

### Per-Model Configuration

```python
class Product(models.Model):
    class ExportMeta:
        # Allowed for export
        allow_export = True

        # Fields allowed for export
        exportable_fields = ["id", "name", "sku", "price", "is_active"]

        # Never export these fields
        exclude_fields = ["internal_notes", "cost_price"]

        # Required permission
        permission = "store.export_product"

        # Maximum records for this model
        max_records = 10000
```

### Field Restrictions

Sensitive fields are automatically excluded:

```python
RAIL_DJANGO_EXPORT = {
    "sensitive_field_patterns": [
        "*password*",
        "*secret*",
        "*token*",
        "*key*",
        "*ssn*",
        "*credit_card*",
    ],
}
```

---

## Asynchronous Exports

For large exports, processing is done asynchronously.

### Configuration

```python
RAIL_DJANGO_EXPORT = {
    # Threshold for async export
    "async_threshold": 10000,

    # Backend (requires Celery or similar)
    "async_backend": "celery",

    # Notifications
    "notify_on_complete": True,
    "notification_email": True,
}
```

### Async Request

```json
{
  "app_name": "store",
  "model_name": "Order",
  "async": true,
  "notify_email": "user@example.com"
}
```

### Response

```json
{
  "status": "processing",
  "export_id": "exp_xyz789",
  "status_url": "/api/v1/export/exp_xyz789/status/",
  "estimated_time": "2 minutes"
}
```

### Email Notification

When export completes:

```
Subject: Your export is ready

Your export of 25,000 Order records is ready for download.

Download link: https://example.com/api/v1/export/exp_xyz789/download/

This link expires on January 23, 2026.
```

---

## Templates

### Excel Templates

Use predefined templates for formatting:

```python
# apps/store/export_templates.py
from rail_django.extensions.export import ExcelTemplate

class ProductExportTemplate(ExcelTemplate):
    name = "product_catalog"

    # Style configuration
    header_style = {
        "font_bold": True,
        "bg_color": "#4472C4",
        "font_color": "#FFFFFF",
    }

    column_widths = {
        "name": 30,
        "description": 50,
        "price": 15,
    }

    # Conditional formatting
    conditional_formats = [
        {
            "column": "price",
            "condition": "greater_than",
            "value": 1000,
            "format": {"bg_color": "#FFC7CE"},
        },
    ]
```

### Use Template

```json
{
  "app_name": "store",
  "model_name": "Product",
  "template_id": "product_catalog"
}
```

---

## Examples

### Basic Export

```bash
curl -X POST /api/v1/export/ \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "app_name": "store",
    "model_name": "Product",
    "file_extension": "xlsx"
  }'
```

### Filtered Export

```bash
curl -X POST /api/v1/export/ \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "app_name": "store",
    "model_name": "Order",
    "file_extension": "csv",
    "filters": {
      "status": "completed",
      "created_at__gte": "2026-01-01"
    },
    "fields": ["reference", "customer__name", "total", "created_at"]
  }'
```

### Programmatic Export

```python
from rail_django.extensions.export import Exporter

# Create exporter
exporter = Exporter(
    model=Product,
    filters={"is_active": True},
    fields=["id", "name", "sku", "price"],
    format="xlsx",
)

# Generate file
file_path = exporter.export()

# Or get as bytes
file_bytes = exporter.export_to_bytes()
```

---

## Best Practices

### 1. Limit Exports

```python
RAIL_DJANGO_EXPORT = {
    "max_records": 50000,
    "max_file_size_mb": 50,
}
```

### 2. Use Filters

```python
# ❌ Avoid exporting millions of records
{"model_name": "LogEntry"}

# ✅ Use filters
{
    "model_name": "LogEntry",
    "filters": {"created_at__gte": "2026-01-01"},
    "limit": 10000
}
```

### 3. Select Only Needed Fields

```json
{
  "fields": ["id", "name", "price"]
}
```

### 4. Use Async for Large Exports

```json
{
  "async": true,
  "notify_email": "user@example.com"
}
```

### 5. Configure Retention

```python
RAIL_DJANGO_EXPORT = {
    "retention_days": 7,  # Automatically delete after 7 days
}
```

### 6. Monitor Exports

```python
# Log all exports
RAIL_DJANGO_AUDIT = {
    "track_system_events": True,
}
```

---

## See Also

- [Reporting & BI](./reporting.md) - Analytical reports
- [Audit & Logging](./audit.md) - Export tracking
- [Configuration](../graphql/configuration.md) - All settings

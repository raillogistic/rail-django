# Tutorial 6: Advanced Features

Rail Django comes with several "Enterprise" features pre-integrated. This tutorial covers Webhooks, Subscriptions, Observability, Exporting, Reporting, and Templating.

## 1. Webhooks

Webhooks allow your application to notify external systems when data changes.

### Configuration

Define your endpoints in `settings.py`:

```python
RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": {
        "enabled": True,
        "endpoints": [
            {
                "name": "analytics_service",
                "url": "https://analytics.example.com/ingest",
                "include_models": ["shop.Order"], # Only send Orders
                "events": {"created": True, "updated": False},
                "signing_secret": "my-secret-key", # Secure your payload
            }
        ]
    }
}
```

Now, whenever an `Order` is created, a JSON payload is POSTed to the URL.

### Payload Example

```json
{
  "event_type": "created",
  "model": "shop.Order",
  "data": {
    "id": 123,
    "total": "99.00"
  },
  "timestamp": "..."
}
```

## 2. Subscriptions

Subscriptions allow clients to listen for real-time updates via WebSockets.

### Requirements
You must install `channels` and `channels-graphql-ws`.

### Configuration

```python
"subscription_settings": {
    "enable_subscriptions": True,
    "include_models": ["chat.Message"],
}
```

### Client Usage

```graphql
subscription {
  message_created {
    node {
      id
      text
      sender { username }
    }
  }
}
```

Whenever a `Message` is saved in Django, the client receives the data instantly.

## 3. Observability (Sentry / OpenTelemetry)

Rail Django can automatically report GraphQL errors and performance traces.

### Sentry Integration

If you have `sentry-sdk` installed:

```python
GRAPHQL_SCHEMA_PLUGINS = {
    "rail_django.extensions.observability.SentryIntegrationPlugin": {
        "enabled": True
    }
}
```

This ensures that:
1.  GraphQL errors are grouped correctly in Sentry.
2.  Variables are captured (can be redacted).
3.  Operation names are used as transaction names.

## 4. Data Exporting

Rail Django provides a robust system for exporting data to CSV and Excel, integrating with your existing GraphQL filters.

### Usage via API

Send a POST request to `/api/export/`:

```json
{
    "app_name": "shop",
    "model_name": "Order",
    "file_extension": "xlsx",
    "fields": [
        "id",
        {"accessor": "customer.email", "title": "Customer"},
        "total",
        "created_at"
    ],
    "variables": {
        "status": "paid",
        "created_at__year": 2024
    }
}
```

The server will return a downloadable file.

### Usage via Python

```python
from rail_django.extensions.exporting import export_model_to_excel

content = export_model_to_excel(
    app_name="shop",
    model_name="Order",
    fields=["id", "total"],
    filters={"status": "paid"}
)
with open("orders.xlsx", "wb") as f:
    f.write(content)
```

### Security Configuration

Configure `RAIL_DJANGO_EXPORT` in `settings.py` to control access:

```python
RAIL_DJANGO_EXPORT = {
    "allowed_models": ["shop.Order"],
    "export_fields": {
        "shop.Order": ["id", "total", "customer.email", "created_at"]
    },
    "rate_limit": {
        "enable": True,
        "max_requests": 10
    }
}
```

## 5. Reporting & BI

The Reporting module allows you to build internal dashboards and datasets backed by your Django models.

### Defining a Dataset

Create a `ReportingDataset` to define the semantic layer over your model.

```python
from rail_django.extensions.reporting import ReportingDataset

dataset = ReportingDataset.objects.create(
    code="sales_by_city",
    model="shop.Order",
    dimensions=[
        {"name": "city", "field": "customer__city"},
        {"name": "month", "field": "created_at", "transform": "trunc:month"}
    ],
    metrics=[
        {"name": "total_sales", "field": "total", "aggregation": "sum"},
        {"name": "order_count", "field": "id", "aggregation": "count"}
    ]
)
```

### Querying Data

You can now query this dataset via the auto-generated GraphQL API or Python.

```python
results = dataset.run_query({
    "dimensions": ["city"],
    "metrics": ["total_sales"],
    "ordering": ["-total_sales"],
    "limit": 10
})
```

## 6. PDF Templating

Generate PDFs using Django templates.

### Decorator Usage

```python
from rail_django.extensions.templating import pdf_template

@pdf_template(
    template_name="invoices/invoice.html",
    file_name="invoice_{{ object.id }}.pdf"
)
def invoice_view(request, pk):
    return Order.objects.get(pk=pk)
```

This registers an endpoint at `/api/templates/invoices/invoice.html/<pk>/`.

## 7. Schema Export & Diffing

You can export your schema for documentation or client generation.

**Endpoint:** `GET /api/v1/schemas/default/export/?format=sdl`

Rail Django also keeps a **Schema Registry**, tracking changes to your API over time. This is useful for detecting breaking changes before deployment.

## Conclusion

Congratulations! You have toured the core features of Rail Django. You are now ready to build production-grade GraphQL APIs with minimal boilerplate and maximum security.

Check the `docs/` folder in the repository for deep dives into specific modules.
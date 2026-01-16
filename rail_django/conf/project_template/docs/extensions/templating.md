# PDF Generation (Templating)

## Overview

Rail Django includes a PDF generation system using HTML templates. This guide covers configuration, template definitions, REST endpoints, and best practices.

---

## Table of Contents

1. [Configuration](#configuration)
2. [Template Types](#template-types)
3. [REST Endpoints](#rest-endpoints)
4. [Asynchronous Rendering](#asynchronous-rendering)
5. [Post-Processing](#post-processing)
6. [Programmatic API](#programmatic-api)
7. [Template Structure](#template-structure)
8. [Best Practices](#best-practices)

---

## Configuration

### Basic Configuration

```python
# root/settings/base.py
RAIL_DJANGO_TEMPLATING = {
    # Activation
    "enabled": True,

    # Rendering engine
    "engine": "weasyprint",  # "weasyprint" or "wkhtmltopdf"

    # Template paths
    "template_dirs": [
        BASE_DIR / "templates" / "pdf",
    ],

    # Temporary storage
    "temp_dir": "/tmp/pdf_generation/",
    "retention_hours": 24,

    # Security
    "require_authentication": True,
    "require_permission": True,

    # Default options
    "default_options": {
        "page_size": "A4",
        "margin_top": "20mm",
        "margin_bottom": "20mm",
        "margin_left": "15mm",
        "margin_right": "15mm",
    },
}
```

### Installation

```bash
# WeasyPrint (recommended)
pip install weasyprint

# Or wkhtmltopdf
# sudo apt-get install wkhtmltopdf
# pip install pdfkit
```

---

## Template Types

### Model Templates

Templates linked to a specific model.

```python
# apps/store/pdf_templates.py
from rail_django.extensions.templating import ModelPDFTemplate

class InvoiceTemplate(ModelPDFTemplate):
    """
    Invoice template for orders.
    """
    name = "invoice"
    model = "store.Order"
    template_path = "pdf/invoice.html"

    # PDF options
    page_size = "A4"
    orientation = "portrait"

    def get_context(self, instance):
        """
        Returns template context.
        """
        return {
            "order": instance,
            "company": get_company_info(),
            "items": instance.items.all(),
            "subtotal": instance.subtotal,
            "tax": instance.tax,
            "total": instance.total,
        }
```

### Function Templates

Templates for custom documents.

```python
from rail_django.extensions.templating import FunctionPDFTemplate

class MonthlyReportTemplate(FunctionPDFTemplate):
    """
    Monthly report template.
    """
    name = "monthly_report"
    template_path = "pdf/monthly_report.html"

    def get_context(self, **kwargs):
        """
        Returns template context.
        """
        month = kwargs.get("month")
        year = kwargs.get("year")

        return {
            "month": month,
            "year": year,
            "orders": Order.objects.filter(
                created_at__month=month,
                created_at__year=year,
            ),
            "stats": calculate_monthly_stats(month, year),
        }
```

---

## REST Endpoints

### POST /api/v1/pdf/generate/

Generates a PDF from a template.

```bash
curl -X POST /api/v1/pdf/generate/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "invoice",
    "model": "store.Order",
    "object_id": "42",
    "options": {
      "orientation": "portrait"
    }
  }'
```

### Response

```json
{
  "status": "success",
  "pdf_id": "pdf_abc123",
  "download_url": "/api/v1/pdf/pdf_abc123/download/",
  "file_size": "125 KB",
  "expires_at": "2026-01-17T12:00:00Z"
}
```

### GET /api/v1/pdf/{id}/download/

Downloads the generated PDF.

```bash
curl -O /api/v1/pdf/pdf_abc123/download/ \
  -H "Authorization: Bearer <jwt>"
```

### POST /api/v1/pdf/preview/

Generates an HTML preview.

```bash
curl -X POST /api/v1/pdf/preview/ \
  -H "Authorization: Bearer <jwt>" \
  -d '{
    "template": "invoice",
    "model": "store.Order",
    "object_id": "42"
  }'
```

---

## Asynchronous Rendering

For complex documents, use asynchronous rendering.

### Configuration

```python
RAIL_DJANGO_TEMPLATING = {
    "async_rendering": True,
    "async_backend": "celery",
    "async_timeout": 300,  # 5 minutes
}
```

### Request

```json
{
  "template": "annual_report",
  "params": { "year": 2025 },
  "async": true,
  "notify_email": "user@example.com"
}
```

### Response

```json
{
  "status": "processing",
  "pdf_id": "pdf_xyz789",
  "status_url": "/api/v1/pdf/pdf_xyz789/status/"
}
```

### Status Endpoint

```json
{
  "status": "completed",
  "progress": 100,
  "download_url": "/api/v1/pdf/pdf_xyz789/download/"
}
```

---

## Post-Processing

### Watermarks

```python
class DraftInvoiceTemplate(ModelPDFTemplate):
    name = "draft_invoice"
    model = "store.Order"
    template_path = "pdf/invoice.html"

    # Watermark configuration
    watermark = {
        "text": "DRAFT",
        "font_size": 60,
        "color": "#CCCCCC",
        "angle": 45,
        "opacity": 0.3,
    }
```

### Encryption

```python
class ConfidentialReportTemplate(FunctionPDFTemplate):
    name = "confidential_report"
    template_path = "pdf/report.html"

    # Encryption
    encryption = {
        "user_password": None,  # Open without password
        "owner_password": "secret",  # Edit with password
        "permissions": ["print", "copy"],
    }
```

### Digital Signatures

```python
class SignedContractTemplate(ModelPDFTemplate):
    name = "signed_contract"
    model = "contracts.Contract"
    template_path = "pdf/contract.html"

    # Digital signature
    signature = {
        "enabled": True,
        "certificate_path": "/certs/signing.p12",
        "certificate_password": os.environ.get("CERT_PASSWORD"),
        "reason": "Document approval",
        "location": "Paris, France",
    }
```

---

## Programmatic API

### Generate PDF

```python
from rail_django.extensions.templating import PDFGenerator

# From model instance
generator = PDFGenerator(template="invoice")
pdf_bytes = generator.render(instance=order)

# From parameters
generator = PDFGenerator(template="monthly_report")
pdf_bytes = generator.render(month=1, year=2026)

# Save to file
generator.render_to_file(instance=order, output_path="/tmp/invoice.pdf")
```

### Custom Options

```python
generator = PDFGenerator(
    template="invoice",
    options={
        "page_size": "Letter",
        "orientation": "landscape",
        "margin_top": "10mm",
    },
)
```

### Direct HTML to PDF

```python
from rail_django.extensions.templating import html_to_pdf

html_content = render_to_string("my_template.html", context)
pdf_bytes = html_to_pdf(html_content, options={"page_size": "A4"})
```

---

## Template Structure

### Basic Template

```html
<!-- templates/pdf/invoice.html -->
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Invoice {{ order.reference }}</title>
    <style>
      @page {
        size: A4;
        margin: 20mm 15mm;
        @top-right {
          content: "Page " counter(page) " of " counter(pages);
        }
      }

      body {
        font-family: "Helvetica Neue", sans-serif;
        font-size: 12pt;
        line-height: 1.4;
      }

      .header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 30px;
      }

      .logo {
        max-height: 60px;
      }

      table {
        width: 100%;
        border-collapse: collapse;
      }

      th,
      td {
        padding: 8px;
        border-bottom: 1px solid #ddd;
      }

      .total-row {
        font-weight: bold;
        background-color: #f5f5f5;
      }

      .footer {
        position: fixed;
        bottom: 0;
        width: 100%;
        text-align: center;
        font-size: 10pt;
        color: #666;
      }
    </style>
  </head>
  <body>
    <div class="header">
      <img src="{{ company.logo_url }}" alt="Logo" class="logo" />
      <div class="invoice-info">
        <h1>INVOICE</h1>
        <p>{{ order.reference }}</p>
        <p>{{ order.created_at|date:"F d, Y" }}</p>
      </div>
    </div>

    <div class="addresses">
      <div class="from">
        <strong>{{ company.name }}</strong><br />
        {{ company.address }}<br />
        {{ company.city }}, {{ company.postal_code }}
      </div>
      <div class="to">
        <strong>{{ order.customer.name }}</strong><br />
        {{ order.customer.address }}<br />
        {{ order.customer.city }}, {{ order.customer.postal_code }}
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Description</th>
          <th>Qty</th>
          <th>Unit Price</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {% for item in items %}
        <tr>
          <td>{{ item.product.name }}</td>
          <td>{{ item.quantity }}</td>
          <td>${{ item.unit_price }}</td>
          <td>${{ item.total }}</td>
        </tr>
        {% endfor %}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="3">Subtotal</td>
          <td>${{ subtotal }}</td>
        </tr>
        <tr>
          <td colspan="3">Tax (20%)</td>
          <td>${{ tax }}</td>
        </tr>
        <tr class="total-row">
          <td colspan="3">Total</td>
          <td>${{ total }}</td>
        </tr>
      </tfoot>
    </table>

    <div class="footer">
      {{ company.name }} - {{ company.registration_number }}
    </div>
  </body>
</html>
```

### Template with Charts

```html
<!-- Use inline SVG for charts -->
<div class="chart">
  <svg viewBox="0 0 400 200">
    {% for point in chart_data %}
    <rect
      x="{{ point.x }}"
      y="{{ 200 - point.value }}"
      width="30"
      height="{{ point.value }}"
      fill="#4472C4"
    />
    {% endfor %}
  </svg>
</div>
```

---

## Best Practices

### 1. Optimize Images

```python
RAIL_DJANGO_TEMPLATING = {
    "image_optimization": {
        "enabled": True,
        "max_width": 800,
        "quality": 85,
    },
}
```

### 2. Use Caching

```python
from django.core.cache import cache

class CachedReportTemplate(FunctionPDFTemplate):
    def render(self, **kwargs):
        cache_key = f"pdf_report_{kwargs['year']}_{kwargs['month']}"
        cached = cache.get(cache_key)

        if cached:
            return cached

        pdf_bytes = super().render(**kwargs)
        cache.set(cache_key, pdf_bytes, timeout=3600)

        return pdf_bytes
```

### 3. Handle Errors Gracefully

```python
from rail_django.extensions.templating import PDFGenerator, PDFGenerationError

try:
    pdf = PDFGenerator(template="invoice").render(instance=order)
except PDFGenerationError as e:
    logger.error(f"PDF generation failed: {e}")
    # Fallback or notification
```

### 4. Test Templates

```python
from django.test import TestCase
from rail_django.extensions.templating import PDFGenerator

class PDFTemplateTests(TestCase):
    def test_invoice_generation(self):
        order = Order.objects.create(...)
        generator = PDFGenerator(template="invoice")
        pdf_bytes = generator.render(instance=order)

        self.assertIsNotNone(pdf_bytes)
        self.assertGreater(len(pdf_bytes), 0)
        # Check PDF header
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
```

---

## See Also

- [Data Export](./exporting.md) - Excel/CSV exports
- [Reporting & BI](./reporting.md) - Analytical reports
- [Configuration](../graphql/configuration.md) - All settings

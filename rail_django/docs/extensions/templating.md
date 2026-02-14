# PDF & Excel Templating

Rail Django provides a powerful templating extension that lets you generate professional PDF documents and Excel spreadsheets directly from your Django models.

## Overview

The templating system lets you:
- Generate PDFs from HTML/CSS using **WeasyPrint** or **wkhtmltopdf**.
- Create dynamic Excel reports from model data.
- Serve generated documents via REST endpoints.
- Handle complex document generation asynchronously.
- Add watermarks, encryption, and digital signatures to PDFs.

## Configuration

Enable the templating extension in your settings:

```python
RAIL_DJANGO_TEMPLATING = {
    "enabled": True,
    # Rendering engine: 'weasyprint' (recommended) or 'wkhtmltopdf'
    "engine": "weasyprint",
    "template_dirs": [
        BASE_DIR / "templates" / "pdf",
    ],
    "require_authentication": True,
    "async_rendering": False, # Enable for heavy documents
}
```

### Installation

```bash
# For WeasyPrint
pip install weasyprint

# For Excel support
pip install openpyxl
```

## PDF Generation

### 1. Defining a Model Template

You can link a PDF template to a specific model using a class-based approach or a decorator.

**Class-based approach:**
```python
from rail_django.extensions.templating import ModelPDFTemplate

class InvoiceTemplate(ModelPDFTemplate):
    name = "invoice"
    model = "store.Order"
    template_path = "pdf/invoice.html"

    def get_context(self, instance):
        return {
            "order": instance,
            "items": instance.items.all(),
            "company": get_company_info(),
        }
```

**Decorator approach:**
```python
from rail_django.extensions.templating import model_pdf_template

class Order(models.Model):
    # ...
    @model_pdf_template(content="pdf/invoice.html", title="Invoice")
    def invoice_pdf(self, request=None):
        return {"order": self}
```

### 2. HTML Template Structure
Use standard Django template syntax. For PDF styling, use standard CSS.

```html
<!-- templates/pdf/invoice.html -->
<!DOCTYPE html>
<html>
<head>
    <style>
        @page { size: A4; margin: 20mm; }
        body { font-family: serif; }
        .header { text-align: center; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Invoice #{{ order.reference }}</h1>
    </div>
    <!-- ... -->
</body>
</html>
```

### 3. Accessing the PDF
PDFs are served at generated URLs:
`GET /api/v1/templates/<app>/<model>/<template_name>/<pk>/`

Or via a generic generation endpoint:
`POST /api/v1/pdf/generate/` with `{"template": "invoice", "object_id": "42"}`

## Excel Generation

Generate spreadsheets easily from your models.

```python
from rail_django.extensions.templating import model_excel_template

class Product(models.Model):
    @model_excel_template(url="reports/stock")
    def export_stock(self):
        return [
            ["SKU", "Name", "Stock"],
            [self.sku, self.name, self.inventory_count]
        ]
```

## Advanced Features

### Asynchronous Rendering
For heavy documents, enable `async_rendering`. The generation will return a `pdf_id` which can be used to poll for status or receive a notification via WebSockets/Subscriptions when ready.

### Post-Processing
Apply watermarks or encryption to your PDFs:

```python
class ConfidentialTemplate(ModelPDFTemplate):
    # ...
    watermark = {"text": "CONFIDENTIAL", "opacity": 0.2}
    encryption = {"owner_password": "secure-password"}
```

## Programmatic Usage

You can also generate PDFs directly in your Python code:

```python
from rail_django.extensions.templating import PDFGenerator

generator = PDFGenerator(template="invoice")
pdf_bytes = generator.render(instance=order)
```

## See Also

- [Data Exporting](./exporting.md) - For CSV and basic Excel exports.
- [Background Tasks](./tasks.md) - For handling long-running generation.
- [Webhooks](./webhooks.md) - For notifying external systems when a document is ready.

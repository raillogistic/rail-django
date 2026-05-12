# Templating (PDF & Excel) Reference

Rail Django provides templating extensions to generate professional PDF documents and Excel spreadsheets directly from Django models.

## Excel Generation (`rail_django.extensions.excel`)

The Excel extension provides a decorator-based approach to register Excel export endpoints for your models.

```python
from django.db import models
from rail_django.extensions.excel import model_excel_template

class Product(models.Model):
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50)
    inventory_count = models.PositiveIntegerField(default=0)

    @model_excel_template(url="reports/stock", title="Product Stock Export")
    def export_stock(self):
        # The method must return a list of lists representing rows.
        # The first row is typically the header.
        products = Product.objects.all()
        return [
            ["SKU", "Name", "Stock"],
            *[[p.sku, p.name, p.inventory_count] for p in products]
        ]
```
- **Endpoints**: These templates are exposed via the `/api/v1/templates/<app>/<model>/<template_name>/<pk>/` endpoints or registered excel URLs.
- **Integration**: To expose the Excel endpoints, you must include `excel_urlpatterns()` in your `urls.py`.

```python
# urls.py
from rail_django.extensions.excel import excel_urlpatterns

urlpatterns = [
    # ... your URLs
] + excel_urlpatterns()
```

## PDF Generation (`rail_django.extensions.templating`)

Generate PDFs from HTML/CSS using WeasyPrint (recommended) or wkhtmltopdf.

### 1. Decorator Approach

The `@model_pdf_template` decorator can be applied to either a specific method or the entire model class.

**Method-Level Usage:**
```python
from rail_django.extensions.templating import model_pdf_template

class Order(models.Model):
    reference = models.CharField(max_length=50)
    
    @model_pdf_template(content="pdf/invoice.html", title="Invoice")
    def invoice_pdf(self, request=None):
        # Return the context dictionary for the HTML template
        return {
            "order": self,
            "items": self.items.all()
        }
```

**Class-Level Usage:**
When applied to a class, it generates a standard template exposing the instance in the context.
```python
from rail_django.extensions.templating import model_pdf_template

@model_pdf_template(
    content="documents/pdf/restitution_slip.html",
    title="Bon de restitution",
)
class Restitution(models.Model):
    # Model fields here...
    pass
```

### 2. Class-Based Approach
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
        }
```

### Advanced Features
- **Async Rendering**: Enable `async_rendering` in settings for heavy documents.
- **Watermarks & Encryption**: Configured via class attributes on `ModelPDFTemplate`.

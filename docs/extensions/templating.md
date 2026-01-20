# Templating Extension

Module: `rail_django.extensions.templating`

The templating extension provides decorators for generating PDF and Excel documents from Django models.

## PDF Templates

### Quick Start

```python
from rail_django.extensions.templating import model_pdf_template

class WorkOrder(models.Model):
    number = models.CharField(max_length=50)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    @model_pdf_template(
        content="pdf/workorders/detail.html",
        header="pdf/shared/header.html",
        footer="pdf/shared/footer.html",
        url="workorders/printable/detail",
        config={"margin": "15mm", "font_family": "Inter, sans-serif"},
    )
    def printable_detail(self):
        return {"title": f"OT #{self.pk}", "lines": self.lines.all()}
```

The view is automatically available at:
```
/api/templates/workorders/printable/detail/<pk>/
```

### Decorator Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `content` | `str` | **Required.** Path to the main content template. |
| `header` | `str` | Path to header template. Uses default from settings if omitted. |
| `footer` | `str` | Path to footer template. Uses default from settings if omitted. |
| `url` | `str` | Custom URL path. Defaults to `<app_label>/<model_name>/<function_name>`. |
| `config` | `dict` | Style overrides (margin, padding, fonts, page_size, etc.). |
| `roles` | `list[str]` | RBAC role names required for access. |
| `permissions` | `list[str]` | Django permission strings required. |
| `guard` | `str` | GraphQL guard name (defaults to "retrieve"). |
| `require_authentication` | `bool` | Whether authentication is required (default: `True`). |
| `title` | `str` | Human-readable label surfaced to the frontend. |
| `allow_client_data` | `bool` | Allow whitelisted query params in template context. |
| `client_data_fields` | `list[str]` | Allowed client data keys (whitelist). |
| `client_data_schema` | `list[dict]` | Schema describing expected client fields. |

### Configuration Options

```python
config = {
    "page_size": "A4",              # A4, Letter, Legal, etc.
    "orientation": "portrait",       # portrait, landscape
    "margin": "10mm",               # Page margins
    "padding": "0",                 # Body padding
    "font_family": "Arial, sans-serif",
    "font_size": "12pt",
    "text_color": "#222222",
    "background_color": "#ffffff",
    "header_spacing": "10mm",
    "footer_spacing": "12mm",
    "content_spacing": "8mm",
    "extra_css": "",                # Additional CSS
    "renderer": "weasyprint",       # weasyprint or wkhtmltopdf
}
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/templates/<template_path>/<pk>/` | Download PDF |
| `GET /api/templates/catalog/` | List available templates |
| `GET /api/templates/preview/<template_path>/<pk>/` | HTML preview (DEBUG only) |
| `GET /api/templates/jobs/<job_id>/` | Async job status |
| `GET /api/templates/jobs/<job_id>/download/` | Download async job result |

### Async PDF Generation

Add `?async=true` to generate PDFs asynchronously:

```
GET /api/templates/workorders/printable/detail/123/?async=true
```

Response:
```json
{
    "job_id": "abc123...",
    "status": "pending",
    "status_url": "http://example.com/api/templates/jobs/abc123.../",
    "download_url": "http://example.com/api/templates/jobs/abc123.../download/",
    "expires_in": 3600
}
```

### Post-Processing

Enable watermarks, encryption, or digital signatures:

```python
RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    "postprocess": {
        "enable": True,
        "watermark": {
            "text": "CONFIDENTIAL",
            "opacity": 0.12,
            "rotation": -30,
        },
        "encryption": {
            "user_password": "viewonly",
            "owner_password": "admin123",
            "permissions": {"print": True, "copy": False},
        },
    },
}
```

### Standalone Function Templates

For templates not tied to a model:

```python
from rail_django.extensions.templating import pdf_template

@pdf_template(
    content="pdf/reports/monthly.html",
    url="reports/monthly",
    title="Monthly Report",
)
def generate_monthly_report(request, pk):
    return {"month": pk, "data": get_report_data(pk)}
```

### Programmatic PDF Generation

```python
from rail_django.extensions.templating import render_pdf, PdfBuilder

# Simple usage
pdf_bytes = render_pdf(
    "pdf/invoice.html",
    {"invoice": invoice},
    config={"page_size": "A4"},
)

# Builder pattern
pdf_bytes = (
    PdfBuilder()
    .header("pdf/header.html")
    .content("pdf/invoice.html")
    .footer("pdf/footer.html")
    .context(invoice=invoice, company=company)
    .config(margin="20mm", font_size="11pt")
    .render()
)
```

### URL Configuration

```python
# urls.py
from django.urls import path, include
from rail_django.extensions.templating import template_urlpatterns

urlpatterns = [
    path("api/", include(template_urlpatterns())),
]
```

### Settings

```python
RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    "url_prefix": "templates",
    "default_header_template": "pdf/default_header.html",
    "default_footer_template": "pdf/default_footer.html",
    "renderer": "weasyprint",
    "expose_errors": False,
    "enable_preview": True,  # Defaults to DEBUG
    "base_url": "request",   # Use request URL as base

    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30,
    },

    "cache": {
        "enable": False,
        "timeout_seconds": 300,
        "vary_on_user": True,
    },

    "async_jobs": {
        "enable": False,
        "backend": "thread",  # thread, celery, rq
        "expires_seconds": 3600,
    },

    "catalog": {
        "enable": True,
        "require_authentication": True,
        "filter_by_access": True,
    },
}
```

### Optional Dependencies

- `weasyprint` - Default PDF renderer
- `wkhtmltopdf` - Alternative renderer (requires binary)
- `pypdf` - Encryption and watermark overlays
- `pyhanko` - Digital signatures

---

## Excel Templates

Module: `rail_django.extensions.excel_export`

### Quick Start

```python
from rail_django.extensions.excel_export import model_excel_template

class Product(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    @model_excel_template(
        url="products/export",
        title="Product Export",
        config={
            "header_style": {
                "bold": True,
                "fill_color": "4472C4",
                "font_color": "FFFFFF",
            },
            "freeze_panes": True,
            "column_widths": "auto",
        },
    )
    def export_products(self):
        """Export all products to Excel."""
        products = Product.objects.all()
        return [
            ["Name", "Price", "Created At"],  # First row = headers
            *[[p.name, p.price, p.created_at] for p in products]
        ]
```

The view is automatically available at:
```
/api/excel/products/export/?pk=1
```

or without pk for function templates that don't require a model instance:
```
/api/excel/reports/summary/
```

### Return Format

**Single Sheet:**
```python
def export_data(self):
    return [
        ["Header1", "Header2", "Header3"],  # First row = headers
        ["Value1", "Value2", "Value3"],
        ["Value4", "Value5", "Value6"],
    ]
```

**Multiple Sheets:**
```python
def export_report(self):
    return {
        "Products": [
            ["Name", "Price"],
            ["Widget", 9.99],
            ["Gadget", 19.99],
        ],
        "Summary": [
            ["Metric", "Value"],
            ["Total Products", 2],
            ["Average Price", 14.99],
        ],
    }
```

### Decorator Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | Custom URL path. Defaults to `<app_label>/<model_name>/<function_name>`. |
| `title` | `str` | Human-readable title and default filename. |
| `config` | `dict` | Styling and formatting options. |
| `roles` | `list[str]` | RBAC role names required for access. |
| `permissions` | `list[str]` | Django permission strings required. |
| `guard` | `str` | GraphQL guard name (defaults to "retrieve"). |
| `require_authentication` | `bool` | Whether authentication is required (default: `True`). |
| `allow_client_data` | `bool` | When `True`, query params are available via `request.rail_excel_client_data`. |
| `client_data_fields` | `list[str]` | Allowed query parameter names. If empty, all params are allowed. |

### Passing Parameters via Request

The decorated method can accept a `request` parameter to access query parameters, the user, and other request data:

```python
@model_excel_template(
    url="products/export",
    title="Product Export",
    allow_client_data=True,
    client_data_fields=["category", "status", "start_date", "end_date"],
)
def export_products(self, request):
    """Export products with filtering."""
    # Option 1: Direct access to query params
    category = request.GET.get("category")
    status = request.GET.get("status")

    # Option 2: Via client_data (sanitized, bounded to 1024 chars)
    client_data = getattr(request, "rail_excel_client_data", {})
    start_date = client_data.get("start_date")
    end_date = client_data.get("end_date")

    # Access the authenticated user
    user = request.user

    # Build filtered queryset
    products = Product.objects.all()
    if category:
        products = products.filter(category__name=category)
    if status == "active":
        products = products.filter(is_active=True)
    if start_date:
        products = products.filter(created_at__gte=start_date)
    if end_date:
        products = products.filter(created_at__lte=end_date)

    return [
        ["SKU", "Name", "Category", "Price", "Status"],
        *[[p.sku, p.name, p.category.name, float(p.price),
           "Active" if p.is_active else "Inactive"] for p in products]
    ]
```

**Call with query parameters:**
```
GET /api/excel/products/export/?pk=1&category=Electronics&status=active&start_date=2024-01-01
```

### Multi-Sheet Exports with Parameters

```python
@model_excel_template(
    url="products/full-report",
    title="Full Product Report",
    allow_client_data=True,
    client_data_fields=["year", "include_inactive"],
)
def export_full_report(self, request):
    """Generate a multi-sheet report with filtering."""
    client_data = getattr(request, "rail_excel_client_data", {})
    year = client_data.get("year", "2024")
    include_inactive = client_data.get("include_inactive") == "true"

    products = Product.objects.filter(created_at__year=year)
    if not include_inactive:
        products = products.filter(is_active=True)

    # Return dict for multi-sheet output
    return {
        "All Products": [
            ["SKU", "Name", "Price", "Inventory"],
            *[[p.sku, p.name, float(p.price), p.inventory_count] for p in products]
        ],
        "By Category": [
            ["Category", "Count", "Total Value"],
            *[
                [cat.name, cat.product_count, float(cat.total_value)]
                for cat in Category.objects.annotate(
                    product_count=Count("products"),
                    total_value=Sum("products__price")
                )
            ]
        ],
        "Summary": [
            ["Metric", "Value"],
            ["Year", year],
            ["Total Products", products.count()],
            ["Active Products", products.filter(is_active=True).count()],
            ["Total Inventory", sum(p.inventory_count for p in products)],
            ["Generated By", request.user.username],
        ],
    }
```

**Call:**
```
GET /api/excel/products/full-report/?pk=1&year=2024&include_inactive=false
```

### Configuration Options

```python
config = {
    # Sheet configuration
    "sheet_name": "Data",           # Default sheet name (single-sheet exports)

    # Header styling
    "header_style": {
        "bold": True,
        "fill_color": "4472C4",     # Hex color (no #)
        "font_color": "FFFFFF",
        "font_size": 11,
        "alignment": "center",      # left, center, right
    },

    # Data cell styling
    "cell_style": {
        "font_size": 10,
        "alignment": "left",
    },

    # Alternating row colors
    "alternate_row_color": "F2F2F2",

    # Column configuration
    "column_widths": "auto",        # "auto" or dict {0: 20, 1: 15}
    "freeze_panes": True,           # Freeze header row
    "auto_filter": True,            # Add filter dropdowns to headers

    # Number formats (Excel format strings)
    "number_formats": {
        1: "#,##0.00",              # Column index: format
        2: "yyyy-mm-dd",
    },

    # Borders
    "border_style": "thin",         # thin, medium, thick, none
}
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/excel/<template_path>/` | Download Excel file (pk via query param) |
| `GET /api/excel/<template_path>/?pk=<id>` | Download Excel for specific instance |
| `GET /api/excel/catalog/` | List available templates |
| `GET /api/excel/jobs/<job_id>/` | Async job status |
| `GET /api/excel/jobs/<job_id>/download/` | Download async job result |

### Async Excel Generation

Add `?async=true` to generate Excel files asynchronously:

```
GET /api/excel/products/export/?pk=1&async=true
```

### Standalone Function Templates

For templates not tied to a specific model instance:

```python
from rail_django.extensions.excel_export import excel_template

@excel_template(
    url="reports/sales",
    title="Sales Report",
    allow_client_data=True,
    client_data_fields=["start_date", "end_date", "region"],
)
def generate_sales_report(request):
    """Generate a sales report with optional filtering."""
    client_data = getattr(request, "rail_excel_client_data", {})
    start_date = client_data.get("start_date")
    end_date = client_data.get("end_date")
    region = client_data.get("region")

    sales = Sale.objects.all()
    if start_date:
        sales = sales.filter(date__gte=start_date)
    if end_date:
        sales = sales.filter(date__lte=end_date)
    if region:
        sales = sales.filter(region=region)

    return [
        ["Date", "Product", "Quantity", "Revenue"],
        *[[s.date, s.product.name, s.quantity, float(s.revenue)] for s in sales]
    ]
```

**Call:**
```
GET /api/excel/reports/sales/?start_date=2024-01-01&end_date=2024-12-31&region=US
```

### Using PK for Model Instance Context

When using `@model_excel_template`, the `pk` query parameter fetches the model instance which becomes `self`:

```python
class Order(models.Model):
    number = models.CharField(max_length=50)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    @model_excel_template(
        url="orders/export",
        title="Order Details",
    )
    def export_order_details(self):
        """Export a single order with its line items."""
        return [
            ["Product", "Quantity", "Unit Price", "Total"],
            *[
                [line.product.name, line.quantity, float(line.unit_price),
                 float(line.quantity * line.unit_price)]
                for line in self.lines.all()
            ]
        ]
```

**Call:**
```
GET /api/excel/orders/export/?pk=123
```

### Exporting All Records (No PK Required)

For exports that don't need a specific instance, use function templates or ignore `self`:

```python
@model_excel_template(
    url="products/all",
    title="All Products Export",
)
def export_all_products(self, request):
    """Export all products - self is not used."""
    products = Product.objects.select_related("category").all()
    return [
        ["SKU", "Name", "Category", "Price", "Stock"],
        *[[p.sku, p.name, p.category.name, float(p.price), p.inventory_count]
          for p in products]
    ]
```

**Call (pk still required but value doesn't matter for the data):**
```
GET /api/excel/products/all/?pk=1
```

**Better approach - use function template:**
```python
from rail_django.extensions.excel_export import excel_template

@excel_template(
    url="products/all",
    title="All Products Export",
)
def export_all_products(request):
    """Export all products - no pk needed."""
    products = Product.objects.select_related("category").all()
    return [
        ["SKU", "Name", "Category", "Price", "Stock"],
        *[[p.sku, p.name, p.category.name, float(p.price), p.inventory_count]
          for p in products]
    ]
```

**Call (no pk required):**
```
GET /api/excel/products/all/
```

### Programmatic Excel Generation

```python
from rail_django.extensions.excel_export import render_excel

# Generate Excel bytes
excel_bytes = render_excel(
    data=[
        ["Name", "Value"],
        ["Item 1", 100],
        ["Item 2", 200],
    ],
    config={
        "sheet_name": "Report",
        "header_style": {"bold": True, "fill_color": "4472C4"},
    },
)

# Multi-sheet
excel_bytes = render_excel(
    data={
        "Sheet1": [["A", "B"], [1, 2]],
        "Sheet2": [["C", "D"], [3, 4]],
    },
)
```

### URL Configuration

```python
# urls.py
from django.urls import path, include
from rail_django.extensions.excel_export import excel_urlpatterns

urlpatterns = [
    path("api/", include(excel_urlpatterns())),
]
```

### Settings

```python
RAIL_DJANGO_GRAPHQL_EXCEL_EXPORT = {
    "url_prefix": "excel",
    "expose_errors": False,

    "default_config": {
        "header_style": {
            "bold": True,
            "fill_color": "4472C4",
            "font_color": "FFFFFF",
        },
        "freeze_panes": True,
        "column_widths": "auto",
    },

    "rate_limit": {
        "enable": True,
        "window_seconds": 60,
        "max_requests": 30,
    },

    "cache": {
        "enable": False,
        "timeout_seconds": 300,
    },

    "async_jobs": {
        "enable": False,
        "backend": "thread",
        "expires_seconds": 3600,
    },

    "catalog": {
        "enable": True,
        "require_authentication": True,
    },
}
```

### Dependencies

- `openpyxl` - Required for Excel generation

Install with:
```bash
pip install openpyxl
```

---

## Security

Both PDF and Excel templates support:

- **Authentication**: Require login via `require_authentication=True`
- **RBAC Roles**: Restrict access via `roles=["admin", "manager"]`
- **Permissions**: Django permissions via `permissions=["app.export_model"]`
- **Guards**: GraphQL guards via `guard="retrieve"`
- **Rate Limiting**: Configurable per-template rate limits
- **Audit Logging**: Automatic logging of access attempts

---

## Template Context

Both decorators inject these variables into the template context (PDF) or pass them to the decorated function:

| Variable | Description |
|----------|-------------|
| `instance` | The model instance (for model templates) |
| `data` | Return value of the decorated method |
| `request` | The HTTP request object |
| `template_config` | The merged configuration |
| `client_data` | Client-provided query parameters (if enabled) |

---

## Quick Reference

### Excel Export Cheat Sheet

```python
from rail_django.extensions.excel_export import model_excel_template, excel_template

# Basic model export
@model_excel_template(url="products/export", title="Products")
def export(self):
    return [["Col1", "Col2"], ["val1", "val2"]]

# With request access and filtering
@model_excel_template(
    url="products/filtered",
    allow_client_data=True,
    client_data_fields=["status", "category"],
)
def export_filtered(self, request):
    status = request.GET.get("status")
    # ... filter and return data

# Multi-sheet export
@model_excel_template(url="products/report")
def export_report(self):
    return {
        "Sheet1": [["A", "B"], [1, 2]],
        "Sheet2": [["C", "D"], [3, 4]],
    }

# Standalone function (no model instance needed)
@excel_template(url="reports/daily")
def daily_report(request):
    return [["Date", "Total"], ["2024-01-01", 100]]
```

### URL Patterns

| Template Type | URL Pattern |
|---------------|-------------|
| Model template | `GET /api/excel/<url>/?pk=<id>` |
| Model template + params | `GET /api/excel/<url>/?pk=<id>&param1=value` |
| Function template | `GET /api/excel/<url>/` |
| Function template + params | `GET /api/excel/<url>/?param1=value` |
| Async generation | Add `&async=true` to any URL |
| Catalog | `GET /api/excel/catalog/` |

### PowerShell Examples

```powershell
# Set token
$token = "your-jwt-token"

# Basic export
curl.exe -o export.xlsx "http://localhost:8000/api/excel/products/export/?pk=1" -H "Authorization: Bearer $token"

# With filters
curl.exe -o filtered.xlsx "http://localhost:8000/api/excel/products/export/?pk=1&status=active&category=Electronics" -H "Authorization: Bearer $token"

# Function template (no pk)
curl.exe -o report.xlsx "http://localhost:8000/api/excel/reports/daily/" -H "Authorization: Bearer $token"

# Check catalog
Invoke-RestMethod -Uri "http://localhost:8000/api/excel/catalog/" -Headers @{Authorization="Bearer $token"}

# Async export
Invoke-RestMethod -Uri "http://localhost:8000/api/excel/products/export/?pk=1&async=true" -Headers @{Authorization="Bearer $token"}
```

# Exporting

Rail Django provides utilities to export data to Excel (.xlsx) and CSV formats.

## Usage

You can use the `ModelExporter` class to generate reports.

### Basic Export

```python
from rail_django.extensions.exporting import ModelExporter
from my_app.models import User

def export_users(request):
    queryset = User.objects.all()
    
    exporter = ModelExporter(
        queryset=queryset,
        fields=["username", "email", "date_joined", "is_active"]
    )
    
    # Returns a StreamingHttpResponse
    return exporter.to_csv_response(filename="users.csv")
```

### Advanced Export (Custom Columns)

You can define custom columns with callables or traversal paths.

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

# Export to Excel
return exporter.to_excel_response(filename="orders.xlsx")
```

## GraphQL Integration

You can expose export capabilities via a custom Mutation or Query that returns a file download URL or the file content (base64).

*Note: Direct file download is often better handled via a standard Django View, as shown above, because handling binary blobs in GraphQL can be inefficient.*

### Example View

```python
# views.py
from django.http import HttpResponse
from rail_django.extensions.exporting import export_model_to_excel

def download_products(request):
    return export_model_to_excel(
        Product.objects.all(),
        fields=["name", "price", "stock"],
        filename="products.xlsx"
    )
```

Add to `urls.py`:

```python
path("downloads/products/", download_products)
```

# Templating

Generate invoices, receipts, and reports directly from your store models using PDF or Excel templates.

## PDF Invoices

Turn a model method into a printable PDF endpoint.

### 1. Model Definition

```python
from rail_django.extensions.templating import model_pdf_template

class Order(models.Model):
    # ...
    @model_pdf_template(
        content="pdf/order_invoice.html", 
        title="Order Invoice"
    )
    def invoice_pdf(self, request=None):
        # Return context for the HTML template
        return {
            "order": self,
            "items": self.items.all(),
            "customer": self.customer
        }
```

### 2. HTML Template (`pdf/order_invoice.html`)

```html
<h1>Invoice for Order {{ order.order_number }}</h1>
<p>Customer: {{ customer.full_name }}</p>
<table>
    {% for item in items %}
    <tr>
        <td>{{ item.product.name }}</td>
        <td>{{ item.quantity }}</td>
        <td>{{ item.unit_price }}</td>
    </tr>
    {% endfor %}
</table>
<p>Total: {{ order.total_amount }}</p>
```

### 3. Accessing the PDF

The PDF is served at a generated URL:
`GET /api/templates/store/order/invoice_pdf/<pk>/`

## Excel Reports

Generate stock reports or sales data.

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

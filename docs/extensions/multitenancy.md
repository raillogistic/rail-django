# Multitenancy

Isolate store data (Products, Orders, Customers) for different vendors or regions.

## Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "multitenancy_settings": {
        "enabled": True,
        "tenant_header": "X-Vendor-ID",
        "default_tenant_field": "vendor",
        "isolation_mode": "row"
    }
}
```

## Model Setup

Your models should inherit from `TenantMixin` or include a ForeignKey to your tenant model.

```python
class Vendor(models.Model):
    name = models.CharField(max_length=100)

class Product(models.Model):
    name = models.CharField(max_length=100)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
```

## How It Works

1.  **Context**: The middleware extracts the Vendor ID from the `X-Vendor-ID` header.
2.  **Queries**: Rail Django automatically appends `WHERE vendor_id = <current_vendor>` to all product and order queries.
3.  **Mutations**: New orders and products are automatically assigned to the current vendor.
4.  **Security**: Attempting to query an ID belonging to another vendor will return `404 Not Found`.

## Client Usage

```bash
# Fetch products for Vendor A
curl -H "X-Vendor-ID: 1" http://localhost:8000/graphql -d '{"query": "{ productList { name } }"}'

# Fetch products for Vendor B
curl -H "X-Vendor-ID: 2" http://localhost:8000/graphql -d '{"query": "{ productList { name } }"}'
```

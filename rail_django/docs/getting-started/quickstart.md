# Quickstart Guide

Build a complete, secured GraphQL API with Rail Django in just a few minutes. This guide will walk you through creating a simple store API with Products and Categories.

## 1. Create the Application

Assuming you have already [installed](../getting-started/installation.md) Rail Django and created a project:

```bash
python manage.py startapp store apps/store
```

## 2. Define the Models

Edit `apps/store/models.py` to define your data structure. We'll use `GraphQLMeta` to configure how these models appear in the API.

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class GraphQLMeta(GraphQLMetaConfig):
        filtering = ["name"] # Enable simple filtering
        ordering = ["name"]

class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    class GraphQLMeta(GraphQLMetaConfig):
        # Configure advanced filtering
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={"price": ["gt", "lt", "between"]}
        )
        # Mark SKU as read-only for updates
        fields = GraphQLMetaConfig.Fields(read_only=["sku"])
```

## 3. Register the App

Add the new app to your `INSTALLED_APPS` in `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "rail_django",
    "apps.store",
]
```

## 4. Run Migrations

```bash
python manage.py makemigrations store
python manage.py migrate
```

## 5. Explore the API

Start your server (`python manage.py runserver`) and open `http://localhost:8000/graphql/`.

### Querying Data
Rail Django has automatically created `productList` and `categoryList` root queries.

```graphql
query ListActiveProducts {
  productList(where: { isActive: { eq: true } }) {
    id
    name
    price
    category {
      name
    }
  }
}
```

### Mutating Data
Rail Django has also created CRUD mutations like `createProduct` and `updateProduct`.

```graphql
mutation CreateProduct {
  createProduct(input: {
    name: "Wireless Headphones",
    sku: "HEAD-001",
    price: 150.00,
    categoryId: "1"
  }) {
    ok
    object { id }
  }
}
```

## 6. Secure the API

By default, Rail Django uses Django's permission system. You can restrict access in `GraphQLMeta`:

```python
class Product(models.Model):
    # ...
    class GraphQLMeta:
        access = {
            "operations": {
                "create": {"roles": ["admin"]},
                "delete": {"roles": ["admin"]},
            }
        }
```

## Next Steps

- Learn about [Advanced Filtering](../core/filtering.md).
- Set up [Authentication & MFA](../security/authentication.md).
- Learn how to [Test your API](../guides/testing.md).
- Configure [Webhooks](../extensions/webhooks.md) for event notifications.
- Dive into [Performance Optimization](../core/performance.md).
- Encountering issues? Check the [Troubleshooting Guide](../guides/troubleshooting.md).

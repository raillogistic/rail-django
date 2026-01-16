# Quickstart

## Overview

This guide shows you how to create a complete GraphQL API in 10 minutes with Rail Django.

---

## Objective

Create an API to manage **Products** and **Categories** with:

- List/retrieve queries with filters
- CRUD mutations
- JWT authentication
- Role-based permissions

---

## Step 1: Create the Application

```bash
cd my_project
python manage.py startapp store
```

Rail Django creates the app in `apps/store/`.

---

## Step 2: Define the Models

```python
# apps/store/models.py
"""
Store module models.

This module contains models for product catalog management.
"""
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig


class Category(models.Model):
    """
    Category Model.

    Represents a product category in the catalog.

    Attributes:
        name: Category name.
        description: Optional description.
        is_active: Indicates if the category is active.
    """
    name = models.CharField("Name", max_length=100)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    class GraphQLMeta(GraphQLMetaConfig):
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name"],
            fields={
                "name": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "icontains"],
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
                ),
            },
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "id"],
            default=["name"],
        )


class Product(models.Model):
    """
    Product Model.

    Represents a product in the catalog.

    Attributes:
        name: Product name.
        sku: Unique article code.
        price: Unit price (excluding tax).
        category: Product category.
        is_active: Indicates if the product is active.
        created_at: Creation date.
    """
    name = models.CharField("Name", max_length=200)
    sku = models.CharField("SKU", max_length=50, unique=True)
    price = models.DecimalField("Price", max_digits=10, decimal_places=2)
    description = models.TextField("Description", blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Category"
    )
    is_active = models.BooleanField("Active", default=True)
    created_at = models.DateTimeField("Created at", auto_now_add=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    class GraphQLMeta(GraphQLMetaConfig):
        # Fields
        fields = GraphQLMetaConfig.Fields(
            read_only=["sku", "created_at"],
        )

        # Filtering
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={
                "name": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "icontains", "istartswith"],
                ),
                "sku": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "istartswith"],
                ),
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "gt", "lt", "range"],
                ),
                "category": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
                ),
            },
        )

        # Sorting
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"],
        )
```

---

## Step 3: Register the Application

```python
# root/settings/base.py
INSTALLED_APPS = [
    # ...
    "apps.store",
]
```

---

## Step 4: Apply Migrations

```bash
python manage.py makemigrations store
python manage.py migrate
```

---

## Step 5: Test the API

Start the server:

```bash
python manage.py runserver
```

Open GraphiQL: http://localhost:8000/graphql/graphiql/

### Authentication

```graphql
mutation {
  login(username: "admin", password: "your_password") {
    ok
    token
    user {
      username
    }
  }
}
```

Copy the `token` and add it to the HTTP Headers:

```json
{
  "Authorization": "Bearer <your_token>"
}
```

### Create a Category

```graphql
mutation {
  create_category(
    input: {
      name: "Electronics"
      description: "Electronic devices"
      is_active: true
    }
  ) {
    ok
    object {
      id
      name
    }
    errors {
      field
      message
    }
  }
}
```

### Create a Product

```graphql
mutation {
  create_product(
    input: {
      name: "iPhone 15 Pro"
      sku: "IPHONE-15-PRO"
      price: "1199.00"
      description: "Latest generation Apple smartphone"
      category_id: "1"
      is_active: true
    }
  ) {
    ok
    object {
      id
      name
      sku
      price
      category {
        name
      }
    }
  }
}
```

### List Products

```graphql
query {
  products(
    filters: { is_active__exact: true }
    order_by: ["-price"]
    limit: 10
  ) {
    id
    name
    sku
    price
    category {
      name
    }
  }
}
```

### Advanced Filtering

```graphql
query {
  products(
    filters: {
      price__gte: 100
      price__lte: 500
      category__name__icontains: "electronics"
    }
  ) {
    id
    name
    price
  }
}
```

### Quick Search

```graphql
query {
  products(quick: "iPhone") {
    id
    name
    sku
  }
}
```

### Paginated Query

```graphql
query {
  products_pages(page: 1, per_page: 20) {
    items {
      id
      name
      price
    }
    page_info {
      total_count
      page_count
      current_page
      has_next_page
    }
  }
}
```

---

## Step 6: Add Permissions

Modify `GraphQLMeta` to add restrictions:

```python
class Product(models.Model):
    # ... fields ...

    class GraphQLMeta(GraphQLMetaConfig):
        # ... filtering, ordering ...

        # Permissions by operation
        access = GraphQLMetaConfig.Access(
            operations={
                "list": {"roles": ["*"]},  # Everyone
                "retrieve": {"roles": ["*"]},
                "create": {"roles": ["catalog_manager", "admin"]},
                "update": {"roles": ["catalog_manager", "admin"]},
                "delete": {"roles": ["admin"]},
            }
        )
```

---

## Summary

You have created:

✅ Two models with relationships  
✅ Auto-generated queries with filters and pagination  
✅ CRUD mutations  
✅ JWT authentication  
✅ Permission configuration

---

## Next Steps

- [Queries](../graphql/queries.md) - Advanced filtering and pagination
- [Mutations](../graphql/mutations.md) - Bulk operations and nested relationships
- [Permissions](../security/permissions.md) - RBAC and field permissions
- [Webhooks](../extensions/webhooks.md) - External notifications

---

## Complete Code

The complete code for this tutorial is available in `apps/store/` after creation with `python manage.py startapp store`.

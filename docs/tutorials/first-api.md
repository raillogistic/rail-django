# Building Your First API

This tutorial will guide you through building a complete e-commerce API from scratch using Rail Django. By the end, you'll have a fully functional GraphQL API with products, categories, orders, and customers.

## Prerequisites

- Rail Django project created with `rail-admin startproject`
- Basic familiarity with Django models
- A text editor or IDE

## What We'll Build

A simple e-commerce API with:

- **Products** - Items for sale
- **Categories** - Product categorization
- **Customers** - User accounts
- **Orders** - Purchase records
- **Order Items** - Line items in orders

## Step 1: Create the Store App

If you used `rail-admin startproject`, you already have a `store` app. Otherwise, create one:

```bash
python manage.py startapp store apps/store
```

## Step 2: Define Your Models

Edit `apps/store/models.py` to define your data structure.

```python
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Category(models.Model):
    """Product category for organization."""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "categories"

class Product(models.Model):
    """Product available for purchase."""
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=50, unique=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='products'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

## Step 3: Run Migrations

```bash
python manage.py makemigrations store
python manage.py migrate
```

## Step 4: Explore Your API

Start the server:

```bash
python manage.py runserver
```

Open `http://localhost:8000/graphql/graphiql` to access GraphiQL. Rail Django has automatically generated your GraphQL schema.

### List Categories

```graphql
query {
  categories {
    id
    name
    slug
  }
}
```

### Create a Category

```graphql
mutation {
  createCategory(
    input: {
      name: "Electronics"
      slug: "electronics"
      description: "Gadgets and more"
    }
  ) {
    ok
    category {
      id
      name
    }
  }
}
```

## Step 5: Advanced Customization

Use `GraphQLMeta` on your models to customize filtering, sorting, and field exposure.

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    # ... fields ...

    class GraphQLMeta(GraphQLMetaConfig):
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={"price": ["gt", "lt", "between"]}
        )
        ordering = ["name", "price", "-created_at"]
```

## Summary

You've built a complete e-commerce API with:

- ✅ **Auto-generated schema** from Django models.
- ✅ **Type-safe queries** and mutations.
- ✅ **Advanced filtering** and ordering out of the box.

## Next Steps

- [Authentication Tutorial](./authentication.md) - Secure your API.
- [Permissions Tutorial](./permissions.md) - Define granular access control.
- [Queries Deep Dive](./queries.md) - Master complex query patterns.

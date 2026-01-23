# Building Your First API

This tutorial will guide you through building a complete e-commerce API from scratch. By the end, you'll have a fully functional GraphQL API with products, categories, orders, and customers.

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

---

## Step 1: Create the Store App

If you used `rail-admin startproject`, you already have a `store` app. Otherwise, create one:

```bash
python manage.py startapp store apps/store
```

## Step 2: Define Your Models

Edit `apps/store/models.py`:

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

    def __str__(self):
        return self.name


class Product(models.Model):
    """Product available for purchase."""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    sku = models.CharField(max_length=50, unique=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='products'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def in_stock(self):
        return self.stock_quantity > 0


class Customer(models.Model):
    """Customer account linked to user."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile'
    )
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


class Order(models.Model):
    """Customer order."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    reference = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.reference

    def calculate_total(self):
        """Recalculate order total from items."""
        self.total_amount = sum(
            item.quantity * item.unit_price
            for item in self.items.all()
        )
        self.save()


class OrderItem(models.Model):
    """Line item in an order."""
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='order_items'
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price
```

## Step 3: Create and Apply Migrations

```bash
python manage.py makemigrations store
python manage.py migrate
```

## Step 4: Start the Server

```bash
python manage.py runserver
```

Open http://localhost:8000/graphql/ to access GraphiQL.

---

## Step 5: Explore Your API

Rail Django has automatically generated your GraphQL schema. Let's explore it!

### List Categories

```graphql
query {
  categories {
    id
    name
    slug
    description
  }
}
```

### Get Single Product

```graphql
query {
  product(id: "1") {
    id
    name
    price
    status
    category {
      name
    }
  }
}
```

### Create a Category

```graphql
mutation {
  createCategory(input: {
    name: "Electronics"
    slug: "electronics"
    description: "Electronic devices and accessories"
  }) {
    ok
    category {
      id
      name
      slug
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
  createProduct(input: {
    name: "Wireless Headphones"
    slug: "wireless-headphones"
    price: 79.99
    sku: "WH-001"
    stockQuantity: 100
    categoryId: "1"
    status: "active"
  }) {
    ok
    product {
      id
      name
      price
      category {
        name
      }
    }
    errors {
      field
      message
    }
  }
}
```

### Update a Product

```graphql
mutation {
  updateProduct(id: "1", input: {
    price: 69.99
    featured: true
  }) {
    ok
    product {
      id
      price
      featured
    }
  }
}
```

### Delete a Product

```graphql
mutation {
  deleteProduct(id: "1") {
    ok
    errors {
      message
    }
  }
}
```

---

## Step 6: Add Filtering

Query products with filters:

```graphql
query {
  products(
    where: {
      status: { eq: "active" }
      price: { gte: 50, lte: 200 }
      category: { name: { icontains: "electronics" } }
    }
  ) {
    id
    name
    price
    status
  }
}
```

### Quick Search

Search across multiple text fields:

```graphql
query {
  products(
    where: {
      OR: [
        { name: { icontains: "wireless" } }
        { description: { icontains: "wireless" } }
        { sku: { icontains: "WH" } }
      ]
    }
  ) {
    id
    name
    sku
  }
}
```

---

## Step 7: Add Ordering

Sort results:

```graphql
query {
  products(
    orderBy: ["-price", "name"]
  ) {
    id
    name
    price
  }
}
```

Options:
- `"price"` - Ascending (low to high)
- `"-price"` - Descending (high to low)
- `"category__name"` - Order by related field

---

## Step 8: Add Pagination

Paginate results:

```graphql
query {
  products(
    where: { status: { eq: "active" } }
    limit: 10
    offset: 0
  ) {
    id
    name
    price
  }
}
```

Or use page-based pagination:

```graphql
query {
  productsPaginated(
    where: { status: { eq: "active" } }
    page: 1
    pageSize: 10
  ) {
    items {
      id
      name
      price
    }
    pagination {
      totalCount
      totalPages
      currentPage
      hasNextPage
      hasPreviousPage
    }
  }
}
```

---

## Step 9: Create Orders with Nested Items

Create an order with items in a single mutation:

```graphql
mutation {
  createOrder(input: {
    reference: "ORD-2024-001"
    customerId: "1"
    status: "pending"
    notes: "Please gift wrap"
    items: {
      create: [
        {
          productId: "1"
          quantity: 2
          unitPrice: 79.99
        }
        {
          productId: "2"
          quantity: 1
          unitPrice: 149.99
        }
      ]
    }
  }) {
    ok
    order {
      id
      reference
      status
      items {
        id
        product {
          name
        }
        quantity
        unitPrice
        lineTotal
      }
      totalAmount
    }
  }
}
```

---

## Step 10: Add GraphQL Meta Configuration

Customize your API by adding `GraphQLMeta` to your models.

Edit `apps/store/models.py`:

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    # ... existing fields ...

    class GraphQLMeta(GraphQLMetaConfig):
        # Hide cost_price from API (internal only)
        fields = GraphQLMetaConfig.Fields(
            exclude=["cost_price"],
            read_only=["created_at", "updated_at", "sku"]
        )

        # Configure filtering
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku", "description"],
            fields={
                "status": GraphQLMetaConfig.FilterField(
                    lookups=["eq", "in"]
                ),
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["gt", "gte", "lt", "lte", "between"]
                ),
                "category": GraphQLMetaConfig.FilterField(
                    lookups=["eq"],
                    nested=True
                )
            }
        )

        # Configure ordering
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at", "stock_quantity"],
            default=["-created_at"]
        )
```

Restart your server to see the changes.

---

## Step 11: Add Seed Data

Create sample data for testing.

Create `apps/store/management/commands/seed_store.py`:

```python
from django.core.management.base import BaseCommand
from apps.store.models import Category, Product


class Command(BaseCommand):
    help = 'Seeds the database with sample store data'

    def handle(self, *args, **options):
        # Create categories
        electronics = Category.objects.create(
            name="Electronics",
            slug="electronics",
            description="Electronic devices and accessories"
        )

        accessories = Category.objects.create(
            name="Accessories",
            slug="accessories",
            description="Phone and computer accessories"
        )

        # Create products
        products = [
            Product(
                name="Wireless Headphones",
                slug="wireless-headphones",
                description="Premium over-ear wireless headphones",
                price=79.99,
                sku="WH-001",
                stock_quantity=100,
                category=electronics,
                status="active",
                featured=True
            ),
            Product(
                name="Bluetooth Speaker",
                slug="bluetooth-speaker",
                description="Portable waterproof speaker",
                price=49.99,
                sku="BS-001",
                stock_quantity=50,
                category=electronics,
                status="active"
            ),
            Product(
                name="Phone Case",
                slug="phone-case",
                description="Protective silicone case",
                price=19.99,
                sku="PC-001",
                stock_quantity=200,
                category=accessories,
                status="active"
            ),
        ]

        Product.objects.bulk_create(products)

        self.stdout.write(
            self.style.SUCCESS(f'Created {len(products)} products')
        )
```

Run the seed command:

```bash
python manage.py seed_store
```

---

## Summary

You've built a complete e-commerce API with:

✅ **Models** - Products, Categories, Orders, Customers
✅ **Queries** - List and retrieve with filtering, ordering, pagination
✅ **Mutations** - Create, update, delete operations
✅ **Nested Operations** - Create orders with items in one mutation
✅ **Configuration** - GraphQLMeta for customization

---

## Next Steps

- [Authentication Tutorial](./authentication.md) - Secure your API
- [Permissions Tutorial](./permissions.md) - Role-based access control
- [Queries Deep Dive](./queries.md) - Advanced filtering techniques
- [Mutations Deep Dive](./mutations.md) - Complex mutation patterns

---

## Complete Code

The complete code for this tutorial is available in the `examples/` directory.

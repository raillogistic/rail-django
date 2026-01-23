from django.contrib.auth import get_user_model
from django.db import models

from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "categories"


class Tag(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "tags"


class Post(models.Model):
    title = models.CharField(max_length=200)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="posts"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="posts")

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "posts"


class Client(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "clients"


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "comments"


class Product(models.Model):
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_creation = models.DateTimeField(auto_now_add=True)
    inventory_count = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="products", null=True, blank=True
    )

    class GraphQLMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(read_only=["date_creation"])
        filter_presets = {
            "expensive": {"price": {"gte": 50.0}},
            "cheap": {"price": {"lt": 50.0}},
            "mid_range": {"price": {"between": [20.0, 80.0]}},
            "complex_preset": {
                "AND": [
                     {"name": {"icontains": "pro"}},
                     {"price": {"gte": 100.0}}
                ]
            },
            "out_of_stock": {"inventory_count": {"eq": 0}},
        }

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "products"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True)

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "profiles"


class OrderItem(models.Model):
    """Order item for testing reverse relation count fields."""
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="order_items"
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "order items"

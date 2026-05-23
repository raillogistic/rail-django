from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models

from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta

User = get_user_model()


class ImportChoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


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
    attachments = GenericRelation(
        "test_app.Attachment",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="post",
    )

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
    name = models.CharField(max_length=120, help_text="Nom du produit")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_creation = models.DateTimeField(auto_now_add=True)
    inventory_count = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="products", null=True, blank=True
    )
    attachments = GenericRelation(
        "test_app.Attachment",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="product",
    )

    class GraphQLMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(read_only=["date_creation"])
        filtering = RailGraphQLMeta.Filtering(
            presets={
                "expensive": {"price": {"gte": 50.0}},
                "cheap": {"price": {"lt": 50.0}},
                "mid_range": {"price": {"between": [20.0, 80.0]}},
                "complex_preset": {
                    "AND": [
                        {"name": {"icontains": "pro"}},
                        {"price": {"gte": 100.0}},
                    ]
                },
                "out_of_stock": {"inventory_count": {"eq": 0}},
            }
        )

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


class Document(models.Model):
    title = models.CharField(max_length=120)
    attachment = models.FileField(upload_to="attachments/", blank=True, null=True)

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "documents"


class ImportChoiceSample(models.Model):
    name = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20,
        choices=ImportChoiceStatus.choices,
        default=ImportChoiceStatus.DRAFT,
    )

    class Meta:
        app_label = "test_app"
        verbose_name_plural = "import choice samples"


class Attachment(models.Model):
    """
    Generic attachment model linked to any model via GenericForeignKey.

    Attributes:
        name: Nom du fichier attaché.
        file_path: Chemin vers le fichier.
        content_type: Type de contenu lié (ContentType Django).
        object_id: Identifiant de l'objet lié.
        content_object: Référence générique vers l'objet parent.
    """

    name = models.CharField(max_length=200, verbose_name="Nom du fichier")
    file_path = models.CharField(
        max_length=500, blank=True, verbose_name="Chemin du fichier"
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Type de contenu",
    )
    object_id = models.PositiveIntegerField(verbose_name="ID de l'objet")
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        app_label = "test_app"
        verbose_name = "Pièce jointe"
        verbose_name_plural = "Pièces jointes"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return self.name

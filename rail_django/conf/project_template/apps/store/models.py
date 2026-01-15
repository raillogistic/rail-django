from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils import timezone

from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig
from rail_django.extensions.templating import model_pdf_template

from .access_control import STORE_ROLES, catalog_operations, order_operations

def _coerce_filter_value(args, kwargs):
    # Support both django-filter (qs, name, value) and GraphQLMeta (qs, value).
    if "value" in kwargs:
        return kwargs["value"]
    if not args:
        return None
    if len(args) == 1:
        return args[0]
    return args[1]


class CustomerStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    ARCHIVED = "archived", "Archived"


class OrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PLACED = "placed", "Placed"
    PAID = "paid", "Paid"
    FULFILLED = "fulfilled", "Fulfilled"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


class PaymentProvider(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    PAYPAL = "paypal", "PayPal"
    MANUAL = "manual", "Manual"


class PaymentStatus(models.TextChoices):
    AUTHORIZED = "authorized", "Authorized"
    CAPTURED = "captured", "Captured"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=60, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Customer(models.Model):
    external_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone_number = models.CharField(max_length=30, blank=True)
    status = models.CharField(
        max_length=20, choices=CustomerStatus.choices, default=CustomerStatus.ACTIVE
    )
    marketing_opt_in = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    class GraphqlMeta(GraphQLMetaConfig):
        classifications = GraphQLMetaConfig.Classification(
            model=["pii"],
            fields={
                "email": ["pii"],
                "phone_number": ["pii"],
                "notes": ["confidential"],
            },
        )


class Address(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(max_length=120)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=2, default="US")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "city", "postal_code"]

    def __str__(self) -> str:
        return f"{self.label} - {self.city}"


class Product(models.Model):
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    tags = models.ManyToManyField(Tag, related_name="products", blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    inventory_count = models.PositiveIntegerField(default=0)
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    internal_notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"

    class GraphQLMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            include=[
                "id",
                "sku",
                "name",
                "description",
                "category",
                "tags",
                "price",
                "currency",
                "inventory_count",
                "weight_grams",
                "is_active",
                "internal_notes",
                "metadata",
                "created_at",
                "updated_at",
            ],
            read_only=["sku", "created_at", "updated_at"],
            write_only=["internal_notes"],
        )
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku", "category__name"],
            quick_lookup="icontains",
            auto_detect_quick=False,
            fields={
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["gte", "lte", "range"],
                    help_text="Filter by list price.",
                ),
                "category__name": GraphQLMetaConfig.FilterField(
                    lookups=["icontains", "exact"],
                    help_text="Filter by category name.",
                ),
                "tags__name": GraphQLMetaConfig.FilterField(
                    lookups=["icontains"],
                    help_text="Filter by tag name.",
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["exact"], help_text="Filter active products."
                ),
            },
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at"],
            default=["-created_at"],
            allow_related=False,
        )
        access = GraphQLMetaConfig.AccessControl(
            roles=STORE_ROLES,
            operations=catalog_operations(allow_anonymous_read=True),
            fields=[
                GraphQLMetaConfig.FieldGuard(
                    field="price",
                    access="read",
                    visibility="visible",
                )
            ],
        )


class Order(models.Model):
    order_number = models.CharField(
        max_length=40, unique=True, default=uuid.uuid4, editable=False
    )
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="orders"
    )
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30, blank=True)
    shipping_address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipping_orders",
    )
    billing_address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_orders",
    )
    currency = models.CharField(max_length=3, default="USD")
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    placed_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    is_priority = models.BooleanField(default=False)
    risk_score = models.PositiveIntegerField(default=0)
    internal_notes = models.TextField(blank=True)
    payment_token = models.CharField(max_length=120, blank=True)
    fraud_context = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_orders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-placed_at"]
        permissions = [
            ("view_financials", "Can view order financials"),
            ("view_risk_score", "Can view order risk scores"),
            ("view_customer_pii", "Can view customer PII"),
        ]

    def __str__(self) -> str:
        return str(self.order_number)

    @property
    def balance_due(self) -> Decimal:
        return self.total_amount - self.paid_amount

    @model_pdf_template(content="pdf/order_invoice.html", title="Order invoice")
    def invoice_pdf(self, request=None):
        return {"order": self, "items": self.items.all()}

    @staticmethod
    def filter_overdue(queryset, *args, **kwargs):
        value = _coerce_filter_value(args, kwargs)
        if not value:
            return queryset
        cutoff = timezone.now() - timedelta(days=30)
        return queryset.filter(paid_at__isnull=True, placed_at__lte=cutoff)

    @staticmethod
    def filter_high_value(queryset, *args, **kwargs):
        value = _coerce_filter_value(args, kwargs)
        if value in (None, "", False):
            return queryset
        threshold = Decimal("1000.00") if value is True else Decimal(str(value))
        return queryset.filter(total_amount__gte=threshold)

    @staticmethod
    def filter_has_balance(queryset, *args, **kwargs):
        value = _coerce_filter_value(args, kwargs)
        if value is None:
            return queryset
        if value:
            return queryset.filter(total_amount__gt=F("paid_amount"))
        return queryset.filter(total_amount__lte=F("paid_amount"))

    @staticmethod
    def resolve_priority_queue(queryset, info, **kwargs):
        return queryset.filter(is_priority=True)

    @staticmethod
    def resolve_mark_paid(queryset, info, **kwargs):
        return queryset

    def resolve_balance_due(self, info):
        return self.balance_due

    @staticmethod
    def can_access_order(user, operation, info, instance, model):
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        if instance is None:
            return True
        return (
            getattr(instance, "created_by_id", None) == user.id
            or getattr(instance, "assigned_to_id", None) == user.id
        )

    @staticmethod
    def can_modify_order(user, operation, info, instance, model):
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        if instance is None:
            return False
        return getattr(instance, "assigned_to_id", None) == user.id

    @staticmethod
    def can_view_contact_email(context):
        user = getattr(context, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        instance = getattr(context, "instance", None)
        if instance is None:
            return False
        return (
            getattr(instance, "created_by_id", None) == user.id
            or getattr(instance, "assigned_to_id", None) == user.id
        )

    class GraphQLMeta(GraphQLMetaConfig):
        filtering = GraphQLMetaConfig.Filtering(
            quick=[
                "order_number",
                "contact_email",
                "customer__email",
                "shipping_address__city",
            ],
            quick_lookup="icontains",
            auto_detect_quick=False,
            fields={
                "status": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "in"],
                    choices=OrderStatus.choices,
                    help_text="Filter by order status.",
                ),
                "total_amount": GraphQLMetaConfig.FilterField(
                    lookups=["gte", "lte", "range"],
                    help_text="Filter by order totals.",
                ),
                "placed_at": GraphQLMetaConfig.FilterField(
                    lookups=["date", "gte", "lte", "range"],
                    help_text="Filter by placement date.",
                ),
                "customer__email": GraphQLMetaConfig.FilterField(
                    lookups=["icontains", "exact"],
                    help_text="Filter by customer email.",
                ),
                "shipping_address__city": GraphQLMetaConfig.FilterField(
                    lookups=["icontains", "exact"],
                    help_text="Filter by shipping city.",
                ),
            },
            custom={
                "overdue": "filter_overdue",
                "high_value": "filter_high_value",
                "has_balance": "filter_has_balance",
            },
        )
        fields = GraphQLMetaConfig.Fields(
            exclude=["raw_payload"],
            read_only=[
                "order_number",
                "subtotal_amount",
                "tax_amount",
                "shipping_amount",
                "discount_amount",
                "total_amount",
                "paid_amount",
                "placed_at",
                "paid_at",
                "fulfilled_at",
                "created_at",
                "updated_at",
            ],
            write_only=["fraud_context"],
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["placed_at", "total_amount", "status", "customer__last_name"],
            default=["-placed_at"],
            allow_related=True,
        )
        resolvers = GraphQLMetaConfig.Resolvers(
            queries={"priority_queue": "resolve_priority_queue"},
            mutations={"mark_paid": "resolve_mark_paid"},
            fields={"balance_due": "resolve_balance_due"},
        )
        access = GraphQLMetaConfig.AccessControl(
            roles=STORE_ROLES,
            operations=order_operations(),
            fields=[
                GraphQLMetaConfig.FieldGuard(
                    field="payment_token",
                    access="read",
                    visibility="visible",
                    roles=["order_admin"],
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="payment_token",
                    access="read",
                    visibility="masked",
                    mask_value="tok_****",
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="internal_notes",
                    access="read",
                    visibility="visible",
                    roles=["order_manager", "order_admin"],
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="internal_notes",
                    access="read",
                    visibility="hidden",
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="contact_email",
                    access="read",
                    visibility="visible",
                    condition="can_view_contact_email",
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="contact_email",
                    access="read",
                    visibility="redacted",
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="risk_score",
                    access="read",
                    visibility="visible",
                    permissions=["store.view_risk_score"],
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="risk_score",
                    access="read",
                    visibility="hidden",
                ),
            ],
        )
        classifications = GraphQLMetaConfig.Classification(
            model=["transactional", "financial"],
            fields={
                "contact_email": ["pii"],
                "payment_token": ["secret", "pci"],
                "internal_notes": ["confidential"],
                "risk_score": ["risk"],
                "total_amount": ["financial"],
            },
        )


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="order_items"
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order_id"]

    def __str__(self) -> str:
        return f"{self.order} - {self.product}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class Payment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    provider = models.CharField(
        max_length=20, choices=PaymentProvider.choices, default=PaymentProvider.STRIPE
    )
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.AUTHORIZED
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    captured_at = models.DateTimeField(null=True, blank=True)
    external_reference = models.CharField(max_length=120, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order} - {self.provider}"

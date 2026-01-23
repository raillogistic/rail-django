from django.contrib import admin

from .models import (
    Address,
    Category,
    Customer,
    Order,
    OrderItem,
    Payment,
    Product,
    Tag,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "price", "is_active")
    search_fields = ("sku", "name")
    list_filter = ("is_active", "category")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "status", "created_at")
    search_fields = ("email", "first_name", "last_name")
    list_filter = ("status", "marketing_opt_in")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("label", "customer", "city", "country", "is_primary")
    search_fields = ("label", "city", "country", "postal_code")
    list_filter = ("country", "is_primary")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "status",
        "customer",
        "total_amount",
        "placed_at",
    )
    search_fields = ("order_number", "contact_email", "customer__email")
    list_filter = ("status", "currency", "is_priority")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "unit_price")
    search_fields = ("order__order_number", "product__name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "provider", "status", "amount", "captured_at")
    search_fields = ("order__order_number", "external_reference")
    list_filter = ("provider", "status")

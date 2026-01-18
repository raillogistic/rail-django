from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ...models import (
    Address,
    Category,
    Customer,
    CustomerStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    Product,
    Tag,
)

CATEGORY_SEEDS = (
    ("coffee", "Coffee"),
    ("tea", "Tea"),
    ("equipment", "Equipment"),
    ("accessories", "Accessories"),
    ("subscriptions", "Subscriptions"),
)

TAG_SEEDS = (
    "best-seller",
    "new-arrival",
    "limited",
    "staff-pick",
    "gift",
    "bundle",
)

PRODUCT_SEEDS = (
    ("BEAN-ESP-01", "Espresso Blend 1lb", "coffee"),
    ("BEAN-HSE-01", "House Blend 1lb", "coffee"),
    ("BEAN-DEC-01", "Decaf Blend 1lb", "coffee"),
    ("TEA-EB-01", "Earl Grey 20ct", "tea"),
    ("TEA-GRN-01", "Jasmine Green 20ct", "tea"),
    ("EQP-GRIND-01", "Burr Grinder", "equipment"),
    ("EQP-DRIP-01", "Pour-Over Kit", "equipment"),
    ("ACC-MUG-01", "Stoneware Mug", "accessories"),
    ("ACC-SCOOP-01", "Coffee Scoop", "accessories"),
    ("SUB-COF-01", "Monthly Coffee Subscription", "subscriptions"),
)

FIRST_NAMES = (
    "Avery",
    "Jordan",
    "Riley",
    "Morgan",
    "Casey",
    "Harper",
    "Quinn",
    "Skyler",
    "Rowan",
    "Emerson",
    "Reese",
    "Parker",
)

LAST_NAMES = (
    "Wright",
    "Patel",
    "Chen",
    "Davis",
    "Nguyen",
    "Lopez",
    "Johnson",
    "Kim",
    "Singh",
    "Garcia",
    "Miller",
    "Brown",
)


class Command(BaseCommand):
    help = "Populate the store app with sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--customers",
            type=int,
            default=12,
            help="Number of customers to create.",
        )
        parser.add_argument(
            "--orders-per-customer",
            type=int,
            default=2,
            help="How many orders to create for each customer.",
        )
        parser.add_argument(
            "--products",
            type=int,
            default=len(PRODUCT_SEEDS),
            help="Number of products to create.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed for reproducible data.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing store data before seeding.",
        )

    def handle(self, *args, **options):
        rng = random.Random(options["seed"])

        with transaction.atomic():
            if options["clear"]:
                self._clear_store_data()

            categories = self._seed_categories()
            tags = self._seed_tags()
            products = self._seed_products(options["products"], categories, tags, rng)
            customers = self._seed_customers(options["customers"], rng)
            self._seed_addresses(customers)
            self._seed_orders(
                customers, products, options["orders_per_customer"], rng
            )

        self.stdout.write(self.style.SUCCESS("Store sample data created."))

    def _clear_store_data(self):
        Payment.objects.all().delete()
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        Address.objects.all().delete()
        Customer.objects.all().delete()
        Product.objects.all().delete()
        Tag.objects.all().delete()
        Category.objects.all().delete()

    def _seed_categories(self):
        categories = {}
        for slug, name in CATEGORY_SEEDS:
            category, _ = Category.objects.update_or_create(
                slug=slug, defaults={"name": name, "is_active": True}
            )
            categories[slug] = category
        return categories

    def _seed_tags(self):
        tags = []
        for tag_name in TAG_SEEDS:
            tag, _ = Tag.objects.update_or_create(name=tag_name)
            tags.append(tag)
        return tags

    def _seed_products(self, count, categories, tags, rng):
        products = []
        for index in range(count):
            if index < len(PRODUCT_SEEDS):
                sku, name, category_key = PRODUCT_SEEDS[index]
            else:
                sku = f"GEN-{index + 1:03d}"
                name = f"Seasonal Item {index + 1}"
                category_key = rng.choice(list(categories.keys()))

            price = Decimal(rng.randint(12, 120)) + Decimal("0.99")
            cost_price = (price * Decimal("0.55")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            product, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "description": f"{name} crafted for the store demo.",
                    "category": categories[category_key],
                    "price": price,
                    "cost_price": cost_price,
                    "inventory_count": rng.randint(5, 120),
                    "weight_grams": rng.choice([250, 340, 500, 750, None]),
                    "is_active": True,
                    "metadata": {"season": "core", "seeded": True},
                },
            )

            product.tags.set(rng.sample(tags, rng.randint(1, min(3, len(tags)))))
            products.append(product)

        return products

    def _seed_customers(self, count, rng):
        customers = []
        for index in range(count):
            first = FIRST_NAMES[index % len(FIRST_NAMES)]
            last = LAST_NAMES[index % len(LAST_NAMES)]
            email = f"{first.lower()}.{last.lower()}{index}@example.com"
            status = rng.choice([CustomerStatus.ACTIVE, CustomerStatus.SUSPENDED])
            customer, _ = Customer.objects.update_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "phone_number": f"+1-555-01{index:02d}",
                    "status": status,
                    "marketing_opt_in": rng.choice([True, False]),
                    "notes": "Seeded customer record.",
                },
            )
            customers.append(customer)
        return customers

    def _seed_addresses(self, customers):
        for index, customer in enumerate(customers):
            Address.objects.update_or_create(
                customer=customer,
                label="Home",
                defaults={
                    "line1": f"{100 + index} Market Street",
                    "line2": "",
                    "city": "Springfield",
                    "state": "CA",
                    "postal_code": f"90{index:03d}",
                    "country": "US",
                    "is_primary": True,
                },
            )
            Address.objects.update_or_create(
                customer=customer,
                label="Office",
                defaults={
                    "line1": f"{200 + index} Mission Ave",
                    "line2": "Suite 5",
                    "city": "Springfield",
                    "state": "CA",
                    "postal_code": f"91{index:03d}",
                    "country": "US",
                    "is_primary": False,
                },
            )

    def _seed_orders(self, customers, products, orders_per_customer, rng):
        status_options = [
            OrderStatus.PLACED,
            OrderStatus.PAID,
            OrderStatus.FULFILLED,
            OrderStatus.CANCELLED,
        ]
        for customer in customers:
            addresses = list(customer.addresses.all())
            shipping_address = next((addr for addr in addresses if addr.is_primary), None)
            billing_address = shipping_address or (addresses[0] if addresses else None)

            for index in range(orders_per_customer):
                order_number = f"SEED-{customer.pk}-{index + 1}"
                status = rng.choice(status_options)
                created_at = timezone.now() - timedelta(days=rng.randint(0, 25))

                order, _ = Order.objects.update_or_create(
                    order_number=order_number,
                    defaults={
                        "status": status,
                        "customer": customer,
                        "contact_email": customer.email,
                        "contact_phone": customer.phone_number,
                        "shipping_address": shipping_address,
                        "billing_address": billing_address,
                        "subtotal_amount": Decimal("0.00"),
                        "tax_amount": Decimal("0.00"),
                        "shipping_amount": Decimal("0.00"),
                        "discount_amount": Decimal("0.00"),
                        "total_amount": Decimal("0.00"),
                        "paid_amount": Decimal("0.00"),
                        "placed_at": created_at,
                        "is_priority": rng.choice([True, False, False]),
                        "risk_score": rng.randint(0, 100),
                        "internal_notes": "Seeded order.",
                        "metadata": {"seeded": True},
                    },
                )

                OrderItem.objects.filter(order=order).delete()
                Payment.objects.filter(order=order).delete()

                item_count = rng.randint(1, 4)
                chosen_products = rng.sample(products, item_count)
                subtotal = Decimal("0.00")
                for product in chosen_products:
                    quantity = rng.randint(1, 3)
                    line_total = product.price * quantity
                    subtotal += line_total
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=quantity,
                        unit_price=product.price,
                    )

                subtotal = subtotal.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                tax = (subtotal * Decimal("0.0825")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                shipping = Decimal("0.00") if subtotal >= 100 else Decimal("9.95")
                discount = Decimal("10.00") if subtotal >= 200 else Decimal("0.00")
                total = (subtotal + tax + shipping - discount).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

                paid_amount = (
                    total
                    if status in (OrderStatus.PAID, OrderStatus.FULFILLED)
                    else Decimal("0.00")
                )
                paid_at = (
                    created_at + timedelta(days=rng.randint(0, 3))
                    if paid_amount > 0
                    else None
                )
                fulfilled_at = (
                    paid_at + timedelta(days=rng.randint(1, 3))
                    if status == OrderStatus.FULFILLED
                    else None
                )

                Order.objects.filter(pk=order.pk).update(
                    subtotal_amount=subtotal,
                    tax_amount=tax,
                    shipping_amount=shipping,
                    discount_amount=discount,
                    total_amount=total,
                    paid_amount=paid_amount,
                    paid_at=paid_at,
                    fulfilled_at=fulfilled_at,
                )

                if status in (OrderStatus.PAID, OrderStatus.FULFILLED):
                    Payment.objects.create(
                        order=order,
                        provider=rng.choice(list(PaymentProvider.values)),
                        status=PaymentStatus.CAPTURED,
                        amount=total,
                        captured_at=paid_at,
                        external_reference=f"PMT-{order_number}",
                        raw_response={"seeded": True},
                    )
                elif status == OrderStatus.PLACED:
                    Payment.objects.create(
                        order=order,
                        provider=rng.choice(list(PaymentProvider.values)),
                        status=PaymentStatus.AUTHORIZED,
                        amount=total,
                        external_reference=f"AUTH-{order_number}",
                        raw_response={"seeded": True},
                    )

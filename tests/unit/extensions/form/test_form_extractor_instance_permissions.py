from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from rail_django.extensions.form.extractors.base import FormConfigExtractor
from rail_django.security.field_permissions import FieldVisibility, field_permission_manager
from test_app.models import Category, Product

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_form_extractor_passes_instance_to_field_permission_checks(monkeypatch):
    category = Category.objects.create(name="Hardware", description="")
    product = Product.objects.create(name="Widget", price=10, category=category)
    user = get_user_model().objects.create_superuser(
        username="instance_perm_admin",
        email="instance_perm_admin@example.com",
        password="pass12345",
    )

    calls: list[tuple[str, str | None]] = []

    def _fake_check_field_permission(target_user, model, field_name, instance=None):
        calls.append((str(field_name), str(getattr(instance, "pk", None)) if instance else None))
        return SimpleNamespace(
            visibility=FieldVisibility.VISIBLE,
            can_write=True,
        )

    monkeypatch.setattr(
        field_permission_manager,
        "check_field_permission",
        _fake_check_field_permission,
        raising=False,
    )

    extractor = FormConfigExtractor(schema_name="default")
    extractor.extract(
        "test_app",
        "Product",
        user=user,
        object_id=str(product.pk),
        mode="UPDATE",
    )

    assert any(field_name == "name" and instance_pk == str(product.pk) for field_name, instance_pk in calls)
    assert any(field_name == "category" and instance_pk == str(product.pk) for field_name, instance_pk in calls)

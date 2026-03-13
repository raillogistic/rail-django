from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from rail_django.extensions.form.extractors.base import FormConfigExtractor
from rail_django.security.field_permissions import FieldAccessLevel, field_permission_manager
from test_app.models import Category, Product

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_form_extractor_passes_create_mode_to_field_permission_checks(monkeypatch):
    category = Category.objects.create(name="Hardware", description="")
    user = get_user_model().objects.create_superuser(
        username="create_mode_perm_admin",
        email="create_mode_perm_admin@example.com",
        password="pass12345",
    )

    operation_types: list[str] = []
    original = field_permission_manager.check_field_permission

    def _wrapped_check_field_permission(
        target_user,
        model,
        field_name,
        *,
        instance=None,
        operation_type="update",
        request_context=None,
        parent_instance=None,
    ):
        operation_types.append(str(operation_type))
        return original(
            target_user,
            model,
            field_name,
            instance=instance,
            operation_type=operation_type,
            request_context=request_context,
            parent_instance=parent_instance,
        )

    monkeypatch.setattr(
        field_permission_manager,
        "check_field_permission",
        _wrapped_check_field_permission,
    )

    extractor = FormConfigExtractor(schema_name="default")
    extractor.extract(
        "test_app",
        "Product",
        user=user,
        mode="CREATE",
    )

    assert "create" in operation_types


@pytest.mark.parametrize(
    ("operation_type", "permission_name"),
    [
        ("create", "test_app.add_product"),
        ("update", "test_app.change_product"),
        ("delete", "test_app.delete_product"),
        ("view", "test_app.view_product"),
    ],
)
def test_field_permission_manager_uses_rbac_and_operation_specific_codenames(
    monkeypatch,
    operation_type,
    permission_name,
):
    user = get_user_model().objects.create_user(
        username=f"rbac_{operation_type}_user",
        email=f"rbac_{operation_type}_user@example.com",
        password="pass12345",
    )

    role_calls: list[tuple[str, str]] = []

    def _fake_has_permission(target_user, permission, permission_context):
        role_calls.append((permission, str(getattr(permission_context, "operation", ""))))
        return permission == permission_name

    monkeypatch.setattr(
        "rail_django.security.rbac.role_manager.has_permission",
        _fake_has_permission,
    )
    monkeypatch.setattr(user, "has_perm", lambda _perm: False)

    context = SimpleNamespace(
        user=user,
        field_name="name",
        model_class=Product,
        instance=None,
        operation_type=operation_type,
        request_context=None,
        parent_instance=None,
    )

    manager = field_permission_manager
    access_level = manager.get_field_access_level(context)

    expected = (
        FieldAccessLevel.READ if operation_type == "view" else FieldAccessLevel.WRITE
    )
    assert access_level == expected
    assert role_calls
    assert role_calls[0][0] == permission_name
    assert role_calls[0][1] == operation_type

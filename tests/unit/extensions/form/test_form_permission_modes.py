from types import SimpleNamespace

import pytest

from rail_django.extensions.form.extractors.base import FormConfigExtractor
from rail_django.security.field_permissions import (
    FieldAccessLevel,
    FieldContext,
    FieldVisibility,
    field_permission_manager,
)
from test_app.models import Product

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_form_extractor_passes_create_mode_to_field_permission_checks(monkeypatch):
    user = SimpleNamespace(is_authenticated=True, pk=1, is_superuser=False)

    operation_types: list[str] = []

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
        return SimpleNamespace(
            visibility=FieldVisibility.VISIBLE,
            can_write=True,
        )

    monkeypatch.setattr(
        field_permission_manager,
        "check_field_permission",
        _wrapped_check_field_permission,
    )
    monkeypatch.setattr(
        "rail_django.extensions.form.extractors.base.apps.get_model",
        lambda app_name, model_name: Product,
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
    user = SimpleNamespace(
        is_authenticated=True,
        pk=1,
        is_superuser=False,
        has_perm=lambda _perm: False,
    )

    role_calls: list[tuple[str, str]] = []

    def _fake_has_permission(target_user, permission, permission_context):
        role_calls.append((permission, str(getattr(permission_context, "operation", ""))))
        return permission == permission_name

    monkeypatch.setattr(
        "rail_django.security.rbac.role_manager.has_permission",
        _fake_has_permission,
    )

    context = FieldContext(
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

"""
Unit tests for field-level permissions and masking helpers.
"""

from types import SimpleNamespace
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from graphql import GraphQLError

from rail_django.security.field_permissions import (
    FieldAccessLevel,
    FieldContext,
    FieldPermissionManager,
    FieldPermissionRule,
    FieldVisibility,
    apply_restricted_field_defaults,
    field_permission_required,
    field_permission_manager,
    has_restricted_field_default,
    mask_sensitive_fields,
    resolve_restricted_field_default,
)
from test_app.models import Category, Product

pytestmark = pytest.mark.unit


class _InfoStub:
    def __init__(self, user):
        self.context = SimpleNamespace(user=user)


@pytest.mark.django_db
def test_mask_sensitive_fields_hides_password_and_masks_token():
    user = User.objects.create_user(username="mask_user", password="pass12345")
    data = {
        "password": "secret",
        "api_token": "abc123",
        "name": "Alpha",
    }

    masked = mask_sensitive_fields(data, user, Category)
    assert "password" not in masked
    assert masked["api_token"] == "***HIDDEN***"
    assert masked["name"] == "Alpha"


@pytest.mark.django_db
def test_field_permission_required_blocks_write_access():
    user = User.objects.create_user(username="field_user", password="pass12345")
    info = _InfoStub(user)

    @field_permission_required("name", access_level=FieldAccessLevel.WRITE, model_class=Category)
    def _secured(_, info):
        return "ok"

    with pytest.raises(GraphQLError):
        _secured(None, info)


@pytest.mark.django_db
def test_filter_fields_for_user_skips_hidden_password_field():
    user = User.objects.create_user(username="filter_user", password="pass12345")
    fields = field_permission_manager.filter_fields_for_user(
        user, get_user_model()
    )

    assert "password" not in fields
    assert "username" in fields


@pytest.mark.django_db
def test_wildcard_field_rule_applies_for_non_sensitive_fields():
    user = User.objects.create_user(username="wildcard_user", password="pass12345")
    manager = FieldPermissionManager()
    manager.register_field_rule(
        FieldPermissionRule(
            field_name="*internal*",
            model_name="*",
            access_level=FieldAccessLevel.READ,
            visibility=FieldVisibility.MASKED,
            mask_value="***MASKED***",
        )
    )

    context = FieldContext(
        user=user,
        field_name="internal_reference",
        model_class=Category,
    )
    visibility, mask_value = manager.get_field_visibility(context)

    assert visibility == FieldVisibility.MASKED
    assert mask_value == "***MASKED***"


@pytest.mark.django_db
def test_global_field_rule_controls_visibility():
    user = User.objects.create_user(username="global_rule_user", password="pass12345")
    manager = FieldPermissionManager()
    manager.register_global_rule(
        FieldPermissionRule(
            field_name="public_notes",
            model_name="*",
            access_level=FieldAccessLevel.READ,
            visibility=FieldVisibility.HIDDEN,
        )
    )

    context = FieldContext(
        user=user,
        field_name="public_notes",
        model_class=Category,
    )
    visibility, mask_value = manager.get_field_visibility(context)

    assert visibility == FieldVisibility.HIDDEN
    assert mask_value is None


@pytest.mark.django_db
def test_financial_fields_mask_for_non_privileged_users():
    user = User.objects.create_user(username="finance_user", password="pass12345")
    manager = FieldPermissionManager()
    context = FieldContext(
        user=user,
        field_name="salary",
        model_class=Category,
    )
    visibility, mask_value = manager.get_field_visibility(context)

    assert visibility == FieldVisibility.MASKED
    assert mask_value == "***CONFIDENTIAL***"


@pytest.mark.django_db
def test_mask_sensitive_fields_uses_null_for_decimal_fields():
    user = User.objects.create_user(username="finance_mask_user", password="pass12345")
    data = {
        "price": Decimal("10.50"),
        "name": "Maskable Product",
    }

    masked = mask_sensitive_fields(data, user, Product)

    assert masked["price"] == Decimal("0")
    assert masked["name"] == "Maskable Product"


def test_restricted_field_default_resolution_for_price():
    value = resolve_restricted_field_default(Product, "price")
    assert value == Decimal("0")
    assert has_restricted_field_default(Product, "price") is True


def test_apply_restricted_field_defaults_injects_missing_price():
    payload = {"name": "Fallback Product"}
    updated = apply_restricted_field_defaults(payload, Product)

    assert "price" not in payload
    assert updated["price"] == Decimal("0")
    assert updated["name"] == "Fallback Product"


@pytest.mark.django_db
def test_check_field_permission_returns_compatibility_result():
    user = User.objects.create_user(username="compat_user", password="pass12345")
    manager = FieldPermissionManager()

    permission = manager.check_field_permission(user, Category, "name")

    assert permission.visibility == FieldVisibility.VISIBLE
    assert permission.can_read is True
    assert permission.can_write is False


def test_check_field_permission_fails_closed_without_user():
    manager = FieldPermissionManager()

    permission = manager.check_field_permission(None, Category, "name")

    assert permission.visibility == FieldVisibility.HIDDEN
    assert permission.can_read is False
    assert permission.can_write is False


@pytest.mark.django_db
def test_wildcard_rule_does_not_match_midstring_without_glob_alignment():
    user = User.objects.create_user(username="glob_user", password="pass12345")
    manager = FieldPermissionManager()
    manager.register_field_rule(
        FieldPermissionRule(
            field_name="name*",
            model_name="*",
            access_level=FieldAccessLevel.NONE,
            visibility=FieldVisibility.HIDDEN,
        )
    )

    unrelated_context = FieldContext(
        user=user,
        field_name="username",
        model_class=Category,
    )
    unrelated_visibility, _ = manager.get_field_visibility(unrelated_context)

    matching_context = FieldContext(
        user=user,
        field_name="name_value",
        model_class=Category,
    )
    matching_visibility, _ = manager.get_field_visibility(matching_context)

    assert unrelated_visibility == FieldVisibility.VISIBLE
    assert matching_visibility == FieldVisibility.HIDDEN


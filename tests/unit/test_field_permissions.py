"""
Unit tests for field-level permissions and masking helpers.
"""

from types import SimpleNamespace

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
    field_permission_required,
    field_permission_manager,
    mask_sensitive_fields,
)
from test_app.models import Category

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


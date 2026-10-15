import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings

from rail_django.extensions.auth.jwt import JWTManager

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_generate_token_includes_user_roles():
    user = get_user_model().objects.create_user(
        username="jwt_roles_user",
        password="pass12345",
    )
    group, _ = Group.objects.get_or_create(name="ops_manager")
    user.groups.add(group)

    token_data = JWTManager.generate_token(user, include_refresh=False)
    payload = JWTManager.verify_token(token_data["token"], expected_type="access")

    assert payload is not None
    assert token_data["roles"] == ["ops_manager"]
    assert payload["roles"] == ["ops_manager"]


@pytest.mark.parametrize("include_permissions", [True, False])
def test_permission_claim_setting_preserves_response_and_identity(include_permissions):
    """Compact tokens retain identity while responses keep the full permission list."""
    user = get_user_model().objects.create_user(username="jwt_compact_user")
    permissions = [f"purchasing.view_model_{index}" for index in range(600)]
    with override_settings(JWT_INCLUDE_PERMISSIONS=include_permissions), patch(
        "rail_django.extensions.auth.utils._get_effective_permissions",
        return_value=permissions,
    ):
        token_data = JWTManager.generate_token(user, include_refresh=False)
    payload = JWTManager.verify_token(token_data["token"], expected_type="access")

    assert payload["user_id"] == user.pk
    assert token_data["permissions"] == permissions
    if include_permissions:
        assert payload["permissions"] == permissions
    else:
        assert "permissions" not in payload
        assert len(token_data["token"]) < 4096

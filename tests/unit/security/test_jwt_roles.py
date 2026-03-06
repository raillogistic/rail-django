import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

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

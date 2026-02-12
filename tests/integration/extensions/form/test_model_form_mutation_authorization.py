from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from graphql import GraphQLError

from rail_django.extensions.form.utils.authorization import (
    ensure_generated_mutation_authorized,
)
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _make_info(user):
    return SimpleNamespace(context=SimpleNamespace(user=user))


def test_generated_mutation_authorization_for_create_update_nested_paths():
    User = get_user_model()
    limited_user = User.objects.create_user(
        username="generated_mutation_limited",
        password="pass12345",
    )
    superuser = User.objects.create_superuser(
        username="generated_mutation_admin",
        email="generated_mutation_admin@example.com",
        password="pass12345",
    )

    with pytest.raises(GraphQLError):
        ensure_generated_mutation_authorized(
            _make_info(limited_user),
            Product,
            operation="create",
        )

    ensure_generated_mutation_authorized(
        _make_info(superuser),
        Product,
        operation="create",
    )
    ensure_generated_mutation_authorized(
        _make_info(superuser),
        Product,
        operation="update",
    )

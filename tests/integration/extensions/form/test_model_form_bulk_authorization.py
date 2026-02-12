from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from graphql import GraphQLError

from rail_django.extensions.form.utils.authorization import (
    ensure_generated_mutation_authorized,
)
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _info(user):
    return SimpleNamespace(context=SimpleNamespace(user=user))


def test_bulk_mutation_paths_enforce_authorization():
    User = get_user_model()
    limited_user = User.objects.create_user(
        username="generated_bulk_limited",
        password="pass12345",
    )
    admin_user = User.objects.create_superuser(
        username="generated_bulk_admin",
        email="generated_bulk_admin@example.com",
        password="pass12345",
    )

    with pytest.raises(GraphQLError):
        ensure_generated_mutation_authorized(
            _info(limited_user), Product, operation="bulk_update"
        )

    ensure_generated_mutation_authorized(
        _info(admin_user), Product, operation="bulk_update"
    )

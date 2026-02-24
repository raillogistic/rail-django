from types import SimpleNamespace

import pytest

from rail_django.extensions.auth import utils as auth_utils


@pytest.mark.unit
def test_get_effective_permissions_returns_empty_for_anonymous():
    user = SimpleNamespace(is_authenticated=False, pk=None)
    assert auth_utils._get_effective_permissions(user) == []


@pytest.mark.unit
def test_get_effective_permissions_merges_rbac_and_django_permissions(monkeypatch):
    user = SimpleNamespace(
        is_authenticated=True,
        pk=7,
        get_all_permissions=lambda: {"orders.view_order", "orders.change_order"},
    )
    monkeypatch.setattr(
        auth_utils.role_manager,
        "get_effective_permissions",
        lambda _user: {"orders.view_order", "orders.delete_order"},
    )

    assert auth_utils._get_effective_permissions(user) == [
        "orders.change_order",
        "orders.delete_order",
        "orders.view_order",
    ]

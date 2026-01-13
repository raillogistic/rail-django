"""
Unit tests for permission checkers and query helpers.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied

from rail_django.extensions.permissions import (
    CustomPermissionChecker,
    DjangoPermissionChecker,
    OperationType,
    PermissionLevel,
    PermissionManager,
    PermissionQuery,
    PermissionResult,
    PermissionFilterMixin,
    require_permission,
)
from test_app.models import Category

pytestmark = pytest.mark.unit


class _InfoStub:
    def __init__(self, user):
        self.context = SimpleNamespace(user=user)


@pytest.mark.django_db
def test_django_permission_checker_allows_user_permission():
    user = User.objects.create_user(username="perm_user", password="pass12345")
    content_type = ContentType.objects.get_for_model(Category)
    perm = Permission.objects.get(codename="view_category", content_type=content_type)
    user.user_permissions.add(perm)

    checker = DjangoPermissionChecker("view", Category)
    result = checker.check_permission(user)
    assert result.allowed is True


@pytest.mark.django_db
def test_custom_permission_checker_handles_exception():
    def _explode(user, obj):
        raise RuntimeError("boom")

    checker = CustomPermissionChecker(_explode, description="test")
    result = checker.check_permission(User(username="tester"))
    assert result.allowed is False


def test_permission_manager_registers_and_checks():
    manager = PermissionManager()

    class _AllowChecker:
        def check_permission(self, user, obj=None, **kwargs):
            return PermissionResult(True, "ok")

    manager.register_operation_permission("test_app.category", OperationType.READ, _AllowChecker())
    result = manager.check_operation_permission(
        User(username="tester"), "test_app.category", OperationType.READ
    )
    assert result.allowed is True


@pytest.mark.django_db
def test_permission_filter_mixin_blocks_unauthenticated():
    Category.objects.create(name="alpha")
    queryset = Category.objects.all()
    filtered = PermissionFilterMixin.filter_queryset_by_permissions(
        queryset, AnonymousUser(), OperationType.READ
    )
    assert filtered.count() == 0


@pytest.mark.django_db
def test_require_permission_decorator_raises_when_denied():
    user = User.objects.create_user(username="perm_user2", password="pass12345")
    info = _InfoStub(user)

    @require_permission(DjangoPermissionChecker("view", Category), PermissionLevel.OPERATION)
    def _secured(_, info):
        return "ok"

    with pytest.raises(PermissionDenied):
        _secured(None, info)


@pytest.mark.django_db
def test_permission_query_returns_entries_for_model_name():
    user = User.objects.create_user(username="perm_user3", password="pass12345")
    info = _InfoStub(user)
    query = PermissionQuery()

    result = query.resolve_my_permissions(info, model_name="test_app.Category")
    assert len(result) == 1
    assert result[0].model_name == "test_app.category"


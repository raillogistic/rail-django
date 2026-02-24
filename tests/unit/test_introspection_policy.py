from types import SimpleNamespace

import pytest

from rail_django.core import security as security_module
from rail_django.core.security import is_introspection_allowed


def _user(
    *,
    authenticated: bool = True,
    staff: bool = False,
    superuser: bool = False,
    groups: list[str] | None = None,
):
    class _Groups:
        def values_list(self, *_args, **_kwargs):
            return list(groups or [])

    return SimpleNamespace(
        is_authenticated=authenticated,
        is_staff=staff,
        is_superuser=superuser,
        groups=_Groups(),
    )


@pytest.mark.unit
def test_introspection_enabled_allows_anonymous():
    assert is_introspection_allowed(None, "gql", enable_introspection=True) is True


@pytest.mark.unit
def test_introspection_disabled_denies_anonymous():
    assert is_introspection_allowed(None, "gql", enable_introspection=False) is False


@pytest.mark.unit
def test_introspection_disabled_requires_allowed_role(monkeypatch):
    monkeypatch.setattr(security_module, "get_introspection_roles", lambda _schema: ["admin"])
    monkeypatch.setattr(security_module.role_manager, "get_user_roles", lambda _user: [])

    assert (
        is_introspection_allowed(
            _user(authenticated=True, staff=False, groups=["viewer"]),
            "gql",
            enable_introspection=False,
        )
        is False
    )


@pytest.mark.unit
def test_introspection_disabled_allows_staff_when_admin_role_allowed(monkeypatch):
    monkeypatch.setattr(security_module, "get_introspection_roles", lambda _schema: ["admin"])
    monkeypatch.setattr(security_module.role_manager, "get_user_roles", lambda _user: [])

    assert (
        is_introspection_allowed(
            _user(authenticated=True, staff=True),
            "gql",
            enable_introspection=False,
        )
        is True
    )


@pytest.mark.unit
def test_introspection_disabled_allows_matching_rbac_role(monkeypatch):
    monkeypatch.setattr(security_module, "get_introspection_roles", lambda _schema: ["developer"])
    monkeypatch.setattr(
        security_module.role_manager,
        "get_user_roles",
        lambda _user: ["developer"],
    )

    assert (
        is_introspection_allowed(
            _user(authenticated=True, groups=[]),
            "gql",
            enable_introspection=False,
        )
        is True
    )

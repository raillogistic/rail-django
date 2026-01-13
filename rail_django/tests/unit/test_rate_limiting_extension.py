"""
Unit tests for rate limiting middleware.
"""

from types import SimpleNamespace

import pytest
from graphql import GraphQLError

from rail_django.extensions.rate_limiting import rate_limit_middleware

pytestmark = pytest.mark.unit


class _LimiterStub:
    def __init__(self, *, enabled=True, allow=True):
        self._enabled = enabled
        self._allow = allow
        self.checked = []

    def is_enabled(self, scope):
        return self._enabled

    def check(self, scope, request=None):
        self.checked.append(scope)
        return SimpleNamespace(allowed=self._allow)


def test_rate_limit_middleware_allows_when_disabled(monkeypatch):
    limiter = _LimiterStub(enabled=False)
    monkeypatch.setattr(
        "rail_django.extensions.rate_limiting.get_rate_limiter", lambda schema_name=None: limiter
    )

    info = SimpleNamespace(context=SimpleNamespace(schema_name="default"), field_name="posts", path=SimpleNamespace(prev=None))
    result = rate_limit_middleware(lambda *_: "ok", None, info)
    assert result == "ok"


def test_rate_limit_middleware_blocks_when_exceeded(monkeypatch):
    limiter = _LimiterStub(enabled=True, allow=False)
    monkeypatch.setattr(
        "rail_django.extensions.rate_limiting.get_rate_limiter", lambda schema_name=None: limiter
    )

    info = SimpleNamespace(context=SimpleNamespace(schema_name="default"), field_name="posts", path=SimpleNamespace(prev=None))
    with pytest.raises(GraphQLError):
        rate_limit_middleware(lambda *_: "ok", None, info)


def test_rate_limit_middleware_checks_login_scope(monkeypatch):
    limiter = _LimiterStub(enabled=True, allow=True)
    monkeypatch.setattr(
        "rail_django.extensions.rate_limiting.get_rate_limiter", lambda schema_name=None: limiter
    )

    info = SimpleNamespace(context=SimpleNamespace(schema_name="default"), field_name="login", path=SimpleNamespace(prev=None))
    result = rate_limit_middleware(lambda *_: "ok", None, info)
    assert result == "ok"
    assert "graphql_login" in limiter.checked


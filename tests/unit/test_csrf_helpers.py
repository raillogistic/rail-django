import pytest
from django.middleware.csrf import get_token
from django.test import RequestFactory

from rail_django.middleware.auth.authentication import GraphQLAuthenticationMiddleware
from rail_django.utils.csrf import is_session_authenticated_request


pytestmark = pytest.mark.unit


class _AuthenticatedUser:
    is_authenticated = True


def test_cookie_auth_csrf_accepts_masked_token():
    rf = RequestFactory()
    bootstrap_request = rf.get("/csrf/")
    masked_token = get_token(bootstrap_request)
    cookie_token = bootstrap_request.META["CSRF_COOKIE"]

    request = rf.post(
        "/graphql/auth/",
        data='{"query":"mutation { refreshToken { ok } }"}',
        content_type="application/json",
        HTTP_X_CSRFTOKEN=masked_token,
    )
    request.COOKIES["csrftoken"] = cookie_token
    request.COOKIES["jwt"] = "cookie-access-token"

    middleware = GraphQLAuthenticationMiddleware(lambda req: None)

    assert middleware._is_csrf_token_valid(request) is True


def test_session_authenticated_request_ignores_jwt_cookie_auth():
    request = RequestFactory().post("/graphql/auth/")
    request.user = _AuthenticatedUser()
    request.auth_method = "jwt"
    request.META["HTTP_AUTHORIZATION"] = ""

    assert is_session_authenticated_request(request) is False


def test_session_authenticated_request_still_matches_django_session_auth():
    request = RequestFactory().post("/graphql/auth/")
    request.user = _AuthenticatedUser()
    request.auth_method = "anonymous"
    request.META["HTTP_AUTHORIZATION"] = ""

    assert is_session_authenticated_request(request) is True

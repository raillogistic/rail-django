"""
Unit tests for JWT view decorators.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.test import RequestFactory

from rail_django.extensions.auth import JWTManager
from rail_django.extensions.auth_decorators import jwt_optional, jwt_required, require_permissions
from test_app.models import Category

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_jwt_required_rejects_missing_token():
    rf = RequestFactory()

    @jwt_required
    def view(request):
        return JsonResponse({"ok": True})

    response = view(rf.get("/protected"))
    assert response.status_code == 401


@pytest.mark.django_db
def test_jwt_required_accepts_valid_token():
    rf = RequestFactory()
    User = get_user_model()
    user = User.objects.create_user(username="jwt_user", password="pass12345")
    token = JWTManager.generate_token(user)["token"]

    @jwt_required
    def view(request):
        return JsonResponse({"username": request.user.username})

    request = rf.get("/protected", HTTP_AUTHORIZATION=f"Bearer {token}")
    response = view(request)
    assert response.status_code == 200
    payload = json.loads(response.content.decode("utf-8"))
    assert payload["username"] == "jwt_user"


@pytest.mark.django_db
def test_jwt_optional_allows_anonymous_and_sets_user_when_token_present():
    rf = RequestFactory()
    User = get_user_model()
    user = User.objects.create_user(username="optional_user", password="pass12345")
    token = JWTManager.generate_token(user)["token"]

    @jwt_optional
    def view(request):
        if request.user.is_authenticated:
            return JsonResponse({"user": request.user.username})
        return JsonResponse({"user": "anonymous"})

    request = rf.get("/optional")
    request.user = AnonymousUser()
    response = view(request)
    payload = json.loads(response.content.decode("utf-8"))
    assert payload["user"] == "anonymous"

    request = rf.get("/optional", HTTP_AUTHORIZATION=f"Bearer {token}")
    response = view(request)
    payload = json.loads(response.content.decode("utf-8"))
    assert payload["user"] == "optional_user"


@pytest.mark.django_db
def test_require_permissions_enforces_permission():
    rf = RequestFactory()
    User = get_user_model()
    user = User.objects.create_user(username="perm_user", password="pass12345")
    token = JWTManager.generate_token(user)["token"]

    @require_permissions("test_app.view_category")
    def view(request):
        return JsonResponse({"ok": True})

    request = rf.get("/perm", HTTP_AUTHORIZATION=f"Bearer {token}")
    response = view(request)
    assert response.status_code == 403

    content_type = ContentType.objects.get_for_model(Category)
    perm = Permission.objects.get(codename="view_category", content_type=content_type)
    user.user_permissions.add(perm)

    request = rf.get("/perm", HTTP_AUTHORIZATION=f"Bearer {token}")
    response = view(request)
    assert response.status_code == 200


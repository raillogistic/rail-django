from types import SimpleNamespace

import pytest
from django.test import RequestFactory, override_settings

from rail_django.http.api.views.base import BaseAPIView


class _ProtectedView(BaseAPIView):
    auth_required = True

    def get(self, request):
        return self.json_response({"ok": True})


@pytest.mark.unit
@override_settings(GRAPHQL_SCHEMA_API_AUTH_REQUIRED=True)
def test_schema_api_requires_authentication_by_default():
    request = RequestFactory().get("/api/v1/schemas/")
    response = _ProtectedView.as_view()(request)
    assert response.status_code == 401


@pytest.mark.unit
@override_settings(GRAPHQL_SCHEMA_API_AUTH_REQUIRED=True)
def test_schema_api_options_bypasses_auth_for_preflight():
    request = RequestFactory().options("/api/v1/schemas/")
    response = _ProtectedView.as_view()(request)
    assert response.status_code == 200


@pytest.mark.unit
@override_settings(GRAPHQL_SCHEMA_API_AUTH_REQUIRED=True)
def test_schema_api_allows_pre_authenticated_request():
    request = RequestFactory().get("/api/v1/schemas/")
    request.user = SimpleNamespace(is_authenticated=True)
    response = _ProtectedView.as_view()(request)
    assert response.status_code == 200

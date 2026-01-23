"""
Unit tests for GraphQLAuthenticationMiddleware.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from rail_django.middleware.auth.authentication import GraphQLAuthenticationMiddleware

pytestmark = pytest.mark.unit

class MockUser:
    def __init__(self, id=1, username="testuser", is_active=True):
        self.id = id
        self.username = username
        self.is_active = is_active

class TestAuthMiddleware:
    @pytest.fixture
    def middleware(self):
        return GraphQLAuthenticationMiddleware(lambda r: HttpResponse())

    @pytest.fixture
    def rf(self):
        return RequestFactory()

    def test_is_graphql_request(self, middleware, rf):
        # Path based detection
        req = rf.post("/graphql/")
        assert middleware._is_graphql_request(req) is True
        
        req = rf.post("/other/")
        assert middleware._is_graphql_request(req) is False
        
        # Content-type based detection
        req = rf.post("/api/custom/", data=json.dumps({"query": "{ hello }"}), content_type="application/json")
        assert middleware._is_graphql_request(req) is True

    @patch("rail_django.middleware.auth.authentication.get_user_model")
    @patch("rail_django.extensions.auth.JWTManager.verify_token")
    def test_process_request_with_valid_token(self, mock_verify, mock_get_user_model, middleware, rf):
        # Setup
        mock_user = MockUser()
        mock_get_user_model().objects.get.return_value = mock_user
        mock_verify.return_value = {"user_id": 1}
        
        req = rf.post("/graphql/", HTTP_AUTHORIZATION="Bearer valid_token")
        
        # Execute
        middleware.process_request(req)
        
        # Verify
        assert req.user == mock_user
        assert req.auth_method == "jwt"
        assert hasattr(req, "auth_timestamp")

    @patch("rail_django.middleware.auth.authentication.get_user_model")
    @patch("rail_django.extensions.auth.JWTManager.verify_token")
    def test_process_request_with_invalid_token(self, mock_verify, mock_get_user_model, middleware, rf):
        # Setup
        mock_verify.return_value = None
        
        req = rf.post("/graphql/", HTTP_AUTHORIZATION="Bearer invalid_token")
        
        # Execute
        middleware.process_request(req)
        
        # Verify
        assert req.user.is_anonymous
        assert req.auth_method == "anonymous"

    def test_process_request_debug_bypass(self, middleware, rf):
        # Setup
        middleware.debug_mode = True
        middleware.debug_bypass = True
        
        req = rf.post("/graphql/")
        
        with patch.object(middleware, "_setup_debug_user") as mock_setup:
            middleware.process_request(req)
            mock_setup.assert_called_once_with(req)

    def test_extract_jwt_token_from_header(self, middleware, rf):
        req = rf.get("/graphql/", HTTP_AUTHORIZATION="Bearer my_token")
        assert middleware._extract_jwt_token(req) == "my_token"
        assert req._jwt_token_source == "header"

    def test_extract_jwt_token_from_cookie(self, middleware, rf):
        req = rf.get("/graphql/")
        req.COOKIES["jwt"] = "cookie_token"
        assert middleware._extract_jwt_token(req) == "cookie_token"
        assert req._jwt_token_source == "cookie"

    def test_process_response_adds_headers(self, middleware, rf):
        req = rf.post("/graphql/")
        req.auth_method = "jwt"
        resp = HttpResponse()
        
        middleware.process_response(req, resp)
        
        assert resp["X-Auth-Method"] == "jwt"
        assert resp["X-Content-Type-Options"] == "nosniff"
        assert resp["X-Frame-Options"] == "DENY"

    @patch("rail_django.middleware.auth.authentication.get_user_model")
    def test_setup_debug_user(self, mock_get_user_model, middleware, rf):
        mock_user = MockUser(username="debug_user")
        
        # Setup mock user model properly
        mock_model = MagicMock()
        mock_model.USERNAME_FIELD = "username"
        mock_model.objects.get_or_create.return_value = (mock_user, True)
        mock_get_user_model.return_value = mock_model
        
        req = rf.post("/graphql/")
        middleware._setup_debug_user(req)
        
        assert req.user == mock_user
        assert req.auth_method == "debug"

"""
GraphQLAuthenticationMiddleware implementation.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from .utils import _get_anonymous_user, get_client_ip

logger = logging.getLogger(__name__)


class GraphQLAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware pour l'authentification GraphQL avec support JWT.
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.get_response = get_response
        self.jwt_header_prefix = getattr(settings, "JWT_AUTH_HEADER_PREFIX", "Bearer")
        self.jwt_header_name = getattr(settings, "JWT_AUTH_HEADER_NAME", "HTTP_AUTHORIZATION")
        self.allow_cookie_auth = getattr(settings, "JWT_ALLOW_COOKIE_AUTH", True)
        self.enforce_csrf = getattr(settings, "JWT_ENFORCE_CSRF", not getattr(settings, "DEBUG", False))
        self.csrf_cookie_name = getattr(settings, "CSRF_COOKIE_NAME", "csrftoken")
        self.enable_audit_logging = getattr(settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True)
        self.debug_mode = getattr(settings, "DEBUG", False)
        self.debug_bypass = getattr(settings, "GRAPHQL_AUTH_DEBUG_BYPASS", False)
        self.user_cache_timeout = getattr(settings, "JWT_USER_CACHE_TIMEOUT", 300)
        self._jwt_user_cache: dict[str, tuple[int, float]] = {}

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        if not self._is_graphql_request(request): return None
        if self.debug_mode and self.debug_bypass:
            self._setup_debug_user(request)
            logger.info("Authentication bypassed for GraphQL request (DEBUG=True)")
            return None

        token = self._extract_jwt_token(request)
        user, auth_method = None, "anonymous"
        if token:
            token_source = getattr(request, "_jwt_token_source", "header")
            if (token_source == "cookie" and self.enforce_csrf and request.method not in ("GET", "HEAD", "OPTIONS", "TRACE")
                and not self._is_csrf_token_valid(request)):
                return self._csrf_failed_response()
            user = self._authenticate_jwt_token(token, request)
            if user: auth_method = "jwt"; self._log_authentication_event(request, user, "success", auth_method)
            else: self._log_authentication_event(request, None, "invalid_token", "jwt")

        request.user, request.auth_method = user or _get_anonymous_user(), auth_method
        request.auth_timestamp = datetime.now(timezone.utc)
        return None

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        if self._is_graphql_request(request):
            response["X-Content-Type-Options"], response["X-Frame-Options"], response["X-XSS-Protection"] = "nosniff", "DENY", "1; mode=block"
            if hasattr(request, "auth_method"): response["X-Auth-Method"] = request.auth_method
        if hasattr(request, "_set_auth_cookies"):
            for cookie in request._set_auth_cookies: response.set_cookie(**cookie)
        if hasattr(request, "_delete_auth_cookies"):
            for cookie_name in request._delete_auth_cookies: response.delete_cookie(cookie_name)
        return response

    def _is_graphql_request(self, request: HttpRequest) -> bool:
        graphql_endpoints = getattr(settings, "GRAPHQL_ENDPOINTS", ["/graphql/", "/graphql"])
        if any(request.path.startswith(endpoint) for endpoint in graphql_endpoints): return True
        if "application/json" in request.content_type.lower() and request.method == "POST":
            try:
                body = json.loads(request.body.decode("utf-8"))
                return "query" in body or "mutation" in body
            except Exception: pass
        return False

    def _extract_jwt_token(self, request: HttpRequest) -> Optional[str]:
        cookie_name = getattr(settings, "JWT_AUTH_COOKIE", "jwt")
        auth_header = request.META.get(self.jwt_header_name, "")
        if auth_header:
            header = auth_header.strip()
            if header.lower().startswith(f"{self.jwt_header_prefix.lower()} "):
                parts = header.split(" ", 1)
                if len(parts) == 2 and parts[1]:
                    request._jwt_token_source = "header"
                    return parts[1]
        if cookie_name and self.allow_cookie_auth:
            token = request.COOKIES.get(cookie_name)
            if token: request._jwt_token_source = "cookie"; return token
        token = request.GET.get("token")
        if token: request._jwt_token_source = "query"
        return token

    def _authenticate_jwt_token(self, token: str, request: HttpRequest) -> Optional[Any]:
        try:
            cache_key = f"jwt_user_{hash(token)}"
            cached = self._jwt_user_cache.get(cache_key)
            if cached and time.time() < cached[1]:
                try:
                    user = get_user_model().objects.get(id=cached[0])
                    if getattr(user, "is_active", True): return user
                except Exception: self._jwt_user_cache.pop(cache_key, None)

            from ...extensions.auth import JWTManager
            payload = JWTManager.verify_token(token, expected_type="access")
            if not payload: return None
            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id: return None
            user = get_user_model().objects.get(id=user_id)
            if not getattr(user, "is_active", True):
                self._log_authentication_event(request, user, "inactive_user", "jwt")
                return None
            self._jwt_user_cache[cache_key] = (user.id, time.time() + float(self.user_cache_timeout))
            return user
        except Exception: return None

    def _log_authentication_event(self, request: HttpRequest, user: Optional[Any], event_type: str, auth_method: str) -> None:
        if not self.enable_audit_logging: return
        try:
            from ...extensions.audit import audit_logger, AuditEventType
            if event_type == "success": audit_logger.log_login_attempt(request, user, success=True)
            elif event_type == "invalid_token": audit_logger.log_token_event(request, user, AuditEventType.TOKEN_INVALID, success=False, error_message="Token JWT invalide")
            elif event_type == "inactive_user": audit_logger.log_login_attempt(request, user, success=False, error_message="Compte utilisateur inactif")
            else: self._legacy_log_authentication_event(request, user, event_type, auth_method)
        except Exception: self._legacy_log_authentication_event(request, user, event_type, auth_method)

    def _legacy_log_authentication_event(self, request: HttpRequest, user: Optional[Any], event_type: str, auth_method: str) -> None:
        log_data = {"event_type": event_type, "auth_method": auth_method, "user_id": user.id if user else None, "username": user.username if user else None, "client_ip": get_client_ip(request), "user_agent": request.META.get("HTTP_USER_AGENT", "Unknown"), "timestamp": datetime.now(timezone.utc).isoformat(), "request_path": request.path, "request_method": request.method}
        if event_type == "success": logger.info(f"Authentification rÇ¸ussie: {log_data}")
        else: logger.warning(f"Tentative d'authentification Ç¸chouÇ¸e: {log_data}")

    def _is_csrf_token_valid(self, request: HttpRequest) -> bool:
        return request.META.get("HTTP_X_CSRFTOKEN") == request.COOKIES.get(self.csrf_cookie_name)

    def _csrf_failed_response(self) -> HttpResponse:
        return HttpResponse(json.dumps({"errors": [{"message": "CSRF validation failed", "code": "CSRF_FAILED"}]}), content_type="application/json", status=403)

    def _setup_debug_user(self, request: HttpRequest) -> None:
        try:
            UserModel = get_user_model()
            username_field = getattr(UserModel, "USERNAME_FIELD", "username")
            ident = "debug@example.com" if username_field == "email" else "debug_user"
            debug_user, created = UserModel.objects.get_or_create(**{username_field: ident}, defaults={"is_active": True, "is_staff": True, "is_superuser": True})
            if created: logger.info("Debug user created for development mode")
            request.user, request.auth_method, request.auth_timestamp = debug_user, "debug", datetime.now(timezone.utc)
        except Exception as e:
            logger.warning(f"Could not create debug user: {e}")
            request.user, request.auth_method, request.auth_timestamp = _get_anonymous_user(), "debug_anonymous", datetime.now(timezone.utc)

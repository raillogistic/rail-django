"""
Base API view for GraphQL schema management.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ...core.services import get_rate_limiter

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class BaseAPIView(View):
    """Base class for API views with common functionality."""

    auth_required = False
    rate_limit_enabled = False
    _json_body_cache_attr = "_rail_json_body_cache"
    _json_body_cache_set_attr = "_rail_json_body_cache_set"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """Handle CORS and common headers."""
        auth_required = self.auth_required and getattr(settings, "GRAPHQL_SCHEMA_API_AUTH_REQUIRED", True)
        if auth_required:
            auth_response = self._authenticate_request(request)
            if auth_response is not None:
                self._audit_request(request, auth_response, path_params=kwargs, extra_data={"auth_failed": True})
                return auth_response

        if self.rate_limit_enabled and request.method != "OPTIONS":
            rate_limit_response = self._check_rate_limit(request)
            if rate_limit_response is not None:
                self._audit_request(request, rate_limit_response, path_params=kwargs, extra_data={"rate_limited": True})
                return rate_limit_response

        response = super().dispatch(request, *args, **kwargs)

        if getattr(settings, "GRAPHQL_SCHEMA_API_CORS_ENABLED", True):
            allow_all = bool(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))
            if allow_all and not getattr(settings, "DEBUG", False): allow_all = False
            allowed_origins = getattr(settings, "GRAPHQL_SCHEMA_API_CORS_ALLOWED_ORIGINS", None)
            if allowed_origins is None: allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
            origin = request.META.get("HTTP_ORIGIN")
            if allow_all: response["Access-Control-Allow-Origin"] = "*"
            elif origin and origin in allowed_origins: response["Access-Control-Allow-Origin"] = origin; response["Vary"] = "Origin"
            elif not allowed_origins: response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

        self._audit_request(request, response, path_params=kwargs)
        return response

    def _check_rate_limit(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Apply a basic rate limit."""
        limiter = get_rate_limiter()
        result = limiter.check("schema_api", request=request)
        if not result.allowed:
            return self.error_response("Rate limit exceeded", status=429, details={"retry_after": result.retry_after})
        return None

    def _authenticate_request(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Authenticate request using JWT access tokens."""
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header: return self.error_response("Authentication required", status=401)
        if not (auth_header.startswith("Bearer ") or auth_header.startswith("Token ")): return self.error_response("Invalid authorization header", status=401)
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or not parts[1]: return self.error_response("Invalid token format", status=401)
        token = parts[1]
        try:
            from ...extensions.auth import JWTManager
            from django.contrib.auth import get_user_model
            payload = JWTManager.verify_token(token, expected_type="access")
            if not payload: return self.error_response("Invalid or expired token", status=401)
            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id: return self.error_response("Invalid token payload", status=401)
            user = get_user_model().objects.filter(id=user_id, is_active=True).first()
            if not user: return self.error_response("User not found or inactive", status=401)
            request.user = user
            request.jwt_payload = payload
            return None
        except Exception as exc:
            logger.warning("API authentication failed: %s", exc)
            return self.error_response("Authentication failed", status=401)

    def options(self, request: HttpRequest, *args, **kwargs):
        """Handle preflight requests."""
        return JsonResponse({}, status=200)

    def json_response(self, data: dict[str, Any], status: int = 200) -> JsonResponse:
        """Create a JSON response."""
        return JsonResponse({'timestamp': datetime.now().isoformat(), 'status': 'success' if 200 <= status < 300 else 'error', 'data': data}, status=status)

    def error_response(self, message: str, status: int = 400, details: Optional[dict] = None) -> JsonResponse:
        """Create an error response."""
        return self.json_response({'message': message, 'details': details or {}}, status=status)

    def parse_json_body(self, request: HttpRequest) -> Optional[dict[str, Any]]:
        """Parse JSON body."""
        if getattr(request, self._json_body_cache_set_attr, False): return getattr(request, self._json_body_cache_attr, None)
        parsed_body = None
        try:
            content_type = (request.content_type or "").lower()
            if request.body and (not content_type or content_type.startswith("application/json")):
                parsed_body = json.loads(request.body.decode('utf-8'))
        except Exception as e: logger.error(f"Error parsing JSON body: {e}")
        setattr(request, self._json_body_cache_attr, parsed_body); setattr(request, self._json_body_cache_set_attr, True)
        return parsed_body

    def _audit_request(self, request: HttpRequest, response: JsonResponse, *, path_params: Optional[dict[str, Any]] = None, extra_data: Optional[dict[str, Any]] = None) -> None:
        if request.method == "OPTIONS": return
        try:
            from ...security import security, EventType, Outcome
            body_data = self.parse_json_body(request) if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None
            event_type = self._get_audit_event_type(request, body_data, EventType)
            additional_data = {"component": "schema_api", "view": self.__class__.__name__, "status_code": response.status_code}
            if path_params: additional_data["path_params"] = path_params
            if isinstance(body_data, dict) and body_data.get("action"): additional_data["action"] = body_data.get("action")
            if extra_data: additional_data.update(extra_data)

            outcome = Outcome.SUCCESS if response.status_code < 400 else Outcome.FAILURE
            if response.status_code == 401 or response.status_code == 403:
                outcome = Outcome.DENIED

            security.emit(
                event_type,
                request=request,
                outcome=outcome,
                action=f"API Request {request.method} {request.path}",
                context=additional_data,
                error=self._extract_error_message(response) if outcome != Outcome.SUCCESS else None
            )
        except Exception: pass

    def _get_audit_event_type(self, request: HttpRequest, body_data: Optional[dict[str, Any]], audit_enum: Any) -> Any:
        method, view_name = request.method.upper(), self.__class__.__name__
        if method in {"GET", "HEAD", "OPTIONS"}: return audit_enum.DATA_READ
        if method in {"PUT", "PATCH"}: return audit_enum.DATA_UPDATE
        if method == "DELETE": return audit_enum.DATA_DELETE
        if method == "POST":
            if view_name in {"SchemaManagementAPIView", "SchemaDiscoveryAPIView"}:
                if isinstance(body_data, dict) and body_data.get("action") == "clear_all": return audit_enum.DATA_DELETE
                return audit_enum.DATA_UPDATE
            return audit_enum.DATA_CREATE
        return audit_enum.DATA_ACCESS

    def _extract_error_message(self, response: JsonResponse) -> Optional[str]:
        try:
            payload = json.loads(response.content.decode("utf-8"))
            if isinstance(payload, dict):
                data = payload.get("data", payload)
                return data.get("message") or data.get("error") if isinstance(data, dict) else payload.get("message") or payload.get("error")
        except Exception: pass
        return None

    def _require_admin(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Ensure the request is authenticated and authorized for management actions."""
        if not getattr(settings, "GRAPHQL_SCHEMA_API_AUTH_REQUIRED", True): return None
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False): return self.error_response("Authentication required", status=401)
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False): return None
        required_perms = getattr(settings, "GRAPHQL_SCHEMA_API_REQUIRED_PERMISSIONS", ["rail_django.manage_schema"])
        if required_perms and not any(user.has_perm(perm) for perm in required_perms): return self.error_response("Admin permissions required", status=403)
        return None

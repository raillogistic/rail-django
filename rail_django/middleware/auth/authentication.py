"""
GraphQLAuthenticationMiddleware implementation.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from .utils import _get_anonymous_user
from ...utils.csrf import validate_csrf_request

logger = logging.getLogger(__name__)


class GraphQLAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware for GraphQL authentication with JWT support.

    Performance optimisation
    -----------------------
    JWT token verification results are cached in-memory using a dict keyed
    by token hash.  The cache stores essential user attributes so that
    repeat requests with the same valid token skip both JWT decode **and**
    the database lookup entirely.
    """

    # Lightweight snapshot stored in the per-process cache.
    # Avoids a DB round-trip on every authenticated request.
    __slots__ = ()

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.get_response = get_response
        self.jwt_header_prefix = getattr(settings, "JWT_AUTH_HEADER_PREFIX", "Bearer")
        self.jwt_header_name = getattr(
            settings, "JWT_AUTH_HEADER_NAME", "HTTP_AUTHORIZATION"
        )
        self.allow_cookie_auth = getattr(settings, "JWT_ALLOW_COOKIE_AUTH", True)
        self.enforce_csrf = getattr(
            settings, "JWT_ENFORCE_CSRF", not getattr(settings, "DEBUG", False)
        )
        self.csrf_cookie_name = getattr(settings, "CSRF_COOKIE_NAME", "csrftoken")
        self.enable_audit_logging = getattr(
            settings, "GRAPHQL_ENABLE_AUDIT_LOGGING", True
        )
        self.debug_mode = getattr(settings, "DEBUG", False)
        self.debug_bypass = getattr(settings, "GRAPHQL_AUTH_DEBUG_BYPASS", False)
        self.user_cache_timeout = getattr(settings, "JWT_USER_CACHE_TIMEOUT", 300)
        # Cache layout: { cache_key: (user_id, expiry_ts, snapshot_dict) }
        self._jwt_user_cache: dict[str, tuple[int, float, dict]] = {}

        # Pre-compute graphql endpoint prefixes for fast path matching
        self._graphql_endpoints: tuple[str, ...] = tuple(
            getattr(settings, "GRAPHQL_ENDPOINTS", ["/graphql/", "/graphql"])
        )

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        if not self._is_graphql_request(request):
            return None
        if self.debug_mode and self.debug_bypass:
            self._setup_debug_user(request)
            logger.info("Authentication bypassed for GraphQL request (DEBUG=True)")
            return None

        token = self._extract_jwt_token(request)
        user, auth_method = None, "anonymous"
        if token:
            token_source = getattr(request, "_jwt_token_source", "header")
            if (
                token_source == "cookie"
                and self.enforce_csrf
                and request.method not in ("GET", "HEAD", "OPTIONS", "TRACE")
                and not self._is_csrf_token_valid(request)
            ):
                return self._csrf_failed_response()
            user = self._authenticate_jwt_token(token, request)
            if user:
                auth_method = "jwt"
                self._audit_auth_event(request, user, "success", auth_method)
            else:
                self._audit_auth_event(request, None, "invalid_token", "jwt")

        request.user, request.auth_method = user or _get_anonymous_user(), auth_method
        request.auth_timestamp = datetime.now(timezone.utc)
        return None

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        if self._is_graphql_request(request):
            (
                response["X-Content-Type-Options"],
                response["X-Frame-Options"],
                response["X-XSS-Protection"],
            ) = "nosniff", "DENY", "1; mode=block"
            if hasattr(request, "auth_method"):
                response["X-Auth-Method"] = request.auth_method
        if hasattr(request, "_set_auth_cookies"):
            for cookie in request._set_auth_cookies:
                response.set_cookie(**cookie)
        if hasattr(request, "_delete_auth_cookies"):
            for cookie_name in request._delete_auth_cookies:
                response.delete_cookie(cookie_name)
        return response

    def _is_graphql_request(self, request: HttpRequest) -> bool:
        """Return True when the request targets a GraphQL endpoint.

        Uses path-prefix matching first (fast).  Falls back to content-type
        body sniffing only when path does not match, for backward
        compatibility with custom endpoint paths.
        """
        request_path = request.path
        if any(request_path.startswith(ep) for ep in self._graphql_endpoints):
            return True
        # Fallback: body sniffing for custom endpoints
        if (
            request.method == "POST"
            and "application/json" in getattr(request, "content_type", "").lower()
        ):
            try:
                body = json.loads(request.body.decode("utf-8"))
                return "query" in body or "mutation" in body
            except Exception:
                pass
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
            if token:
                request._jwt_token_source = "cookie"
                return token
        return None

    def _authenticate_jwt_token(
        self, token: str, request: HttpRequest
    ) -> Optional[Any]:
        """Authenticate a JWT token, using an in-memory cache to skip DB.

        Cache structure per entry:
          (user_id, expiry_timestamp, user_snapshot_dict)

        On cache hit the user object is reconstructed from the snapshot
        without touching the database.  If the user has been deactivated
        since the snapshot was taken, the deactivation will be detected
        when the cache entry expires (default 5 min).

        Args:
            token: Raw JWT token string.
            request: The current HTTP request.

        Returns:
            Authenticated user instance or None.
        """
        try:
            cache_key = f"jwt_user_{hash(token)}"
            cached = self._jwt_user_cache.get(cache_key)
            if cached is not None and time.time() < cached[1]:
                # ── Fast path: reconstruct user from cached snapshot ──
                snapshot = cached[2]
                UserModel = get_user_model()
                user = UserModel.__new__(UserModel)
                user.__dict__.update(snapshot)
                # Attach Django model state so the ORM doesn't consider
                # this instance as unsaved / from a different DB.
                from django.db.models.base import ModelState
                user._state = ModelState()
                user._state.db = "default"
                user._state.adding = False
                return user

            from ...extensions.auth import JWTManager

            payload = JWTManager.verify_token(token, expected_type="access")
            if not payload:
                return None
            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id:
                return None
            user = get_user_model().objects.get(id=user_id)
            if not getattr(user, "is_active", True):
                self._audit_auth_event(request, user, "inactive_user", "jwt")
                return None

            # Store a lightweight snapshot of the user attributes
            snapshot = {
                k: v for k, v in user.__dict__.items()
                if not k.startswith("_")
            }
            self._jwt_user_cache[cache_key] = (
                user.id,
                time.time() + float(self.user_cache_timeout),
                snapshot,
            )
            return user
        except Exception:
            return None

    def _audit_auth_event(
        self,
        request: HttpRequest,
        user: Optional[Any],
        event_type: str,
        auth_method: str,
    ) -> None:
        if not self.enable_audit_logging:
            return
        try:
            from ...security import security, EventType, Outcome

            if event_type == "success":
                security.auth_success(request, user.id, user.username)
            elif event_type == "invalid_token":
                security.emit(
                    EventType.AUTH_TOKEN_INVALID,
                    request=request,
                    outcome=Outcome.FAILURE,
                    error="Token JWT invalide",
                )
            elif event_type == "inactive_user":
                security.auth_failure(
                    request,
                    user.username if user else None,
                    "Compte utilisateur inactif",
                )
        except Exception as e:
            logger.warning(f"Error auditing auth event: {e}")

    def _is_csrf_token_valid(self, request: HttpRequest) -> bool:
        is_valid, reject_reason = validate_csrf_request(request)
        if not is_valid:
            logger.warning(
                "JWT cookie-auth CSRF rejection path=%s origin=%s referer=%s reason=%s",
                getattr(request, "path", ""),
                request.META.get("HTTP_ORIGIN"),
                request.META.get("HTTP_REFERER"),
                reject_reason,
            )
        return is_valid

    def _csrf_failed_response(self) -> HttpResponse:
        return HttpResponse(
            json.dumps(
                {
                    "errors": [
                        {"message": "CSRF validation failed", "code": "CSRF_FAILED"}
                    ]
                }
            ),
            content_type="application/json",
            status=403,
        )

    def _setup_debug_user(self, request: HttpRequest) -> None:
        try:
            UserModel = get_user_model()
            username_field = getattr(UserModel, "USERNAME_FIELD", "username")
            ident = "debug@example.com" if username_field == "email" else "debug_user"
            debug_user, created = UserModel.objects.get_or_create(
                **{username_field: ident},
                defaults={"is_active": True, "is_staff": True, "is_superuser": True},
            )
            if created:
                logger.info("Debug user created for development mode")
            request.user, request.auth_method, request.auth_timestamp = (
                debug_user,
                "debug",
                datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.warning(f"Could not create debug user: {e}")
            request.user, request.auth_method, request.auth_timestamp = (
                _get_anonymous_user(),
                "debug_anonymous",
                datetime.now(timezone.utc),
            )

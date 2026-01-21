"""
GraphQLRateLimitMiddleware implementation.
"""

import json
import logging
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from ...core.services import get_rate_limiter

logger = logging.getLogger(__name__)


class GraphQLRateLimitMiddleware(MiddlewareMixin):
    """
    Middleware de limitation de dÇ¸bit spÇ¸cifique aux requÇºtes d'authentification GraphQL.
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.get_response = get_response
        self.rate_limiter = get_rate_limiter()
        self.debug_mode = getattr(settings, "DEBUG", False)

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        if not self._is_graphql_request(request): return None
        if self.debug_mode:
            logger.info("Rate limiting bypassed for GraphQL request (DEBUG=True)")
            return None

        self._current_request = request
        result = self.rate_limiter.check("graphql", request=request)
        if not result.allowed:
            return self._create_rate_limit_response("Trop de requÇºtes GraphQL", retry_after=result.retry_after)

        if self._is_login_request(request):
            result = self.rate_limiter.check("graphql_login", request=request)
            if not result.allowed:
                return self._create_rate_limit_response("Trop de tentatives de connexion", retry_after=result.retry_after)
        return None

    def _is_graphql_request(self, request: HttpRequest) -> bool:
        graphql_endpoints = getattr(settings, "GRAPHQL_ENDPOINTS", ["/graphql/", "/graphql"])
        return any(request.path.startswith(endpoint) for endpoint in graphql_endpoints)

    def _is_login_request(self, request: HttpRequest) -> bool:
        try:
            if hasattr(request, "body") and request.body:
                body = json.loads(request.body.decode("utf-8"))
                query = body.get("query", "").lower()
                return "login" in query or ("mutation" in query and "login" in query)
        except Exception: pass
        return False

    def _create_rate_limit_response(self, message: str, retry_after: Optional[int] = None) -> HttpResponse:
        try:
            from ...extensions.audit import audit_logger
            if hasattr(self, "_current_request"): audit_logger.log_rate_limit_exceeded(self._current_request, "GraphQL rate limit")
        except Exception: pass
        response = HttpResponse(json.dumps({"errors": [{"message": message, "code": "RATE_LIMITED"}]}), content_type="application/json", status=429)
        if retry_after is not None: response["Retry-After"] = str(int(retry_after))
        return response

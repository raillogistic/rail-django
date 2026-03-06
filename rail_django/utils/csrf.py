"""CSRF helpers for endpoints that allow token auth but must reject forged session requests."""

from __future__ import annotations

import logging

from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import CsrfViewMiddleware

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class _ReasonCapturingCsrfViewMiddleware(CsrfViewMiddleware):
    """Expose Django's internal CSRF rejection reason for logging/debugging."""

    def __init__(self) -> None:
        super().__init__(lambda req: None)
        self.reject_reason: str | None = None

    def _reject(self, request, reason):
        self.reject_reason = str(reason)
        return super()._reject(request, reason)


def is_session_authenticated_request(request: HttpRequest) -> bool:
    if getattr(request, "auth_method", None) == "jwt":
        return False
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    auth_header = (request.META.get("HTTP_AUTHORIZATION", "") or "").strip().lower()
    return not (auth_header.startswith("bearer ") or auth_header.startswith("token "))


def enforce_csrf_for_session_auth(
    request: HttpRequest,
    *,
    failure_message: str = "CSRF validation failed.",
) -> JsonResponse | None:
    if request.method in SAFE_METHODS or not is_session_authenticated_request(request):
        return None

    middleware = _ReasonCapturingCsrfViewMiddleware()
    rejection = middleware.process_view(request, None, (), {})
    if rejection is not None:
        logger.warning(
            "CSRF rejection for session-authenticated request path=%s origin=%s referer=%s reason=%s",
            getattr(request, "path", ""),
            request.META.get("HTTP_ORIGIN"),
            request.META.get("HTTP_REFERER"),
            middleware.reject_reason,
        )
        return JsonResponse({"errors": [{"message": failure_message}]}, status=403)
    return None


def validate_csrf_request(request: HttpRequest) -> tuple[bool, str | None]:
    """
    Validate a request using Django's CSRF middleware and return the rejection reason.
    """
    middleware = _ReasonCapturingCsrfViewMiddleware()
    rejection = middleware.process_view(request, None, (), {})
    return rejection is None, middleware.reject_reason

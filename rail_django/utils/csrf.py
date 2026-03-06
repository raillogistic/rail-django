"""CSRF helpers for endpoints that allow token auth but must reject forged session requests."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def is_session_authenticated_request(request: HttpRequest) -> bool:
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

    middleware = CsrfViewMiddleware(lambda req: None)
    rejection = middleware.process_view(request, None, (), {})
    if rejection is not None:
        return JsonResponse({"errors": [{"message": failure_message}]}, status=403)
    return None

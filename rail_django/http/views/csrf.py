"""
CSRF bootstrap endpoint for cookie-based auth flows.
"""

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods


@ensure_csrf_cookie
@require_http_methods(["GET"])
def csrf_token_view(request):
    """
    Return a CSRF token in JSON and expose it in a response header.
    """
    token = get_token(request)
    response = JsonResponse({"csrfToken": token})
    response["X-CSRFToken"] = token
    return response

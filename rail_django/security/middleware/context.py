from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin
from ..context import SecurityContext

SECURITY_CONTEXT_ATTR = "_security_context"


class SecurityContextMiddleware(MiddlewareMixin):
    """Injects SecurityContext into every request."""

    def process_request(self, request: HttpRequest) -> None:
        context = SecurityContext.from_request(request)
        setattr(request, SECURITY_CONTEXT_ATTR, context)
        # Add correlation ID to response headers
        request._security_correlation_id = context.correlation_id

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        correlation_id = getattr(request, "_security_correlation_id", None)
        if correlation_id:
            response["X-Correlation-ID"] = correlation_id
        return response


def get_security_context(request: HttpRequest) -> SecurityContext:
    """Retrieve security context from request."""
    ctx = getattr(request, SECURITY_CONTEXT_ATTR, None)
    if ctx is None:
        # Fallback: create context if middleware wasn't applied
        ctx = SecurityContext.from_request(request)
        setattr(request, SECURITY_CONTEXT_ATTR, ctx)
    return ctx

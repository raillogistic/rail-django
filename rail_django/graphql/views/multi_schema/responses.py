"""
Response helper methods for MultiSchemaGraphQLView.
"""

from django.conf import settings
from django.http import JsonResponse

class ResponseMixin:
    """Mixin for common view responses."""

    def _introspection_disabled_response(self) -> JsonResponse:
        return JsonResponse({"errors": [{"message": "Introspection is disabled for this schema", "extensions": {"code": "INTROSPECTION_DISABLED"}}]}, status=403)

    def _schema_not_found_response(self, schema_name: str) -> JsonResponse:
        return JsonResponse({"errors": [{"message": f"Schema '{schema_name}' not found", "extensions": {"code": "SCHEMA_NOT_FOUND", "schema_name": schema_name}}]}, status=404)

    def _schema_disabled_response(self, schema_name: str) -> JsonResponse:
        return JsonResponse({"errors": [{"message": f"Schema '{schema_name}' is currently disabled", "extensions": {"code": "SCHEMA_DISABLED", "schema_name": schema_name}}]}, status=403)

    def _authentication_required_response(self) -> JsonResponse:
        return JsonResponse({"errors": [{"message": "Authentication required for this schema", "extensions": {"code": "authentication_required"}}]}, status=200)

    def _error_response(self, error_message: str) -> JsonResponse:
        return JsonResponse({"errors": [{"message": "Internal server error", "extensions": {"code": "INTERNAL_ERROR", "details": error_message if settings.DEBUG else None}}]}, status=500)

"""
SchemaListView implementation.
"""

import logging
from typing import Any, Optional

from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.generic import View

from .utils import (
    _get_authenticated_user,
    _get_effective_schema_settings,
    _host_allowed,
)

logger = logging.getLogger(__name__)


class SchemaListView(View):
    """
    View for listing available GraphQL schemas and their metadata.
    """

    template_name = "schema_registry.html"

    def get(self, request: HttpRequest) -> JsonResponse:
        """Return available schemas as JSON or a rendered HTML page."""
        wants_html = self._wants_html(request)
        try:
            from ...core.registry import schema_registry

            schema_registry.discover_schemas()
            schemas = self._serialize_schemas(schema_registry.list_schemas(), request=request)

            if wants_html:
                return render(
                    request,
                    self.template_name,
                    self._build_context(schemas),
                )

            return JsonResponse({"schemas": schemas, "count": len(schemas)})

        except ImportError:
            if wants_html:
                context = self._build_context([])
                context["error"] = "Schema registry not available"
                return render(request, self.template_name, context, status=503)

            return JsonResponse({"error": "Schema registry not available"}, status=503)
        except Exception as e:
            logger.error(f"Error listing schemas: {e}")
            if wants_html:
                context = self._build_context([])
                context["error"] = "Failed to list schemas"
                return render(request, self.template_name, context, status=500)

            return JsonResponse({"error": "Failed to list schemas"}, status=500)

    def _serialize_schemas(
        self,
        schema_list,
        request: Optional[HttpRequest] = None,
    ) -> list[dict[str, Any]]:
        schemas = []
        for schema_info in schema_list:
            if not schema_info:
                continue
            if request and not self._is_graphiql_visible(request, schema_info):
                continue
            settings_dict = getattr(schema_info, "settings", {}) or {}
            schema_settings = settings_dict.get("schema_settings", {})
            if not isinstance(schema_settings, dict):
                schema_settings = {}
            raw_models = getattr(schema_info, "models", []) or []
            if isinstance(raw_models, (list, tuple, set)):
                models = list(raw_models)
            else:
                models = []
            public_info = {
                "name": getattr(schema_info, "name", ""),
                "description": getattr(schema_info, "description", ""),
                "version": getattr(schema_info, "version", "1.0.0"),
                "enabled": getattr(schema_info, "enabled", True),
                "graphiql_enabled": schema_settings.get(
                    "enable_graphiql",
                    settings_dict.get("enable_graphiql", True),
                ),
                "authentication_required": schema_settings.get(
                    "authentication_required",
                    settings_dict.get("authentication_required", False),
                ),
                "models": models,
            }
            schemas.append(public_info)
        return schemas

    def _is_graphiql_visible(self, request: HttpRequest, schema_info: dict[str, Any]) -> bool:
        if str(getattr(schema_info, "name", "")).lower() != "graphiql":
            return True

        schema_settings = _get_effective_schema_settings(schema_info)
        allowed_hosts = schema_settings.get("graphiql_allowed_hosts") or []
        if not isinstance(allowed_hosts, (list, tuple, set)):
            allowed_hosts = [str(allowed_hosts)]
        if not _host_allowed(request, list(allowed_hosts)):
            return False

        if schema_settings.get("graphiql_superuser_only", False):
            user = _get_authenticated_user(request)
            if not user or not getattr(user, "is_superuser", False):
                return False

        return True

    def _build_context(self, schemas: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(schemas)
        enabled = sum(1 for schema in schemas if schema.get("enabled"))
        graphiql_enabled = sum(
            1 for schema in schemas if schema.get("graphiql_enabled")
        )
        auth_required = sum(
            1 for schema in schemas if schema.get("authentication_required")
        )
        return {
            "schemas": schemas,
            "counts": {
                "total": total,
                "enabled": enabled,
                "disabled": total - enabled,
                "graphiql_enabled": graphiql_enabled,
                "auth_required": auth_required,
            },
        }

    def _wants_html(self, request: HttpRequest) -> bool:
        format_param = str(request.GET.get("format", "") or "").lower()
        if format_param == "json":
            return False
        if format_param == "html":
            return True

        accept = str(request.META.get("HTTP_ACCEPT", "") or "")
        return "text/html" in accept.lower()

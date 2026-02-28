"""Reusable welcome/dashboard views for scaffolded projects."""

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.views.generic import TemplateView


class SuperuserRequiredTemplateView(TemplateView):
    """TemplateView mixin that restricts access to authenticated superusers."""

    login_url_name = "admin:login"

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                reverse(self.login_url_name),
            )
        if not user.is_superuser:
            raise PermissionDenied("Superuser access required.")
        return super().dispatch(request, *args, **kwargs)


class WelcomeView(SuperuserRequiredTemplateView):
    """Superuser-only operations dashboard for HTTP and GraphQL endpoints."""

    template_name = "root/welcome.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["quick_links"] = [
            {
                "label": "Django admin",
                "href": "/admin/",
                "description": "Manage users, models, and permissions.",
            },
            {
                "label": "GraphQL endpoint",
                "href": "/graphql/gql/",
                "description": "Primary authenticated GraphQL schema.",
            },
            {
                "label": "Schema registry",
                "href": "/schemas/",
                "description": "Inspect active schema registrations.",
            },
            {
                "label": "GraphiQL",
                "href": "/graphql/graphiql/",
                "description": "Interactive IDE (when enabled by settings).",
            },
        ]
        context["api_sections"] = [
            {
                "id": "schema-core",
                "title": "Schema registry API",
                "summary": "Core /api/v1 routes from rail_django.http.api.urls and schema views.",
                "items": [
                    {
                        "method": "GET",
                        "path": "/api/v1/schemas/",
                        "href": "/api/v1/schemas/",
                        "description": "List registered schemas.",
                    },
                    {
                        "method": "POST",
                        "path": "/api/v1/schemas/",
                        "href": None,
                        "description": "Create/register a schema.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/schemas/<schema_name>/",
                        "href": "/api/v1/schemas/gql/",
                        "description": "Read one schema (example uses gql).",
                    },
                    {
                        "method": "PUT",
                        "path": "/api/v1/schemas/<schema_name>/",
                        "href": None,
                        "description": "Update schema configuration.",
                    },
                    {
                        "method": "DELETE",
                        "path": "/api/v1/schemas/<schema_name>/",
                        "href": None,
                        "description": "Delete schema registration.",
                    },
                    {
                        "method": "POST",
                        "path": "/api/v1/management/",
                        "href": None,
                        "description": "Enable/disable/clear schemas.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/discovery/",
                        "href": "/api/v1/discovery/",
                        "description": "Get discovery status.",
                    },
                    {
                        "method": "POST",
                        "path": "/api/v1/discovery/",
                        "href": None,
                        "description": "Run auto-discovery now.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/health/",
                        "href": "/api/v1/health/",
                        "description": "Registry health diagnostics.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/metrics/",
                        "href": "/api/v1/metrics/",
                        "description": "Schema and plugin metrics.",
                    },
                ],
            },
            {
                "id": "schema-ops",
                "title": "Schema snapshot operations",
                "summary": "Snapshot export/history/diff routes backed by schema_ops views.",
                "items": [
                    {
                        "method": "GET",
                        "path": "/api/v1/schemas/<schema_name>/export/?format=json|sdl|markdown",
                        "href": "/api/v1/schemas/gql/export/?format=json",
                        "description": "Export current or versioned schema.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/schemas/<schema_name>/history/?limit=10",
                        "href": "/api/v1/schemas/gql/history/",
                        "description": "List schema snapshots.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/schemas/<schema_name>/diff/?from_version=v1&to_version=v2",
                        "href": "/api/v1/schemas/gql/diff/",
                        "description": "Compare two schema versions.",
                    },
                ],
            },
            {
                "id": "jobs-export",
                "title": "Export and task APIs",
                "summary": "Model export routes plus async status endpoints.",
                "items": [
                    {
                        "method": "POST",
                        "path": "/api/v1/export/",
                        "href": None,
                        "description": "Create an export job.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/export/",
                        "href": "/api/v1/export/",
                        "description": "List export jobs.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/export/jobs/<job_id>/",
                        "href": None,
                        "description": "Read export job status.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/export/jobs/<job_id>/download/",
                        "href": None,
                        "description": "Download completed export output.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/tasks/<task_id>/",
                        "href": None,
                        "description": "Read background task execution status.",
                    },
                ],
            },
            {
                "id": "document-endpoints",
                "title": "Template and document endpoints",
                "summary": "PDF, Excel, and import-template routes included under /api/v1.",
                "items": [
                    {
                        "method": "GET",
                        "path": "/api/v1/templates/catalog/",
                        "href": "/api/v1/templates/catalog/",
                        "description": "List available PDF templates.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/templates/preview/<template_path>/<pk>/",
                        "href": None,
                        "description": "Render HTML preview for a template target.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/templates/<template_path>/<pk>/",
                        "href": None,
                        "description": "Generate PDF response.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/templates/jobs/<job_id>/",
                        "href": None,
                        "description": "Read PDF async job status.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/templates/jobs/<job_id>/download/",
                        "href": None,
                        "description": "Download generated PDF output.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/excel/catalog/",
                        "href": "/api/v1/excel/catalog/",
                        "description": "List available Excel templates.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/excel/<template_path>/?pk=<pk>",
                        "href": None,
                        "description": "Generate XLSX output.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/excel/jobs/<job_id>/",
                        "href": None,
                        "description": "Read Excel async job status.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/excel/jobs/<job_id>/download/",
                        "href": None,
                        "description": "Download generated XLSX output.",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/import/templates/<app_label>/<model_name>/",
                        "href": None,
                        "description": "Download CSV import template for a model.",
                    },
                ],
            },
        ]
        return context


__all__ = ["SuperuserRequiredTemplateView", "WelcomeView"]

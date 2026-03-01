"""Reusable welcome/dashboard views for scaffolded projects."""

from copy import deepcopy

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import NoReverseMatch, reverse
from django.views.generic import TemplateView

QUICK_LINKS = [
    {
        "label": "Control center",
        "href": "/control-center/",
        "description": "Operations cockpit with health, security, logs, jobs, and backups.",
    },
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
    {
        "label": "Health dashboard",
        "href": "/health/",
        "description": "Live health dashboard for system components.",
    },
    {
        "label": "Audit dashboard",
        "href": "/audit/dashboard/",
        "description": "Security and access audit timeline dashboard.",
    },
    {
        "label": "Log viewer",
        "href": "/audit/logs/",
        "description": "Read runtime logs from the protected log viewer.",
    },
    {
        "label": "PDF catalog",
        "href": "/api/v1/templates/catalog/",
        "description": "Template catalog page for PDF documents.",
    },
    {
        "label": "Excel catalog",
        "href": "/api/v1/excel/catalog/",
        "description": "Template catalog page for Excel exports.",
    },
]

SYSTEM_DASHBOARDS = [
    {
        "title": "Control Center",
        "href": "/control-center/",
        "badge": "Ops",
        "description": "Unified operations pages: overview, health, security, logs, jobs, backups, capacity/cost, and settings.",
    },
    {
        "title": "Schema Registry UI",
        "href": "/schemas/",
        "badge": "Schema",
        "description": "Template page for schema registry operations and status.",
    },
    {
        "title": "Health Dashboard",
        "href": "/health/",
        "badge": "Health",
        "description": "Template page with live health metrics, readiness and component checks.",
    },
    {
        "title": "Audit Dashboard",
        "href": "/audit/dashboard/",
        "badge": "Audit",
        "description": "Template page for security events, access audits and trends.",
    },
    {
        "title": "Log Viewer",
        "href": "/audit/logs/",
        "badge": "Logs",
        "description": "Template page to inspect protected application log streams.",
    },
    {
        "title": "PDF Catalog",
        "href": "/api/v1/templates/catalog/",
        "badge": "PDF",
        "description": "Template page listing available PDF export templates.",
    },
    {
        "title": "Excel Catalog",
        "href": "/api/v1/excel/catalog/",
        "badge": "Excel",
        "description": "Template page listing available Excel export templates.",
    },
]

API_SECTIONS = [
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
                "key": "schema-create",
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
                "key": "schema-update",
                "method": "PUT",
                "path": "/api/v1/schemas/<schema_name>/",
                "href": None,
                "description": "Update schema configuration.",
            },
            {
                "key": "schema-delete",
                "method": "DELETE",
                "path": "/api/v1/schemas/<schema_name>/",
                "href": None,
                "description": "Delete schema registration.",
            },
            {
                "key": "schema-management",
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
                "key": "schema-discovery-run",
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
                "key": "export-create",
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
                "key": "export-job-status",
                "method": "GET",
                "path": "/api/v1/export/jobs/<job_id>/",
                "href": None,
                "description": "Read export job status.",
            },
            {
                "key": "export-job-download",
                "method": "GET",
                "path": "/api/v1/export/jobs/<job_id>/download/",
                "href": None,
                "description": "Download completed export output.",
            },
            {
                "key": "task-status",
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
                "key": "template-preview",
                "method": "GET",
                "path": "/api/v1/templates/preview/<template_path>/<pk>/",
                "href": None,
                "description": "Render HTML preview for a template target.",
            },
            {
                "key": "template-generate",
                "method": "GET",
                "path": "/api/v1/templates/<template_path>/<pk>/",
                "href": None,
                "description": "Generate PDF response.",
            },
            {
                "key": "template-job-status",
                "method": "GET",
                "path": "/api/v1/templates/jobs/<job_id>/",
                "href": None,
                "description": "Read PDF async job status.",
            },
            {
                "key": "template-job-download",
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
                "key": "excel-generate",
                "method": "GET",
                "path": "/api/v1/excel/<template_path>/?pk=<pk>",
                "href": None,
                "description": "Generate XLSX output.",
            },
            {
                "key": "excel-job-status",
                "method": "GET",
                "path": "/api/v1/excel/jobs/<job_id>/",
                "href": None,
                "description": "Read Excel async job status.",
            },
            {
                "key": "excel-job-download",
                "method": "GET",
                "path": "/api/v1/excel/jobs/<job_id>/download/",
                "href": None,
                "description": "Download generated XLSX output.",
            },
            {
                "key": "import-template-download",
                "method": "GET",
                "path": "/api/v1/import/templates/<app_label>/<model_name>/",
                "href": None,
                "description": "Download CSV import template for a model.",
            },
        ],
    },
]


def _build_endpoint_guides():
    guides = {}
    for section in API_SECTIONS:
        for item in section["items"]:
            key = item.get("key")
            if not key:
                continue
            guides[key] = {
                "key": key,
                "section_id": section["id"],
                "section_title": section["title"],
                "method": item["method"],
                "path": item["path"],
                "description": item["description"],
            }
    return guides


ENDPOINT_GUIDES = _build_endpoint_guides()


def _build_sample_curl(endpoint):
    lines = [
        f'curl -X {endpoint["method"]} "https://<your-host>{endpoint["path"]}"',
        '  -H "Authorization: Bearer <JWT_ACCESS_TOKEN>"',
    ]
    if endpoint["method"] in {"POST", "PUT", "PATCH"}:
        lines.append('  -H "Content-Type: application/json"')
        lines.append("  -d '{\"example\": \"value\"}'")
    return " \\\n".join(lines)


def _resolve_api_sections():
    api_sections = deepcopy(API_SECTIONS)
    for section in api_sections:
        for item in section["items"]:
            if item.get("href"):
                continue
            endpoint_key = item.get("key")
            if not endpoint_key:
                continue
            try:
                item["href"] = reverse(
                    "rail-endpoint-guide",
                    kwargs={"endpoint_key": endpoint_key},
                )
                item["guide_only"] = True
            except NoReverseMatch:
                item["href"] = None
    return api_sections


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

        # Eliminate redundant URLs between quick links and dashboard cards.
        dashboard_hrefs = {item.get("href") for item in SYSTEM_DASHBOARDS if item.get("href")}
        seen_hrefs = set()
        deduped_quick_links = []
        for link in QUICK_LINKS:
            href = link.get("href")
            if not href:
                continue
            if href in dashboard_hrefs:
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            deduped_quick_links.append(link)

        context["quick_links"] = deduped_quick_links
        context["system_dashboards"] = SYSTEM_DASHBOARDS
        context["api_sections"] = _resolve_api_sections()
        return context


class EndpointGuideView(SuperuserRequiredTemplateView):
    """Superuser-only detail page for HTTP endpoint usage guidance."""

    template_name = "root/endpoint_guide.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        endpoint_key = kwargs.get("endpoint_key")
        endpoint = ENDPOINT_GUIDES.get(endpoint_key)
        if not endpoint:
            raise Http404("Endpoint guide not found.")

        endpoint_context = dict(endpoint)
        endpoint_context["sample_curl"] = _build_sample_curl(endpoint_context)
        endpoint_context["has_placeholders"] = "<" in endpoint_context["path"]
        endpoint_context["requires_body"] = endpoint_context["method"] in {
            "POST",
            "PUT",
            "PATCH",
        }

        context["endpoint"] = endpoint_context
        try:
            context["welcome_url"] = reverse("welcome")
        except NoReverseMatch:
            context["welcome_url"] = "/"
        return context


__all__ = ["EndpointGuideView", "SuperuserRequiredTemplateView", "WelcomeView"]

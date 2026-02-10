"""HTTP views for import template downloads."""

from __future__ import annotations

import csv
import io

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..excel.builder import OPENPYXL_AVAILABLE, render_excel

try:
    from ..auth.decorators import jwt_required
except ImportError:  # pragma: no cover
    jwt_required = None

from .services import require_import_access, resolve_template_descriptor


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(jwt_required if jwt_required else (lambda view: view), name="dispatch")
class ModelImportTemplateDownloadView(View):
    """Download a template file for model imports."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, app_label: str, model_name: str, *args, **kwargs) -> HttpResponse:
        user = getattr(request, "user", None)
        require_import_access(user, app_label=app_label, model_name=model_name)

        try:
            descriptor = resolve_template_descriptor(app_label=app_label, model_name=model_name)
        except LookupError:
            return JsonResponse(
                {"error": f"Model '{app_label}.{model_name}' not found."},
                status=404,
            )

        column_names: list[str] = []
        seen: set[str] = set()
        for column in descriptor["required_columns"] + descriptor["optional_columns"]:
            name = str(column["name"]).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            column_names.append(name)

        requested_format = str(request.GET.get("format", "csv")).strip().lower()
        if requested_format not in {"csv", "xlsx"}:
            return JsonResponse(
                {"error": "Unsupported format. Use 'csv' or 'xlsx'."},
                status=400,
            )

        file_base = f"{app_label}-{model_name.lower()}-import-template"
        if requested_format == "xlsx":
            if not OPENPYXL_AVAILABLE:
                return JsonResponse(
                    {"error": "XLSX export unavailable because openpyxl is not installed."},
                    status=500,
                )
            content = render_excel([column_names])
            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{file_base}.xlsx"'
            return response

        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(column_names)
        response = HttpResponse(
            buffer.getvalue().encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{file_base}.csv"'
        return response


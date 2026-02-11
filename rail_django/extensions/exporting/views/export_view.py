"""Export View

This module provides the main ExportView class for handling export requests.
"""

import json
import logging
from datetime import datetime
from typing import Any

from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..config import get_export_settings, sanitize_filename
from ..exceptions import ExportError
from ..exporter import ModelExporter
from ..security import (
    check_rate_limit,
    enforce_model_permissions,
    jwt_required_decorator,
    log_export_event,
)
from .helpers import (
    apply_export_template,
    enqueue_export_job,
    resolve_max_rows,
    stream_csv_response,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(jwt_required_decorator, name="dispatch")
class ExportView(View):
    """Django view for handling model export requests with JWT authentication."""

    def post(self, request):
        """Handle POST request for model export (JWT protected)."""
        if hasattr(request, "user") and request.user.is_authenticated:
            logger.info(
                f"Export request from user: {request.user.username} "
                f"(ID: {request.user.id})"
            )

        audit_details = {"action": "export"}

        try:
            export_settings = get_export_settings()
            rate_limit_response = check_rate_limit(request, export_settings)
            if rate_limit_response is not None:
                log_export_event(
                    request, success=False,
                    error_message="Rate limit exceeded", details=audit_details,
                )
                return rate_limit_response

            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                log_export_event(
                    request, success=False,
                    error_message="Invalid JSON payload", details=audit_details,
                )
                return JsonResponse({"error": "Invalid JSON payload"}, status=400)

            if not isinstance(data, dict):
                log_export_event(
                    request, success=False,
                    error_message="Payload must be an object", details=audit_details,
                )
                return JsonResponse({"error": "Payload must be an object"}, status=400)

            template_name = data.get("template")
            if template_name:
                resolved = apply_export_template(
                    request, str(template_name), data, export_settings
                )
                if isinstance(resolved, JsonResponse):
                    log_export_event(
                        request, success=False,
                        error_message="Template not permitted", details=audit_details,
                    )
                    return resolved
                data = resolved
                audit_details["template"] = str(template_name)

            # Validate required parameters
            for field in ["app_name", "model_name", "file_extension", "fields"]:
                if field not in data:
                    log_export_event(
                        request, success=False,
                        error_message=f"Missing required field: {field}",
                        details=audit_details,
                    )
                    return JsonResponse(
                        {"error": f"Missing required field: {field}"}, status=400
                    )

            app_name = data["app_name"]
            model_name = data["model_name"]
            file_extension = str(data["file_extension"]).lower()
            fields = data["fields"]
            group_by = data.get("group_by")
            audit_details.update({
                "app_name": app_name,
                "model_name": model_name,
                "file_extension": file_extension,
            })

            if file_extension in ["excel", "xlsx"]:
                file_extension = "xlsx"
            if file_extension not in ["xlsx", "csv"]:
                log_export_event(
                    request, success=False,
                    error_message='file_extension must be "xlsx" or "csv"',
                    details=audit_details,
                )
                return JsonResponse(
                    {"error": 'file_extension must be "xlsx" or "csv"'}, status=400
                )
            if group_by is not None and file_extension != "xlsx":
                log_export_event(
                    request, success=False,
                    error_message="group_by is only supported for xlsx exports",
                    details=audit_details,
                )
                return JsonResponse(
                    {"error": "group_by is only supported for xlsx exports"},
                    status=400,
                )

            if not isinstance(fields, list) or not fields:
                log_export_event(
                    request, success=False,
                    error_message="fields must be a non-empty list",
                    details=audit_details,
                )
                return JsonResponse(
                    {"error": "fields must be a non-empty list"}, status=400
                )

            # Validate field configurations
            for i, field_config in enumerate(fields):
                if isinstance(field_config, str):
                    continue
                elif isinstance(field_config, dict):
                    if "accessor" not in field_config:
                        log_export_event(
                            request, success=False,
                            error_message="Invalid field configuration",
                            details=audit_details,
                        )
                        return JsonResponse({
                            "error": f"Invalid field configuration at index {i}: "
                            "dict format must contain 'accessor' key"
                        }, status=400)
                else:
                    log_export_event(
                        request, success=False,
                        error_message="Invalid field configuration",
                        details=audit_details,
                    )
                    return JsonResponse({
                        "error": f"Invalid field configuration at index {i}"
                    }, status=400)

            # Optional parameters
            filename = data.get("filename")
            ordering = data.get("ordering")
            variables = data.get("variables") or {}
            presets = data.get("presets")
            schema_name = data.get("schema_name")
            distinct_on = data.get("distinct_on")
            group_by = data.get("group_by")
            async_request = bool(data.get("async", False))

            # Validate optional parameters
            validation_error = self._validate_optional_params(
                request, data, audit_details
            )
            if validation_error:
                return validation_error

            max_rows, max_rows_error = resolve_max_rows(data, export_settings)
            if max_rows_error is not None:
                log_export_event(
                    request, success=False,
                    error_message="Invalid max_rows", details=audit_details,
                )
                return max_rows_error

            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{model_name}_{timestamp}"
            filename = sanitize_filename(str(filename))

            exporter = ModelExporter(
                app_name, model_name,
                export_settings=export_settings, schema_name=schema_name,
            )
            permission_response = enforce_model_permissions(
                request, exporter.model, export_settings
            )
            if permission_response is not None:
                audit_details["model_label"] = exporter.model._meta.label
                log_export_event(
                    request, success=False,
                    error_message="Export not permitted", details=audit_details,
                )
                return permission_response

            parsed_fields = exporter.validate_fields(
                fields, user=getattr(request, "user", None),
                export_settings=export_settings,
            )
            group_by = exporter.validate_group_by(
                group_by,
                user=getattr(request, "user", None),
                export_settings=export_settings,
            )
            where_input = variables.get("where", variables) if variables else None
            exporter.validate_filter_input(where_input, export_settings=export_settings)
            ordering_value = exporter._normalize_ordering(ordering) or None

            async_settings = export_settings.get("async_jobs") or {}
            if async_request:
                if not async_settings.get("enable", False):
                    log_export_event(
                        request, success=False,
                        error_message="Async export is disabled", details=audit_details,
                    )
                    return JsonResponse(
                        {"error": "Async export is disabled"}, status=400
                    )
                job_response = enqueue_export_job(
                    request=request, exporter=exporter,
                    parsed_fields=parsed_fields, variables=variables,
                    ordering=ordering_value, max_rows=max_rows,
                    filename=filename, file_extension=file_extension,
                    group_by=group_by,
                    export_settings=export_settings,
                )
                log_export_event(request, success=True, details=audit_details)
                return job_response

            return self._generate_export_response(
                request, exporter, fields, parsed_fields, variables,
                ordering_value, max_rows, filename, file_extension,
                export_settings, presets, distinct_on, group_by, audit_details,
            )

        except ExportError as e:
            logger.error(f"Export error: {e}")
            message = str(e)
            status = 403 if "denied" in message.lower() else 400
            log_export_event(
                request, success=False, error_message=message, details=audit_details,
            )
            return JsonResponse({"error": message}, status=status)
        except Exception as e:
            logger.error(f"Unexpected error during export: {e}")
            log_export_event(
                request, success=False,
                error_message="Internal server error", details=audit_details,
            )
            return JsonResponse({"error": "Internal server error"}, status=500)

    def _validate_optional_params(
        self, request: Any, data: dict, audit_details: dict
    ) -> Any:
        """Validate optional request parameters."""
        variables = data.get("variables") or {}
        ordering = data.get("ordering")
        presets = data.get("presets")
        schema_name = data.get("schema_name")
        distinct_on = data.get("distinct_on")
        group_by = data.get("group_by")
        async_value = data.get("async", False)

        if async_value is not None and not isinstance(async_value, bool):
            log_export_event(
                request, success=False,
                error_message="async must be a boolean", details=audit_details,
            )
            return JsonResponse({"error": "async must be a boolean"}, status=400)

        if not isinstance(variables, dict):
            log_export_event(
                request, success=False,
                error_message="variables must be an object", details=audit_details,
            )
            return JsonResponse(
                {"error": "variables must be an object"}, status=400
            )

        if ordering is not None and not isinstance(ordering, (list, tuple, str)):
            log_export_event(
                request, success=False,
                error_message="ordering must be a string or list",
                details=audit_details,
            )
            return JsonResponse(
                {"error": "ordering must be a string or list"}, status=400
            )

        if presets is not None and not isinstance(presets, list):
            log_export_event(
                request, success=False,
                error_message="presets must be a list", details=audit_details,
            )
            return JsonResponse(
                {"error": "presets must be a list"}, status=400
            )

        if schema_name is not None and not isinstance(schema_name, str):
            log_export_event(
                request, success=False,
                error_message="schema_name must be a string", details=audit_details,
            )
            return JsonResponse(
                {"error": "schema_name must be a string"}, status=400
            )

        if distinct_on is not None and not isinstance(distinct_on, list):
            log_export_event(
                request, success=False,
                error_message="distinct_on must be a list", details=audit_details,
            )
            return JsonResponse(
                {"error": "distinct_on must be a list"}, status=400
            )
        if group_by is not None and not isinstance(group_by, str):
            log_export_event(
                request, success=False,
                error_message="group_by must be a string", details=audit_details,
            )
            return JsonResponse({"error": "group_by must be a string"}, status=400)

        return None

    def _generate_export_response(
        self, request, exporter, fields, parsed_fields, variables,
        ordering_value, max_rows, filename, file_extension,
        export_settings, presets, distinct_on, group_by, audit_details,
    ):
        """Generate the export response."""
        if file_extension == "xlsx":
            content = exporter.export_to_excel(
                fields, variables, ordering_value,
                max_rows=max_rows, parsed_fields=parsed_fields,
                presets=presets, distinct_on=distinct_on, group_by=group_by,
            )
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            file_ext = "xlsx"
        else:
            if export_settings.get("enforce_streaming_csv", True) or \
               export_settings.get("stream_csv", True):
                audit_details["stream_csv"] = True
                log_export_event(request, success=True, details=audit_details)
                return stream_csv_response(
                    exporter=exporter, parsed_fields=parsed_fields,
                    variables=variables, ordering=ordering_value,
                    max_rows=max_rows, filename=filename,
                    chunk_size=int(export_settings.get("csv_chunk_size", 1000)),
                    presets=presets, distinct_on=distinct_on,
                )
            content = exporter.export_to_csv(
                fields, variables, ordering_value,
                max_rows=max_rows, parsed_fields=parsed_fields,
                presets=presets, distinct_on=distinct_on,
            )
            content_type = "text/csv; charset=utf-8"
            file_ext = "csv"

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{filename}.{file_ext}"'
        )
        response["Content-Length"] = len(content)

        logger.info(
            f"Successfully exported {exporter.model_name} data to {file_extension}"
        )
        log_export_event(request, success=True, details=audit_details)
        return response

    def get(self, request):
        """Handle GET request - return API documentation."""
        if hasattr(request, "user") and request.user.is_authenticated:
            logger.info(
                f"Export API documentation request from: {request.user.username}"
            )

        documentation = {
            "endpoint": "/export",
            "method": "POST",
            "authentication": "JWT token required",
            "required_parameters": {
                "app_name": "string - Django app name",
                "model_name": "string - Model name",
                "file_extension": 'string - "xlsx" or "csv"',
                "fields": "array - Field configurations",
            },
            "optional_parameters": {
                "filename": "string - Custom filename",
                "ordering": "array - Ordering expressions",
                "variables": "object - Filter parameters",
                "group_by": "string - Group rows by field (xlsx only)",
                "max_rows": "integer - Row limit",
                "template": "string - Export template name",
                "async": "boolean - Async export",
            },
            "async_endpoints": {
                "status": "GET /api/v1/export/jobs/<job_id>/",
                "download": "GET /api/v1/export/jobs/<job_id>/download/",
            },
        }

        return JsonResponse(documentation, json_dumps_params={"indent": 2})

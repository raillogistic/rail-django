"""Export View Helpers

This module provides helper functions and utilities for the export view.
"""

import csv
import io
import json
import uuid
from datetime import timedelta
from typing import Any, List, Optional, Union

from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone

from ..config import (
    get_export_settings,
    get_export_templates,
    sanitize_filename,
)
from ..exporter import ModelExporter
from ..jobs import (
    export_job_task,
    set_export_job_payload,
    set_export_job,
    start_export_job_thread,
    update_export_job,
)
from ..security import check_template_access


def resolve_max_rows(
    data: dict[str, Any], export_settings: dict[str, Any]
) -> tuple[Optional[int], Optional[JsonResponse]]:
    """Resolve max rows with request override and config cap.

    Args:
        data: Request data dictionary.
        export_settings: Export configuration.

    Returns:
        Tuple of (resolved max_rows, error response if any).
    """
    config_max_rows = export_settings.get("max_rows", None)
    requested_max = data.get("max_rows", data.get("limit"))

    if config_max_rows is not None:
        try:
            config_max_rows = int(config_max_rows)
        except (TypeError, ValueError):
            config_max_rows = None
    if config_max_rows is not None and config_max_rows <= 0:
        config_max_rows = None

    if requested_max is None:
        return config_max_rows, None

    try:
        requested_max = int(requested_max)
    except (TypeError, ValueError):
        return None, JsonResponse(
            {"error": "max_rows must be an integer"}, status=400
        )

    if requested_max <= 0:
        return config_max_rows, None

    if config_max_rows is None:
        return requested_max, None

    return min(requested_max, config_max_rows), None


def apply_export_template(
    request: Any,
    template_name: str,
    data: dict[str, Any],
    export_settings: dict[str, Any],
) -> Union[dict[str, Any], JsonResponse]:
    """Merge a named export template into the request payload.

    Args:
        request: Django request object.
        template_name: Name of the template.
        data: Request data dictionary.
        export_settings: Export configuration.

    Returns:
        Merged data dictionary or JsonResponse if error.
    """
    templates = get_export_templates(export_settings)
    template = templates.get(template_name)
    if not template:
        return JsonResponse(
            {"error": "Export template not found", "template": template_name},
            status=404,
        )
    if not isinstance(template, dict):
        return JsonResponse(
            {"error": "Export template is invalid", "template": template_name},
            status=400,
        )
    if not check_template_access(request, template):
        return JsonResponse(
            {"error": "Export template not permitted", "template": template_name},
            status=403,
        )

    merged = dict(template)
    merged["template"] = template_name

    allow_overrides = template.get(
        "allow_overrides", ["variables", "filename", "max_rows", "ordering"]
    )
    if isinstance(allow_overrides, (list, tuple, set)):
        for key in allow_overrides:
            if key in data:
                if key == "variables" and isinstance(data[key], dict):
                    base_vars = dict(template.get("variables") or {})
                    base_vars.update(data[key])
                    merged[key] = base_vars
                else:
                    merged[key] = data[key]

    return merged


def enqueue_export_job(
    *,
    request: Any,
    exporter: ModelExporter,
    parsed_fields: list[dict[str, str]],
    variables: dict[str, Any],
    ordering: Optional[Union[str, list[str]]],
    max_rows: Optional[int],
    filename: str,
    file_extension: str,
    group_by: Optional[str],
    export_settings: dict[str, Any],
) -> JsonResponse:
    """Create and enqueue an export job for async processing.

    Args:
        request: Django request object.
        exporter: ModelExporter instance.
        parsed_fields: Validated field configurations.
        variables: Filter variables.
        ordering: Ordering configuration.
        max_rows: Maximum rows to export.
        filename: Output filename.
        file_extension: File extension (csv/xlsx).
        group_by: Optional grouping accessor (xlsx only).
        export_settings: Export configuration.

    Returns:
        JsonResponse with job details.
    """
    async_settings = export_settings.get("async_jobs") or {}
    backend = str(async_settings.get("backend", "thread")).lower()
    expires_seconds = int(async_settings.get("expires_seconds", 3600))

    job_id = str(uuid.uuid4())
    now = timezone.now()
    job = {
        "id": job_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=expires_seconds)).isoformat(),
        "owner_id": getattr(getattr(request, "user", None), "id", None),
        "file_extension": file_extension,
        "filename": filename,
        "processed_rows": 0,
        "total_rows": None,
    }

    payload = {
        "app_name": exporter.app_name,
        "model_name": exporter.model_name,
        "file_extension": file_extension,
        "filename": filename,
        "fields": parsed_fields,
        "parsed_fields": parsed_fields,
        "variables": variables,
        "ordering": ordering,
        "max_rows": max_rows,
        "group_by": group_by,
    }

    set_export_job(job_id, job, timeout=expires_seconds)
    set_export_job_payload(job_id, payload, timeout=expires_seconds)

    if backend == "thread":
        start_export_job_thread(job_id)
    elif backend == "celery":
        if not export_job_task:
            update_export_job(
                job_id,
                {"status": "failed", "error": "Celery is not available"},
                timeout=expires_seconds,
            )
            return JsonResponse(
                {"error": "Celery backend not available"}, status=500
            )
        export_job_task.delay(job_id)
    elif backend == "rq":
        try:
            import django_rq
        except Exception:
            update_export_job(
                job_id,
                {"status": "failed", "error": "RQ is not available"},
                timeout=expires_seconds,
            )
            return JsonResponse({"error": "RQ backend not available"}, status=500)
        from ..jobs import run_export_job

        queue_name = async_settings.get("queue", "default")
        queue = django_rq.get_queue(queue_name)
        queue.enqueue(run_export_job, job_id)
    else:
        update_export_job(
            job_id,
            {"status": "failed", "error": "Unknown async backend"},
            timeout=expires_seconds,
        )
        return JsonResponse({"error": "Unknown async backend"}, status=500)

    base_path = request.path.rstrip("/")
    status_path = f"{base_path}/jobs/{job_id}/"
    download_path = f"{base_path}/jobs/{job_id}/download/"
    return JsonResponse(
        {
            "job_id": job_id,
            "status": "pending",
            "status_url": request.build_absolute_uri(status_path),
            "download_url": request.build_absolute_uri(download_path),
            "expires_in": expires_seconds,
        },
        status=202,
    )


def stream_csv_response(
    *,
    exporter: ModelExporter,
    parsed_fields: list[dict[str, str]],
    variables: dict[str, Any],
    ordering: Optional[Union[str, list[str]]],
    max_rows: Optional[int],
    filename: str,
    chunk_size: int,
    presets: Optional[List[str]] = None,
    distinct_on: Optional[List[str]] = None,
) -> StreamingHttpResponse:
    """Stream a CSV export response.

    Args:
        exporter: ModelExporter instance.
        parsed_fields: Validated field configurations.
        variables: Filter variables.
        ordering: Ordering configuration.
        max_rows: Maximum rows to export.
        filename: Output filename.
        chunk_size: Rows per chunk.
        presets: Filter presets to apply.
        distinct_on: DISTINCT ON fields.

    Returns:
        StreamingHttpResponse with CSV data.
    """
    headers = [field["title"] for field in parsed_fields]
    accessors = [field["accessor"] for field in parsed_fields]

    if chunk_size <= 0:
        chunk_size = 1000

    queryset = exporter.get_queryset(
        variables,
        ordering,
        fields=accessors,
        max_rows=max_rows,
        presets=presets,
        skip_validation=True,
        distinct_on=distinct_on,
    ).iterator(chunk_size=chunk_size)

    def row_generator():
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for instance in queryset:
            row = [
                exporter.get_field_value(instance, accessor)
                for accessor in accessors
            ]
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    response = StreamingHttpResponse(
        row_generator(), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    return response

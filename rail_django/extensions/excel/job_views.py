"""
Excel async job Django views.

This module provides Django views for async Excel job status and download.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..async_job_views import ensure_job_access, get_job_or_404, handle_job_expiry
from .config import _url_prefix
from .jobs import (
    _cleanup_excel_job_files,
    _delete_excel_job,
    _get_excel_job,
    _job_access_allowed,
    _parse_iso_datetime,
    _sanitize_filename,
)

# Optional imports
try:
    from ..auth.decorators import jwt_required
except ImportError:
    jwt_required = None

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class ExcelTemplateJobStatusView(View):
    """Return status for async Excel jobs."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id: str) -> JsonResponse:
        """Get the status of an async Excel job."""
        job_id = str(job_id)
        job = get_job_or_404(
            job_id,
            _get_excel_job,
            not_found_message="Excel job not found",
        )
        handle_job_expiry(
            job,
            job_id,
            parse_expires=_parse_iso_datetime,
            cleanup_files=_cleanup_excel_job_files,
            delete_job=_delete_excel_job,
            expired_message="Excel job not found",
            expired_status=404,
            not_found_message="Excel job not found",
        )
        forbidden = ensure_job_access(
            request,
            job,
            access_allowed=_job_access_allowed,
            forbidden_message="Excel job not permitted",
        )
        if forbidden:
            return forbidden

        payload: Dict[str, Any] = {
            "job_id": job.get("id"),
            "status": job.get("status"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "completed_at": job.get("completed_at"),
            "expires_at": job.get("expires_at"),
        }
        if job.get("status") == "completed":
            download_path = f"/api/{_url_prefix().rstrip('/')}/jobs/{job_id}/download/"
            payload["download_url"] = request.build_absolute_uri(download_path)

        return JsonResponse(payload)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class ExcelTemplateJobDownloadView(View):
    """Download completed Excel job files."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id: str) -> HttpResponse:
        """Download a completed async Excel file."""
        job_id = str(job_id)
        job = get_job_or_404(
            job_id,
            _get_excel_job,
            not_found_message="Excel job not found",
        )
        handle_job_expiry(
            job,
            job_id,
            parse_expires=_parse_iso_datetime,
            cleanup_files=_cleanup_excel_job_files,
            delete_job=_delete_excel_job,
            expired_message="Excel job not found",
            expired_status=404,
            not_found_message="Excel job not found",
        )
        forbidden = ensure_job_access(
            request,
            job,
            access_allowed=_job_access_allowed,
            forbidden_message="Excel job not permitted",
        )
        if forbidden:
            return forbidden

        if job.get("status") != "completed":
            return JsonResponse({"error": "Excel job not completed"}, status=409)

        file_path = job.get("file_path")
        if not file_path or not Path(str(file_path)).exists():
            return JsonResponse({"error": "Excel job file missing"}, status=410)

        filename = _sanitize_filename(str(job.get("filename") or "export"))
        response = FileResponse(
            open(file_path, "rb"),
            content_type=job.get(
                "content_type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


__all__ = [
    "ExcelTemplateJobStatusView",
    "ExcelTemplateJobDownloadView",
]

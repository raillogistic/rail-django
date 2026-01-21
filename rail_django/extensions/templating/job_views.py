"""
Async job views for PDF templating.

This module provides Django views for managing async PDF job status
and file downloads.
"""

import logging
from pathlib import Path
from typing import Any

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .config import _url_prefix
from .jobs import (
    _sanitize_filename,
    _get_pdf_job,
    _delete_pdf_job,
    _cleanup_pdf_job_files,
    _parse_iso_datetime,
    _job_access_allowed,
)

logger = logging.getLogger(__name__)

# Optional JWT protection (mirrors export endpoints)
try:
    from .auth_decorators import jwt_required
except ImportError:
    try:
        from ..auth_decorators import jwt_required
    except ImportError:
        jwt_required = None


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class PdfTemplateJobStatusView(View):
    """Return status for async PDF jobs."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id: str) -> JsonResponse:
        job = _get_pdf_job(str(job_id))
        if not job:
            raise Http404("PDF job not found")

        expires_at = _parse_iso_datetime(job.get("expires_at"))
        if expires_at and expires_at <= timezone.now():
            _cleanup_pdf_job_files(job)
            _delete_pdf_job(str(job_id))
            raise Http404("PDF job not found")

        if not _job_access_allowed(request, job):
            return JsonResponse({"error": "PDF job not permitted"}, status=403)

        payload = {
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
class PdfTemplateJobDownloadView(View):
    """Download completed PDF job files."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id: str) -> HttpResponse:
        job = _get_pdf_job(str(job_id))
        if not job:
            raise Http404("PDF job not found")

        expires_at = _parse_iso_datetime(job.get("expires_at"))
        if expires_at and expires_at <= timezone.now():
            _cleanup_pdf_job_files(job)
            _delete_pdf_job(str(job_id))
            raise Http404("PDF job not found")

        if not _job_access_allowed(request, job):
            return JsonResponse({"error": "PDF job not permitted"}, status=403)

        if job.get("status") != "completed":
            return JsonResponse({"error": "PDF job not completed"}, status=409)

        file_path = job.get("file_path")
        if not file_path or not Path(str(file_path)).exists():
            return JsonResponse({"error": "PDF job file missing"}, status=410)

        filename = _sanitize_filename(str(job.get("filename") or "document"))
        response = FileResponse(
            open(file_path, "rb"),
            content_type=job.get("content_type", "application/pdf"),
        )
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

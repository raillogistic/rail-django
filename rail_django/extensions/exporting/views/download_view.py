"""Export Job Download View

This module provides the ExportJobDownloadView for downloading completed export files.
"""

from pathlib import Path

from django.http import FileResponse, Http404, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from ..config import sanitize_filename
from ..jobs import (
    cleanup_export_job_files,
    delete_export_job,
    get_export_job,
    parse_iso_datetime,
)
from ..security import job_access_allowed, jwt_required_decorator


@method_decorator(jwt_required_decorator, name="dispatch")
class ExportJobDownloadView(View):
    """Download completed export job files.

    Serves the generated export file (CSV or Excel) for completed async jobs.

    Authentication:
        Requires JWT token: Authorization: Bearer <token>

    Access Control:
        Users can only download their own jobs, unless they are superusers.

    Error Responses:
        - 403: User not authorized to access this job
        - 404: Job not found or file not found
        - 409: Job not yet completed
        - 410: Job has expired
    """

    def get(self, request, job_id):
        """Download the export file for a completed job.

        Args:
            request: Django request object.
            job_id: UUID of the export job.

        Returns:
            FileResponse with the export file.

        Raises:
            Http404: If job or file is not found.
        """
        job_id = str(job_id)
        job = get_export_job(job_id)
        if not job:
            raise Http404("Export job not found")
        if not job_access_allowed(request, job):
            return JsonResponse({"error": "Export job not permitted"}, status=403)

        expires_at = parse_iso_datetime(job.get("expires_at"))
        if expires_at and timezone.now() > expires_at:
            cleanup_export_job_files(job)
            delete_export_job(job_id)
            return JsonResponse({"error": "Export job expired"}, status=410)

        if job.get("status") != "completed":
            return JsonResponse({"error": "Export job not completed"}, status=409)

        file_path = job.get("file_path")
        if not file_path or not Path(file_path).exists():
            raise Http404("Export file not found")

        filename = sanitize_filename(str(job.get("filename") or "export"))
        extension = job.get("file_extension") or "csv"
        response = FileResponse(
            open(file_path, "rb"),
            content_type=job.get("content_type", "application/octet-stream"),
            as_attachment=True,
            filename=f"{filename}.{extension}",
        )
        return response

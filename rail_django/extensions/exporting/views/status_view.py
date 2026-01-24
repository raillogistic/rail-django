"""Export Job Status View

This module provides the ExportJobStatusView for checking async export job status.
"""

from django.http import Http404, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from ...async_job_views import ensure_job_access, get_job_or_404, handle_job_expiry
from ..jobs import (
    cleanup_export_job_files,
    delete_export_job,
    get_export_job,
    parse_iso_datetime,
)
from ..security import job_access_allowed, jwt_required_decorator


@method_decorator(jwt_required_decorator, name="dispatch")
class ExportJobStatusView(View):
    """Return export job status details.

    Provides information about an async export job including:
    - Current status (pending, running, completed, failed)
    - Progress information (processed_rows, total_rows)
    - Timestamps (created_at, completed_at, expires_at)
    - Error message if failed
    - Download URL if completed

    Authentication:
        Requires JWT token: Authorization: Bearer <token>

    Access Control:
        Users can only access their own jobs, unless they are superusers.
    """

    def get(self, request, job_id):
        """Get status of an export job.

        Args:
            request: Django request object.
            job_id: UUID of the export job.

        Returns:
            JsonResponse with job status information.

        Raises:
            Http404: If job is not found.
        """
        job_id = str(job_id)
        job = get_job_or_404(
            job_id,
            get_export_job,
            not_found_message="Export job not found",
        )
        forbidden = ensure_job_access(
            request,
            job,
            access_allowed=job_access_allowed,
            forbidden_message="Export job not permitted",
        )
        if forbidden:
            return forbidden
        expired = handle_job_expiry(
            job,
            job_id,
            parse_expires=parse_iso_datetime,
            cleanup_files=cleanup_export_job_files,
            delete_job=delete_export_job,
            expired_message="Export job expired",
            expired_status=410,
        )
        if expired:
            return expired

        base_path = request.path.rstrip("/")
        download_path = f"{base_path}/download/"
        response = {
            "job_id": job_id,
            "status": job.get("status"),
            "processed_rows": job.get("processed_rows"),
            "total_rows": job.get("total_rows"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "completed_at": job.get("completed_at"),
            "expires_at": job.get("expires_at"),
        }
        if job.get("status") == "completed":
            response["download_url"] = request.build_absolute_uri(download_path)
        return JsonResponse(response)

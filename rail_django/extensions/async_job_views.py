"""
Shared helpers for async job status/download views.
"""

from typing import Any, Callable, Optional

from django.http import Http404, JsonResponse
from django.utils import timezone


def get_job_or_404(
    job_id: str,
    get_job: Callable[[str], Optional[dict[str, Any]]],
    *,
    not_found_message: str,
) -> dict[str, Any]:
    """Fetch a job or raise Http404."""
    job = get_job(job_id)
    if not job:
        raise Http404(not_found_message)
    return job


def handle_job_expiry(
    job: dict[str, Any],
    job_id: str,
    *,
    parse_expires: Callable[[Optional[str]], Any],
    cleanup_files: Callable[[dict[str, Any]], None],
    delete_job: Callable[[str], None],
    expired_message: str,
    expired_status: int,
    not_found_message: Optional[str] = None,
) -> Optional[JsonResponse]:
    """Handle expired jobs with cleanup and a response or 404."""
    expires_at = parse_expires(job.get("expires_at"))
    if expires_at and expires_at <= timezone.now():
        cleanup_files(job)
        delete_job(job_id)
        if expired_status == 404:
            raise Http404(not_found_message or "Job not found")
        return JsonResponse({"error": expired_message}, status=expired_status)
    return None


def ensure_job_access(
    request: Any,
    job: dict[str, Any],
    *,
    access_allowed: Callable[[Any, dict[str, Any]], bool],
    forbidden_message: str,
) -> Optional[JsonResponse]:
    """Return a forbidden response if the job access is denied."""
    if not access_allowed(request, job):
        return JsonResponse({"error": forbidden_message}, status=403)
    return None


__all__ = ["ensure_job_access", "get_job_or_404", "handle_job_expiry"]

"""Export Job Management

This module provides job management, cache utilities, and async export execution
for the exporting package.
"""

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from django.utils import timezone

from ..async_jobs import JobCache, build_storage_dir, parse_iso_datetime as parse_iso_datetime_util
from .config import get_export_settings

logger = logging.getLogger(__name__)

_EXPORT_JOB_CACHE = JobCache("rail:export_job", "rail:export_job_payload")


def export_job_cache_key(job_id: str) -> str:
    """Generate cache key for export job metadata.

    Args:
        job_id: Unique job identifier.

    Returns:
        Cache key string.
    """
    return _EXPORT_JOB_CACHE.job_key(job_id)


def export_job_payload_key(job_id: str) -> str:
    """Generate cache key for export job payload.

    Args:
        job_id: Unique job identifier.

    Returns:
        Cache key string.
    """
    return _EXPORT_JOB_CACHE.payload_key(job_id)


def get_export_job_payload(job_id: str) -> Optional[dict[str, Any]]:
    """Retrieve export job payload from cache."""
    return _EXPORT_JOB_CACHE.get_payload(job_id)


def set_export_job_payload(
    job_id: str, payload: dict[str, Any], *, timeout: int
) -> None:
    """Store export job payload in cache."""
    _EXPORT_JOB_CACHE.set_payload(job_id, payload, timeout=timeout)


def get_export_storage_dir(export_settings: dict[str, Any]) -> Path:
    """Get the directory for storing export files.

    Checks async_jobs.storage_dir setting first, then MEDIA_ROOT,
    finally falls back to system temp directory.

    Args:
        export_settings: Export configuration dictionary.

    Returns:
        Path to the export storage directory (created if needed).
    """
    async_settings = export_settings.get("async_jobs") or {}
    return build_storage_dir(
        async_settings.get("storage_dir"),
        media_subdir="rail_exports",
        temp_subdir="rail_exports",
    )


def get_export_job(job_id: str) -> Optional[dict[str, Any]]:
    """Retrieve export job metadata from cache.

    Args:
        job_id: Unique job identifier.

    Returns:
        Job metadata dictionary, or None if not found.
    """
    return _EXPORT_JOB_CACHE.get_job(job_id)


def set_export_job(job_id: str, job: dict[str, Any], *, timeout: int) -> None:
    """Store export job metadata in cache.

    Args:
        job_id: Unique job identifier.
        job: Job metadata dictionary.
        timeout: Cache timeout in seconds.
    """
    _EXPORT_JOB_CACHE.set_job(job_id, job, timeout=timeout)


def update_export_job(
    job_id: str, updates: dict[str, Any], *, timeout: int
) -> Optional[dict[str, Any]]:
    """Update export job metadata in cache.

    Args:
        job_id: Unique job identifier.
        updates: Dictionary of fields to update.
        timeout: Cache timeout in seconds.

    Returns:
        Updated job dictionary, or None if job not found.
    """
    return _EXPORT_JOB_CACHE.update_job(job_id, updates, timeout=timeout)


def delete_export_job(job_id: str) -> None:
    """Delete export job metadata and payload from cache.

    Args:
        job_id: Unique job identifier.
    """
    _EXPORT_JOB_CACHE.delete_job(job_id)


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string.

    Args:
        value: ISO 8601 datetime string, or None.

    Returns:
        Timezone-aware datetime object, or None if parsing fails.
    """
    return parse_iso_datetime_util(value, make_aware=True)


def cleanup_export_job_files(job: dict[str, Any]) -> None:
    """Clean up export job files from disk.

    Args:
        job: Job metadata dictionary containing file_path.
    """
    file_path = job.get("file_path")
    if not file_path:
        return
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
    except Exception:
        return


def run_export_job(job_id: str) -> None:
    """Execute an async export job and update cache state.

    This function is called by background workers (thread, Celery, RQ)
    to process an export job asynchronously.

    Args:
        job_id: Unique job identifier.
    """
    # Import here to avoid circular imports
    from .exporter import ModelExporter
    from .exceptions import ExportError

    job = get_export_job(job_id)
    if not job:
        return

    export_settings = get_export_settings()
    async_settings = export_settings.get("async_jobs") or {}
    timeout = int(async_settings.get("expires_seconds", 3600))
    payload = get_export_job_payload(job_id)
    if not payload:
        update_export_job(
            job_id,
            {"status": "failed", "error": "Missing job payload"},
            timeout=timeout,
        )
        return

    update_export_job(
        job_id,
        {"status": "running", "started_at": timezone.now().isoformat()},
        timeout=timeout,
    )

    processed_rows = 0
    total_rows = None

    def progress_callback(count: int) -> None:
        nonlocal processed_rows
        processed_rows = count
        update_export_job(
            job_id,
            {"processed_rows": processed_rows},
            timeout=timeout,
        )

    try:
        exporter = ModelExporter(
            payload["app_name"],
            payload["model_name"],
            export_settings=export_settings,
        )
        parsed_fields = payload.get("parsed_fields") or exporter.validate_fields(
            payload["fields"], export_settings=export_settings
        )
        ordering = payload.get("ordering")
        variables = payload.get("variables") or {}
        max_rows = payload.get("max_rows")
        group_by = payload.get("group_by")
        file_extension = payload["file_extension"]
        filename = payload["filename"]
        if file_extension not in {"csv", "xlsx"}:
            raise ExportError("Unsupported export format")
        if group_by and file_extension != "xlsx":
            raise ExportError("group_by is only supported for xlsx exports")

        storage_dir = get_export_storage_dir(export_settings)
        file_path = storage_dir / f"{job_id}.{file_extension}"

        if async_settings.get("track_progress", True):
            try:
                total_rows = exporter.get_queryset(
                    variables,
                    ordering,
                    fields=[field["accessor"] for field in parsed_fields],
                    max_rows=max_rows,
                ).count()
            except Exception:
                total_rows = None
            update_export_job(
                job_id,
                {"total_rows": total_rows},
                timeout=timeout,
            )

        if file_extension == "csv":
            with open(file_path, "w", encoding="utf-8", newline="") as handle:
                exporter.export_to_csv(
                    payload["fields"],
                    variables,
                    ordering,
                    max_rows=max_rows,
                    parsed_fields=parsed_fields,
                    output=handle,
                    progress_callback=progress_callback,
                )
            content_type = "text/csv; charset=utf-8"
        else:
            with open(file_path, "wb") as handle:
                exporter.export_to_excel(
                    payload["fields"],
                    variables,
                    ordering,
                    max_rows=max_rows,
                    parsed_fields=parsed_fields,
                    output=handle,
                    progress_callback=progress_callback,
                    group_by=group_by,
                )
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        if total_rows is not None and total_rows > processed_rows:
            processed_rows = total_rows
        update_export_job(
            job_id,
            {
                "status": "completed",
                "completed_at": timezone.now().isoformat(),
                "file_path": str(file_path),
                "content_type": content_type,
                "filename": filename,
                "processed_rows": processed_rows,
            },
            timeout=timeout,
        )

    except Exception as exc:
        update_export_job(
            job_id,
            {
                "status": "failed",
                "error": str(exc),
                "completed_at": timezone.now().isoformat(),
            },
            timeout=timeout,
        )


# Celery task registration (if Celery is available)
try:
    from celery import shared_task
except Exception:
    shared_task = None

if shared_task:

    @shared_task(name="rail_django.export_job")
    def export_job_task(job_id: str) -> None:
        """Celery task for running export jobs.

        Args:
            job_id: Unique job identifier.
        """
        run_export_job(job_id)
else:
    export_job_task = None


def start_export_job_thread(job_id: str) -> threading.Thread:
    """Start an export job in a background thread.

    Args:
        job_id: Unique job identifier.

    Returns:
        The started Thread object.
    """
    thread = threading.Thread(target=run_export_job, args=(job_id,), daemon=True)
    thread.start()
    return thread

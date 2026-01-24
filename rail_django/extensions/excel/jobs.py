"""
Async Excel job management.

This module provides functionality for generating Excel files asynchronously
using background threads, Celery, or RQ.
"""

import logging
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest
from django.utils import timezone

from .builder import render_excel
from .config import (
    ExcelTemplateDefinition,
    _excel_async,
    _excel_cache,
    _excel_expose_errors,
    _merge_dict,
    _url_prefix,
)
from ..async_jobs import (
    JobCache,
    build_job_request,
    build_storage_dir,
    hash_payload,
    job_access_allowed,
    parse_iso_datetime,
)
from ...utils.sanitization import sanitize_filename_basic

logger = logging.getLogger(__name__)

_EXCEL_JOB_CACHE = JobCache("rail:excel_job", "rail:excel_job_payload")


def _hash_payload(payload: Dict[str, Any]) -> str:
    """
    Create a hash of a payload for cache key generation.

    Args:
        payload: The payload to hash.

    Returns:
        The hash string.
    """
    return hash_payload(payload)


def _cache_settings_for_template(template_def: ExcelTemplateDefinition) -> Dict[str, Any]:
    """
    Get cache settings for a template, merging global and template-specific config.

    Args:
        template_def: The template definition.

    Returns:
        Merged cache settings.
    """
    from .config import EXCEL_CACHE_DEFAULTS

    overrides = {}
    if isinstance(template_def.config, dict):
        overrides = template_def.config.get("cache") or {}
    return _merge_dict(_excel_cache(), overrides)


def _build_excel_cache_key(
    template_def: ExcelTemplateDefinition,
    *,
    pk: Optional[str],
    user: Optional[Any],
    cache_settings: Dict[str, Any],
) -> Optional[str]:
    """
    Build a cache key for an Excel export.

    Args:
        template_def: The template definition.
        pk: The primary key.
        user: The user.
        cache_settings: Cache settings.

    Returns:
        The cache key or None if caching is disabled.
    """
    if not cache_settings.get("enable", False):
        return None

    payload: Dict[str, Any] = {"template": template_def.url_path, "pk": pk}
    if cache_settings.get("vary_on_user", True):
        payload["user"] = getattr(user, "id", None) or "anon"

    key_prefix = cache_settings.get("key_prefix", "rail:excel_cache")
    return f"{key_prefix}:{_hash_payload(payload)}"


def _excel_job_cache_key(job_id: str) -> str:
    """Get cache key for an async Excel job."""
    return _EXCEL_JOB_CACHE.job_key(job_id)


def _excel_job_payload_key(job_id: str) -> str:
    """Get cache key for an async Excel job payload."""
    return _EXCEL_JOB_CACHE.payload_key(job_id)


def _get_excel_storage_dir(async_settings: Dict[str, Any]) -> Path:
    """
    Get the storage directory for async Excel files.

    Args:
        async_settings: Async settings.

    Returns:
        The storage directory path.
    """
    return build_storage_dir(
        async_settings.get("storage_dir"),
        media_subdir="rail_excel",
        temp_subdir="rail_excel",
    )


def _get_excel_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get an async Excel job from cache."""
    return _EXCEL_JOB_CACHE.get_job(job_id)


def _set_excel_job(job_id: str, job: Dict[str, Any], *, timeout: int) -> None:
    """Set an async Excel job in cache."""
    _EXCEL_JOB_CACHE.set_job(job_id, job, timeout=timeout)


def _update_excel_job(
    job_id: str, updates: Dict[str, Any], *, timeout: int
) -> Optional[Dict[str, Any]]:
    """Update an async Excel job in cache."""
    return _EXCEL_JOB_CACHE.update_job(job_id, updates, timeout=timeout)


def _delete_excel_job(job_id: str) -> None:
    """Delete an async Excel job from cache."""
    _EXCEL_JOB_CACHE.delete_job(job_id)


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string."""
    return parse_iso_datetime(value)


def _job_access_allowed(request: Any, job: Dict[str, Any]) -> bool:
    """Check if the requesting user can access a job."""
    from .access import _resolve_request_user
    return job_access_allowed(request, job, resolve_user=_resolve_request_user)


def _notify_excel_job_webhook(
    job: Dict[str, Any], async_settings: Dict[str, Any]
) -> None:
    """Send a webhook notification for a completed Excel job."""
    webhook_url = async_settings.get("webhook_url")
    if not webhook_url:
        return
    try:
        import requests
    except Exception:
        logger.warning("requests is unavailable; cannot post Excel webhook")
        return
    headers = async_settings.get("webhook_headers") or {}
    timeout = int(async_settings.get("webhook_timeout_seconds", 10))
    try:
        requests.post(webhook_url, json=job, headers=headers, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Failed to notify Excel webhook: %s", exc)


def _build_job_request(owner_id: Optional[Any]) -> HttpRequest:
    """Build a mock request for async job processing."""
    return build_job_request(owner_id)


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe use in Content-Disposition header.

    Args:
        filename: The raw filename.

    Returns:
        The sanitized filename.
    """
    return sanitize_filename_basic(filename, default="export")


def _run_excel_job(job_id: str) -> None:
    """Run an async Excel generation job."""
    from .exporter import _get_excel_data, excel_template_registry

    job = _get_excel_job(job_id)
    if not job:
        return

    async_settings = _excel_async()
    timeout = int(async_settings.get("expires_seconds", 3600))
    payload = _EXCEL_JOB_CACHE.get_payload(job_id)
    if not payload:
        _update_excel_job(
            job_id, {"status": "failed", "error": "Missing job payload"}, timeout=timeout
        )
        return

    _update_excel_job(
        job_id,
        {"status": "running", "started_at": timezone.now().isoformat()},
        timeout=timeout,
    )

    template_path = payload.get("template_path")
    template_def = excel_template_registry.get(str(template_path))
    if not template_def:
        _update_excel_job(
            job_id, {"status": "failed", "error": "Template not found"}, timeout=timeout
        )
        return

    pk = payload.get("pk")
    instance: Optional[models.Model] = None
    if template_def.model:
        try:
            instance = template_def.model.objects.get(pk=pk)
        except (template_def.model.DoesNotExist, ValidationError, ValueError, TypeError):
            _update_excel_job(
                job_id,
                {"status": "failed", "error": "Instance not found"},
                timeout=timeout,
            )
            return

    request = _build_job_request(job.get("owner_id"))

    try:
        data = _get_excel_data(
            request, instance, template_def, pk=str(pk) if pk else None
        )
        excel_bytes = render_excel(data, config=template_def.config)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Async Excel job failed: %s", exc)
        _update_excel_job(
            job_id,
            {
                "status": "failed",
                "error": str(exc) if _excel_expose_errors() else "Excel render failed",
            },
            timeout=timeout,
        )
        _notify_excel_job_webhook(_get_excel_job(job_id) or job, async_settings)
        return

    storage_dir = _get_excel_storage_dir(async_settings)
    filename = payload.get("filename") or template_def.url_path.replace("/", "-")
    filename = _sanitize_filename(filename)
    file_path = storage_dir / f"{job_id}.xlsx"
    try:
        with open(file_path, "wb") as handle:
            handle.write(excel_bytes)
    except OSError as exc:
        _update_excel_job(
            job_id,
            {"status": "failed", "error": f"Failed to persist Excel: {exc}"},
            timeout=timeout,
        )
        _notify_excel_job_webhook(_get_excel_job(job_id) or job, async_settings)
        return

    _update_excel_job(
        job_id,
        {
            "status": "completed",
            "completed_at": timezone.now().isoformat(),
            "file_path": str(file_path),
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "filename": f"{filename}.xlsx",
        },
        timeout=timeout,
    )
    _notify_excel_job_webhook(_get_excel_job(job_id) or job, async_settings)


# Optional Celery support
try:
    from celery import shared_task
except Exception:  # pragma: no cover - optional dependency
    shared_task = None

if shared_task:

    @shared_task(name="rail_django.excel_job")
    def excel_job_task(job_id: str) -> None:
        """Celery task for async Excel generation."""
        _run_excel_job(job_id)

else:
    excel_job_task = None


def generate_excel_async(
    *,
    request: HttpRequest,
    template_def: ExcelTemplateDefinition,
    pk: Optional[str],
) -> Dict[str, Any]:
    """
    Generate an Excel file asynchronously.

    Args:
        request: The HTTP request.
        template_def: The template definition.
        pk: The primary key.

    Returns:
        Job information including job_id and status URLs.
    """
    from .access import _resolve_request_user

    async_settings = _excel_async()
    backend = str(async_settings.get("backend", "thread")).lower()
    expires_seconds = int(async_settings.get("expires_seconds", 3600))

    job_id = str(uuid.uuid4())
    now = timezone.now()
    owner = _resolve_request_user(request)
    job = {
        "id": job_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=expires_seconds)).isoformat(),
        "owner_id": getattr(owner, "id", None),
    }

    payload = {
        "template_path": template_def.url_path,
        "pk": pk,
        "filename": template_def.title,
    }

    _set_excel_job(job_id, job, timeout=expires_seconds)
    _EXCEL_JOB_CACHE.set_payload(job_id, payload, timeout=expires_seconds)

    if backend == "thread":
        thread = threading.Thread(target=_run_excel_job, args=(job_id,), daemon=True)
        thread.start()
    elif backend == "celery":
        if not excel_job_task:
            _update_excel_job(
                job_id,
                {"status": "failed", "error": "Celery is not available"},
                timeout=expires_seconds,
            )
            raise RuntimeError("Celery backend not available")
        excel_job_task.delay(job_id)
    elif backend == "rq":
        try:
            import django_rq
        except Exception as exc:
            _update_excel_job(
                job_id,
                {"status": "failed", "error": "RQ is not available"},
                timeout=expires_seconds,
            )
            raise RuntimeError("RQ backend not available") from exc
        queue_name = async_settings.get("queue", "default")
        queue = django_rq.get_queue(queue_name)
        queue.enqueue(_run_excel_job, job_id)
    else:
        _update_excel_job(
            job_id,
            {"status": "failed", "error": "Unknown async backend"},
            timeout=expires_seconds,
        )
        raise RuntimeError("Unknown async backend")

    status_path = f"/api/{_url_prefix().rstrip('/')}/jobs/{job_id}/"
    download_path = f"/api/{_url_prefix().rstrip('/')}/jobs/{job_id}/download/"
    return {
        "job_id": job_id,
        "status": "pending",
        "status_url": request.build_absolute_uri(status_path),
        "download_url": request.build_absolute_uri(download_path),
        "expires_in": expires_seconds,
    }


def _cleanup_excel_job_files(job: Dict[str, Any]) -> None:
    """Clean up files from an async Excel job."""
    file_path = job.get("file_path")
    if not file_path:
        return
    try:
        Path(str(file_path)).unlink(missing_ok=True)
    except Exception:
        return


__all__ = [
    # Cache helpers
    "_hash_payload",
    "_cache_settings_for_template",
    "_build_excel_cache_key",
    # Job cache keys
    "_excel_job_cache_key",
    "_excel_job_payload_key",
    # Storage
    "_get_excel_storage_dir",
    # Job CRUD
    "_get_excel_job",
    "_set_excel_job",
    "_update_excel_job",
    "_delete_excel_job",
    # Job utilities
    "_parse_iso_datetime",
    "_job_access_allowed",
    "_notify_excel_job_webhook",
    "_build_job_request",
    "_sanitize_filename",
    "_run_excel_job",
    "_cleanup_excel_job_files",
    # Celery task
    "excel_job_task",
    # Main async function
    "generate_excel_async",
]

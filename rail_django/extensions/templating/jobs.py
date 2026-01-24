"""
Async job management for PDF generation.

This module provides functions for managing asynchronous PDF generation jobs
including job creation, status tracking, and background processing.
"""

import logging
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest
from django.utils import timezone

from .config import (
    _merge_dict,
    _templating_async,
    _templating_cache,
    _templating_expose_errors,
    _url_prefix,
)
from .registry import template_registry, TemplateDefinition
from .access import _resolve_request_user, _build_template_context
from .rendering import render_pdf
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

_PDF_JOB_CACHE = JobCache("rail:pdf_job", "rail:pdf_job_payload")


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------


def _sanitize_filename(filename: str) -> str:
    return sanitize_filename_basic(filename, default="document")


# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------


def _hash_payload(payload: dict[str, Any]) -> str:
    return hash_payload(payload)


def _cache_settings_for_template(template_def: TemplateDefinition) -> dict[str, Any]:
    overrides = {}
    if isinstance(template_def.config, dict):
        overrides = template_def.config.get("cache") or {}
    return _merge_dict(_templating_cache(), overrides)


def _build_pdf_cache_key(
    template_def: TemplateDefinition,
    *,
    pk: Optional[str],
    user: Optional[Any],
    client_data: dict[str, Any],
    cache_settings: dict[str, Any],
) -> Optional[str]:
    if not cache_settings.get("enable", False):
        return None

    from .config import _templating_renderer_name

    payload: dict[str, Any] = {"template": template_def.url_path, "pk": pk}
    if cache_settings.get("vary_on_user", True):
        payload["user"] = getattr(user, "id", None) or "anon"
    if cache_settings.get("vary_on_client_data", True):
        payload["client_data"] = client_data or {}
    if cache_settings.get("vary_on_template_config", True):
        payload["config"] = template_def.config
    payload["renderer"] = template_def.config.get("renderer") or _templating_renderer_name()

    key_prefix = cache_settings.get("key_prefix", "rail:pdf_cache")
    return f"{key_prefix}:{_hash_payload(payload)}"


# ---------------------------------------------------------------------------
# Job cache functions
# ---------------------------------------------------------------------------


def _pdf_job_cache_key(job_id: str) -> str:
    return _PDF_JOB_CACHE.job_key(job_id)


def _pdf_job_payload_key(job_id: str) -> str:
    return _PDF_JOB_CACHE.payload_key(job_id)


def _get_pdf_storage_dir(async_settings: dict[str, Any]) -> Path:
    return build_storage_dir(
        async_settings.get("storage_dir"),
        media_subdir="rail_pdfs",
        temp_subdir="rail_pdfs",
    )


def _get_pdf_job(job_id: str) -> Optional[dict[str, Any]]:
    return _PDF_JOB_CACHE.get_job(job_id)


def _set_pdf_job(job_id: str, job: dict[str, Any], *, timeout: int) -> None:
    _PDF_JOB_CACHE.set_job(job_id, job, timeout=timeout)


def _update_pdf_job(
    job_id: str, updates: dict[str, Any], *, timeout: int
) -> Optional[dict[str, Any]]:
    return _PDF_JOB_CACHE.update_job(job_id, updates, timeout=timeout)


def _delete_pdf_job(job_id: str) -> None:
    _PDF_JOB_CACHE.delete_job(job_id)


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    return parse_iso_datetime(value)


def _job_access_allowed(request: Any, job: dict[str, Any]) -> bool:
    return job_access_allowed(request, job, resolve_user=_resolve_request_user)


def _notify_pdf_job_webhook(
    job: dict[str, Any], async_settings: dict[str, Any]
) -> None:
    webhook_url = async_settings.get("webhook_url")
    if not webhook_url:
        return
    try:
        import requests
    except Exception:
        logger.warning("requests is unavailable; cannot post PDF webhook")
        return
    headers = async_settings.get("webhook_headers") or {}
    timeout = int(async_settings.get("webhook_timeout_seconds", 10))
    try:
        requests.post(webhook_url, json=job, headers=headers, timeout=timeout)
    except Exception as exc:
        logger.warning("Failed to notify PDF webhook: %s", exc)


def _build_job_request(owner_id: Optional[Any]) -> HttpRequest:
    return build_job_request(owner_id)


def _cleanup_pdf_job_files(job: dict[str, Any]) -> None:
    file_path = job.get("file_path")
    if not file_path:
        return
    try:
        Path(str(file_path)).unlink(missing_ok=True)
    except Exception:
        return


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------


def _run_pdf_job(job_id: str) -> None:
    job = _get_pdf_job(job_id)
    if not job:
        return

    async_settings = _templating_async()
    timeout = int(async_settings.get("expires_seconds", 3600))
    payload = _PDF_JOB_CACHE.get_payload(job_id)
    if not payload:
        _update_pdf_job(
            job_id, {"status": "failed", "error": "Missing job payload"}, timeout=timeout
        )
        return

    _update_pdf_job(
        job_id,
        {"status": "running", "started_at": timezone.now().isoformat()},
        timeout=timeout,
    )

    template_path = payload.get("template_path")
    template_def = template_registry.get(str(template_path))
    if not template_def:
        _update_pdf_job(
            job_id, {"status": "failed", "error": "Template not found"}, timeout=timeout
        )
        return

    pk = payload.get("pk")
    instance: Optional[models.Model] = None
    if template_def.model:
        try:
            instance = template_def.model.objects.get(pk=pk)
        except (template_def.model.DoesNotExist, ValidationError, ValueError, TypeError):
            _update_pdf_job(
                job_id,
                {"status": "failed", "error": "Instance not found"},
                timeout=timeout,
            )
            return

    request = _build_job_request(job.get("owner_id"))
    client_data = payload.get("client_data") or {}
    setattr(request, "rail_template_client_data", client_data)
    context = _build_template_context(
        request, instance, template_def, client_data, pk=str(pk) if pk else None
    )

    try:
        pdf_bytes = render_pdf(
            template_def.content_template,
            context,
            config=template_def.config,
            header_template=template_def.header_template,
            footer_template=template_def.footer_template,
            base_url=payload.get("base_url"),
            renderer=payload.get("renderer"),
        )
    except Exception as exc:
        logger.exception("Async PDF job failed: %s", exc)
        _update_pdf_job(
            job_id,
            {"status": "failed", "error": str(exc) if _templating_expose_errors() else "PDF render failed"},
            timeout=timeout,
        )
        _notify_pdf_job_webhook(_get_pdf_job(job_id) or job, async_settings)
        return

    storage_dir = _get_pdf_storage_dir(async_settings)
    filename = payload.get("filename") or template_def.url_path.replace("/", "-")
    filename = _sanitize_filename(filename)
    file_path = storage_dir / f"{job_id}.pdf"
    try:
        with open(file_path, "wb") as handle:
            handle.write(pdf_bytes)
    except OSError as exc:
        _update_pdf_job(
            job_id,
            {"status": "failed", "error": f"Failed to persist PDF: {exc}"},
            timeout=timeout,
        )
        _notify_pdf_job_webhook(_get_pdf_job(job_id) or job, async_settings)
        return

    _update_pdf_job(
        job_id,
        {
            "status": "completed",
            "completed_at": timezone.now().isoformat(),
            "file_path": str(file_path),
            "content_type": "application/pdf",
            "filename": f"{filename}.pdf",
        },
        timeout=timeout,
    )
    _notify_pdf_job_webhook(_get_pdf_job(job_id) or job, async_settings)


# ---------------------------------------------------------------------------
# Celery task (optional)
# ---------------------------------------------------------------------------


try:
    from celery import shared_task
except Exception:
    shared_task = None

if shared_task:
    @shared_task(name="rail_django.pdf_job")
    def pdf_job_task(job_id: str) -> None:
        _run_pdf_job(job_id)
else:
    pdf_job_task = None


# ---------------------------------------------------------------------------
# Async job generation
# ---------------------------------------------------------------------------


def generate_pdf_async(
    *,
    request: HttpRequest,
    template_def: TemplateDefinition,
    pk: Optional[str],
    client_data: dict[str, Any],
    base_url: Optional[str] = None,
    renderer: Optional[str] = None,
) -> dict[str, Any]:
    """
    Schedule an asynchronous PDF generation job.

    Args:
        request: The HTTP request.
        template_def: Template definition to render.
        pk: Primary key of the model instance (if applicable).
        client_data: Client-provided data for the template context.
        base_url: Base URL for resolving relative URLs.
        renderer: Name of the renderer to use.

    Returns:
        Dict with job_id, status, status_url, download_url, and expires_in.

    Raises:
        RuntimeError: If the configured backend is not available.
    """
    async_settings = _templating_async()
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
        "client_data": client_data,
        "base_url": base_url,
        "renderer": renderer,
        "filename": template_def.title,
    }

    _set_pdf_job(job_id, job, timeout=expires_seconds)
    _PDF_JOB_CACHE.set_payload(job_id, payload, timeout=expires_seconds)

    if backend == "thread":
        thread = threading.Thread(target=_run_pdf_job, args=(job_id,), daemon=True)
        thread.start()
    elif backend == "celery":
        if not pdf_job_task:
            _update_pdf_job(
                job_id,
                {"status": "failed", "error": "Celery is not available"},
                timeout=expires_seconds,
            )
            raise RuntimeError("Celery backend not available")
        pdf_job_task.delay(job_id)
    elif backend == "rq":
        try:
            import django_rq
        except Exception as exc:
            _update_pdf_job(
                job_id,
                {"status": "failed", "error": "RQ is not available"},
                timeout=expires_seconds,
            )
            raise RuntimeError("RQ backend not available") from exc
        queue_name = async_settings.get("queue", "default")
        queue = django_rq.get_queue(queue_name)
        queue.enqueue(_run_pdf_job, job_id)
    else:
        _update_pdf_job(
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

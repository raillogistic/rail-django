"""
Shared helpers for async job workflows.

This module centralizes common cache, storage, and access utilities used by
Excel, PDF templating, and exporting async jobs.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone

from ..utils.datetime_utils import parse_iso_datetime as _parse_iso_datetime


def hash_payload(payload: dict[str, Any]) -> str:
    """Create a stable hash for a payload."""
    serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_storage_dir(
    storage_dir: Optional[Any],
    *,
    media_subdir: str,
    temp_subdir: str,
) -> Path:
    """Resolve and create a storage directory for async job artifacts."""
    if storage_dir:
        path = Path(str(storage_dir))
    elif getattr(settings, "MEDIA_ROOT", None):
        path = Path(settings.MEDIA_ROOT) / media_subdir
    else:
        path = Path(tempfile.gettempdir()) / temp_subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_iso_datetime(
    value: Optional[str], *, make_aware: bool = False
) -> Optional[datetime]:
    """Parse ISO 8601 strings with optional timezone awareness."""
    parsed = _parse_iso_datetime(value)
    if not parsed:
        return None
    if make_aware and timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


def job_access_allowed(
    request: Any,
    job: dict[str, Any],
    *,
    resolve_user: Optional[Callable[[Any], Any]] = None,
) -> bool:
    """Check if the requesting user can access a job payload."""
    user = resolve_user(request) if resolve_user else getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    owner_id = job.get("owner_id")
    return bool(owner_id and str(owner_id) == str(getattr(user, "id", "")))


def build_job_request(owner_id: Optional[Any]) -> HttpRequest:
    """Build a lightweight request object for background job execution."""
    request = HttpRequest()
    user = None
    if owner_id:
        try:
            user_model = get_user_model()
            user = user_model.objects.filter(pk=owner_id).first()
        except Exception:
            user = None
    request.user = user or AnonymousUser()
    return request


@dataclass(frozen=True)
class JobCache:
    """Cache helper for async job metadata and payloads."""

    job_prefix: str
    payload_prefix: str

    def job_key(self, job_id: str) -> str:
        return f"{self.job_prefix}:{job_id}"

    def payload_key(self, job_id: str) -> str:
        return f"{self.payload_prefix}:{job_id}"

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        return cache.get(self.job_key(job_id))

    def set_job(self, job_id: str, job: dict[str, Any], *, timeout: int) -> None:
        cache.set(self.job_key(job_id), job, timeout=timeout)

    def update_job(
        self, job_id: str, updates: dict[str, Any], *, timeout: int
    ) -> Optional[dict[str, Any]]:
        job = self.get_job(job_id)
        if not job:
            return None
        job.update(updates)
        self.set_job(job_id, job, timeout=timeout)
        return job

    def delete_job(self, job_id: str) -> None:
        cache.delete(self.job_key(job_id))
        cache.delete(self.payload_key(job_id))

    def get_payload(self, job_id: str) -> Optional[dict[str, Any]]:
        return cache.get(self.payload_key(job_id))

    def set_payload(self, job_id: str, payload: dict[str, Any], *, timeout: int) -> None:
        cache.set(self.payload_key(job_id), payload, timeout=timeout)


__all__ = [
    "JobCache",
    "build_job_request",
    "build_storage_dir",
    "hash_payload",
    "job_access_allowed",
    "parse_iso_datetime",
]

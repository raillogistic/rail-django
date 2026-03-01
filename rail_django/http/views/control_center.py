"""Superuser-only Control Center pages and APIs."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading
import zipfile
from uuid import UUID
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import close_old_connections
from django.db.models import Count
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.urls import NoReverseMatch, reverse
from django.utils.timezone import now
from django.views import View
from django.views.generic import TemplateView

from rail_django import __version__ as rail_django_version
from rail_django.extensions.audit.models import get_audit_event_model
from rail_django.extensions.excel.exporter import excel_template_registry
from rail_django.extensions.health import HealthChecker
from rail_django.extensions.importing.models import ImportBatch
from rail_django.extensions.reporting.models.export_job import ReportingExportJob
from rail_django.extensions.tasks.models import TaskExecution
from rail_django.extensions.templating.registry import template_registry
from rail_django.models import (
    MediaExportJob,
    MediaExportJobStatus,
    MetadataDeployVersionModel,
    SchemaRegistryModel,
)
from rail_django.security.config import SecurityConfig

logger = logging.getLogger(__name__)
_PROCESS_STARTED_AT = now()
_MEDIA_EXPORT_GLOBAL_CONCURRENCY = 2
_MEDIA_EXPORT_MAX_UNCOMPRESSED_DEFAULT = 2 * 1024 * 1024 * 1024
_MEDIA_EXPORT_RETENTION_HOURS_DEFAULT = 24
_MEDIA_EXPORT_POLL_INTERVAL_SECONDS_DEFAULT = 2


def _media_export_max_uncompressed_bytes() -> int:
    value = getattr(
        settings,
        "MEDIA_EXPORT_MAX_UNCOMPRESSED_BYTES",
        _MEDIA_EXPORT_MAX_UNCOMPRESSED_DEFAULT,
    )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return _MEDIA_EXPORT_MAX_UNCOMPRESSED_DEFAULT
    return max(1, parsed)


def _media_export_retention_hours() -> int:
    value = getattr(
        settings,
        "MEDIA_EXPORT_RETENTION_HOURS",
        _MEDIA_EXPORT_RETENTION_HOURS_DEFAULT,
    )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return _MEDIA_EXPORT_RETENTION_HOURS_DEFAULT
    return max(1, parsed)


def _media_export_poll_interval_seconds() -> int:
    value = getattr(
        settings,
        "MEDIA_EXPORT_POLL_INTERVAL_SECONDS",
        _MEDIA_EXPORT_POLL_INTERVAL_SECONDS_DEFAULT,
    )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return _MEDIA_EXPORT_POLL_INTERVAL_SECONDS_DEFAULT
    return max(1, parsed)


def _is_within_directory(base_dir: Path, candidate: Path) -> bool:
    base_dir = base_dir.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _resolve_media_root() -> Path:
    configured = str(getattr(settings, "MEDIA_ROOT", "") or "").strip()
    base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    if not configured:
        return (base_dir / "mediafiles").resolve()
    candidate = Path(configured)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def _resolve_media_export_dir() -> Path:
    return (_resolve_backup_dir() / "media_exports").resolve()


def _safe_value(loader: Callable[[], Any], default: Any) -> Any:
    try:
        return loader()
    except Exception as exc:  # pragma: no cover - defensive safety
        logger.debug("Control center loader failed: %s", exc)
        return default


def _mask(value: Any, *, head: int = 2, tail: int = 2) -> str:
    text = str(value or "")
    if len(text) <= head + tail:
        return "*" * len(text) if text else ""
    return f"{text[:head]}{'*' * max(3, len(text) - head - tail)}{text[-tail:]}"


def _human_size(num_bytes: int) -> str:
    size = float(max(0, num_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return "0B"


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")


def _resolve_log_dir() -> Path:
    log_dir = getattr(settings, "LOGGING_DIR", None)
    if log_dir:
        return Path(log_dir)
    base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    return base_dir / "logs"


def _resolve_backup_dir() -> Path:
    configured = os.environ.get("BACKUP_PATH", "").strip()
    base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    if not configured:
        return base_dir / "backups"
    candidate = Path(configured)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _default_database_config() -> dict[str, Any]:
    databases = getattr(settings, "DATABASES", {}) or {}
    return databases.get("default", {}) or {}


def _is_postgresql_database() -> bool:
    engine = str(_default_database_config().get("ENGINE", "")).lower()
    return "postgresql" in engine or "postgis" in engine


def _build_pg_dump_command(output_file: Path) -> tuple[list[str], dict[str, str]]:
    db = _default_database_config()
    db_name = db.get("NAME")
    if not db_name:
        raise RuntimeError("PostgreSQL database name is not configured.")

    command = [
        "pg_dump",
        "--format=custom",
        "--compress=9",
        "--no-owner",
        "--no-privileges",
        f"--file={output_file}",
        f"--dbname={db_name}",
    ]
    host = db.get("HOST")
    port = db.get("PORT")
    user = db.get("USER")
    if host:
        command.append(f"--host={host}")
    if port:
        command.append(f"--port={port}")
    if user:
        command.append(f"--username={user}")

    env = os.environ.copy()
    password = db.get("PASSWORD")
    if password:
        env["PGPASSWORD"] = str(password)
    return command, env


def _create_postgresql_backup_file() -> Path:
    backup_dir = _resolve_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_file = backup_dir / f"backup_{timestamp}.dump"
    command, env = _build_pg_dump_command(output_file)

    try:
        subprocess.run(command, env=env, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("pg_dump is not installed on the server.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or "").strip() or "pg_dump failed."
        raise RuntimeError(message) from exc

    if not output_file.exists() or output_file.stat().st_size == 0:
        output_file.unlink(missing_ok=True)
        raise RuntimeError("pg_dump produced an empty backup file.")

    return output_file


def _list_media_top_level_entries() -> tuple[list[dict[str, Any]], dict[str, Path]]:
    media_root = _resolve_media_root()
    if not media_root.exists() or not media_root.is_dir():
        return [], {}

    entries: list[dict[str, Any]] = []
    entry_map: dict[str, Path] = {}
    for candidate in sorted(media_root.iterdir(), key=lambda p: p.name.lower()):
        entry_id = candidate.name
        entry_type = "folder" if candidate.is_dir() else "file"
        size_bytes = 0
        if candidate.is_file():
            try:
                size_bytes = candidate.stat().st_size
            except OSError:
                size_bytes = 0
        else:
            try:
                size_bytes = _calculate_uncompressed_size(
                    [candidate], media_root, _media_export_max_uncompressed_bytes()
                )[0]
            except Exception:
                size_bytes = 0
        entries.append(
            {
                "id": entry_id,
                "name": candidate.name,
                "type": entry_type,
                "rel_path": candidate.name,
                "size_bytes": size_bytes,
                "selected_default": True,
            }
        )
        entry_map[entry_id] = candidate
    return entries, entry_map


def _iter_selected_media_files(
    selected_paths: list[Path], media_root: Path
):
    seen: set[str] = set()
    for selected_path in selected_paths:
        try:
            resolved_selected = selected_path.resolve()
        except OSError:
            continue
        if not _is_within_directory(media_root, resolved_selected):
            continue

        if resolved_selected.is_file():
            rel_path = resolved_selected.relative_to(media_root).as_posix()
            if rel_path in seen:
                continue
            seen.add(rel_path)
            try:
                size = resolved_selected.stat().st_size
            except OSError:
                size = 0
            yield (resolved_selected, rel_path, max(0, int(size)))
            continue

        if not resolved_selected.is_dir():
            continue

        for root, dirs, names in os.walk(resolved_selected, followlinks=False):
            root_path = Path(root)
            safe_dirs: list[str] = []
            for directory_name in dirs:
                dir_path = root_path / directory_name
                try:
                    if _is_within_directory(media_root, dir_path.resolve()):
                        safe_dirs.append(directory_name)
                except OSError:
                    continue
            dirs[:] = safe_dirs

            for file_name in names:
                file_path = root_path / file_name
                try:
                    resolved_file = file_path.resolve()
                except OSError:
                    continue
                if not _is_within_directory(media_root, resolved_file):
                    continue
                if not resolved_file.is_file():
                    continue
                rel_path = resolved_file.relative_to(media_root).as_posix()
                if rel_path in seen:
                    continue
                seen.add(rel_path)
                try:
                    size = resolved_file.stat().st_size
                except OSError:
                    size = 0
                yield (resolved_file, rel_path, max(0, int(size)))


def _calculate_uncompressed_size(
    selected_paths: list[Path], media_root: Path, max_bytes: int
) -> tuple[int, int]:
    total_bytes = 0
    total_files = 0
    for _path, _rel, size in _iter_selected_media_files(selected_paths, media_root):
        total_files += 1
        total_bytes += size
        if total_bytes > max_bytes:
            break
    return total_bytes, total_files


def _cleanup_expired_media_exports() -> None:
    export_dir = _resolve_media_export_dir()
    expired_jobs = MediaExportJob.objects.filter(
        expires_at__isnull=False, expires_at__lte=now()
    )
    for job in expired_jobs:
        archive_path = Path(job.archive_path) if job.archive_path else None
        if archive_path and archive_path.is_file() and _is_within_directory(
            export_dir, archive_path
        ):
            archive_path.unlink(missing_ok=True)
    expired_jobs.delete()


def _reconcile_stale_media_jobs() -> None:
    stale_before = now() - timedelta(hours=2)
    MediaExportJob.objects.filter(
        status__in=[MediaExportJobStatus.PENDING, MediaExportJobStatus.RUNNING],
        created_at__lt=stale_before,
    ).update(
        status=MediaExportJobStatus.FAILED,
        error_message="Job timed out before completion.",
        finished_at=now(),
        progress=0,
    )


def _run_media_export_job(job_id: UUID) -> None:
    close_old_connections()
    try:
        job = MediaExportJob.objects.filter(pk=job_id).first()
        if job is None:
            return
        media_root = _resolve_media_root()
        max_bytes = _media_export_max_uncompressed_bytes()
        retention_hours = _media_export_retention_hours()

        job.status = MediaExportJobStatus.RUNNING
        job.started_at = now()
        job.progress = 1
        job.message = "Preparing file list..."
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "started_at",
                "progress",
                "message",
                "error_message",
                "updated_at",
            ]
        )

        if not media_root.exists() or not media_root.is_dir():
            raise RuntimeError("MEDIA_ROOT does not exist on this server.")

        selected_paths: list[Path] = []
        for rel_path in job.selected_paths:
            candidate = (media_root / str(rel_path)).resolve()
            if not _is_within_directory(media_root, candidate):
                continue
            if candidate.exists():
                selected_paths.append(candidate)
        if not selected_paths:
            raise RuntimeError("No valid media entries were selected.")

        files = list(_iter_selected_media_files(selected_paths, media_root))
        if not files:
            raise RuntimeError("Selected entries do not contain readable files.")
        total_uncompressed = sum(item[2] for item in files)
        if total_uncompressed > max_bytes:
            max_display = _human_size(max_bytes)
            actual_display = _human_size(total_uncompressed)
            raise RuntimeError(
                f"Selected media exceeds limit ({actual_display} > {max_display})."
            )

        export_dir = _resolve_media_export_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_name = f"media_export_{timestamp}_{str(job.id)[:8]}.zip"
        final_archive = (export_dir / archive_name).resolve()
        if not _is_within_directory(export_dir, final_archive):
            raise RuntimeError("Invalid media export path.")

        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".zip",
            dir=export_dir,
            prefix=f".tmp_media_export_{str(job.id)[:8]}_",
            delete=False,
        ) as tmp_handle:
            tmp_path = Path(tmp_handle.name)

        written_bytes = 0
        try:
            with zipfile.ZipFile(
                tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for index, (file_path, rel_path, size) in enumerate(files, start=1):
                    archive.write(file_path, arcname=rel_path)
                    written_bytes += size
                    if index % 25 == 0 or index == len(files):
                        if total_uncompressed > 0:
                            progress = min(
                                95,
                                max(5, int((written_bytes / total_uncompressed) * 95)),
                            )
                        else:
                            progress = min(95, max(5, int((index / len(files)) * 95)))
                        MediaExportJob.objects.filter(pk=job.id).update(
                            progress=progress,
                            message=f"Compressed {index}/{len(files)} files...",
                        )
            tmp_path.replace(final_archive)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        archive_size = final_archive.stat().st_size if final_archive.exists() else 0
        if archive_size <= 0:
            final_archive.unlink(missing_ok=True)
            raise RuntimeError("Archive generation failed (empty ZIP output).")

        MediaExportJob.objects.filter(pk=job.id).update(
            status=MediaExportJobStatus.SUCCESS,
            progress=100,
            archive_name=archive_name,
            archive_path=str(final_archive),
            uncompressed_size_bytes=total_uncompressed,
            archive_size_bytes=archive_size,
            message=f"Archive ready ({len(files)} files).",
            finished_at=now(),
            expires_at=now() + timedelta(hours=retention_hours),
            error_message="",
        )
    except Exception as exc:
        logger.exception("Media export job %s failed: %s", job_id, exc)
        MediaExportJob.objects.filter(pk=job_id).update(
            status=MediaExportJobStatus.FAILED,
            progress=0,
            message="Media export failed.",
            error_message=str(exc),
            finished_at=now(),
        )
    finally:
        close_old_connections()


def _start_media_export_job(job_id: UUID) -> None:
    worker = threading.Thread(
        target=_run_media_export_job,
        args=(job_id,),
        daemon=True,
        name=f"media-export-{str(job_id)[:8]}",
    )
    worker.start()


def _tail_lines(
    path: Path,
    *,
    lines: int = 30,
    max_line_length: int = 320,
) -> list[str]:
    if not path.exists():
        return []
    try:
        requested = max(1, min(200, int(lines)))
        chunk_size = 4096
        data = b""
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            newline_count = 0
            while position > 0 and newline_count <= requested:
                read_size = chunk_size if position >= chunk_size else position
                position -= read_size
                handle.seek(position)
                chunk = handle.read(read_size)
                data = chunk + data
                newline_count = data.count(b"\n")

        decoded = data.decode("utf-8", errors="replace")
        rows = decoded.splitlines()[-requested:]
        trimmed = []
        for row in rows:
            if len(row) > max_line_length:
                trimmed.append(f"{row[:max_line_length]}... [truncated]")
            else:
                trimmed.append(row)
        return trimmed
    except Exception as exc:  # pragma: no cover - defensive safety
        logger.debug("Control center tail failed for %s: %s", path, exc)
        return []


def _build_health_payload() -> dict[str, Any]:
    checker = HealthChecker()
    report = checker.get_comprehensive_health_report()
    status = checker.summarize_report(report)
    components = report.get("components", {})
    schema = components.get("schema", {})
    databases = components.get("databases", [])
    caches = components.get("caches", [])

    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "Overall status", "value": status.get("overall_status", "unknown")},
            {"label": "Healthy", "value": status.get("healthy_components", 0)},
            {"label": "Degraded", "value": status.get("degraded_components", 0)},
            {"label": "Unhealthy", "value": status.get("unhealthy_components", 0)},
        ],
        "panels": [
            {
                "title": "Schema",
                "items": [
                    ("status", schema.get("status", "unknown")),
                    ("message", schema.get("message", "-")),
                    ("response_time_ms", schema.get("response_time_ms", "-")),
                ],
            },
            {
                "title": "System metrics",
                "items": sorted(
                    (report.get("system_metrics") or {}).items(),
                    key=lambda kv: kv[0],
                ),
            },
        ],
        "tables": [
            {
                "title": "Database components",
                "columns": ["component", "status", "message", "response_time_ms"],
                "rows": databases,
            },
            {
                "title": "Cache components",
                "columns": ["component", "status", "message", "response_time_ms"],
                "rows": caches,
            },
        ],
    }


def _build_overview_payload() -> dict[str, Any]:
    health_payload = _safe_value(_build_health_payload, {"summary": []})
    health_summary = {
        item["label"]: item["value"] for item in health_payload.get("summary", [])
    }
    active_since = _PROCESS_STARTED_AT
    uptime_seconds = int((now() - active_since).total_seconds())

    open_task_statuses = ["PENDING", "RUNNING", "RETRYING"]
    open_import_statuses = [
        "UPLOADED",
        "PARSED",
        "REVIEWING",
        "VALIDATED",
        "SIMULATED",
    ]

    task_total = _safe_value(lambda: TaskExecution.objects.count(), 0)
    tasks_inflight = _safe_value(
        lambda: TaskExecution.objects.filter(status__in=open_task_statuses).count(),
        0,
    )
    import_inflight = _safe_value(
        lambda: ImportBatch.objects.filter(status__in=open_import_statuses).count(),
        0,
    )
    def _runtime_schema_counts() -> tuple[int, int]:
        from rail_django.core.registry import schema_registry

        schema_registry.discover_schemas()
        enabled = len(schema_registry.get_schema_names(enabled_only=True))
        total = len(schema_registry.get_schema_names(enabled_only=False))
        return enabled, total

    schema_enabled, schema_total = _safe_value(_runtime_schema_counts, (0, 0))
    persisted_schema_total = _safe_value(lambda: SchemaRegistryModel.objects.count(), 0)
    persisted_schema_enabled = _safe_value(
        lambda: SchemaRegistryModel.objects.filter(enabled=True).count(),
        0,
    )
    deploy_version = _safe_value(
        lambda: MetadataDeployVersionModel.objects.filter(key="default")
        .values_list("version", flat=True)
        .first(),
        None,
    )

    AuditModel = get_audit_event_model()
    since_24h = now() - timedelta(hours=24)
    audit_24h = _safe_value(
        lambda: AuditModel.objects.filter(timestamp__gte=since_24h).count(),
        0,
    )

    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "Rail Django", "value": rail_django_version},
            {"label": "Uptime (seconds)", "value": uptime_seconds},
            {
                "label": "Health",
                "value": health_summary.get("Overall status", "unknown"),
            },
            {"label": "Schemas enabled", "value": f"{schema_enabled}/{schema_total}"},
            {"label": "Tasks in-flight", "value": tasks_inflight},
            {"label": "Task executions", "value": task_total},
            {"label": "Imports in-flight", "value": import_inflight},
            {"label": "Audit events (24h)", "value": audit_24h},
            {"label": "Deploy version", "value": deploy_version or "n/a"},
        ],
        "panels": [
            {
                "title": "Project runtime",
                "items": [
                    ("settings_module", os.environ.get("DJANGO_SETTINGS_MODULE", "")),
                    ("debug", getattr(settings, "DEBUG", False)),
                    ("timezone", str(getattr(settings, "TIME_ZONE", "UTC"))),
                    ("base_dir", str(getattr(settings, "BASE_DIR", ""))),
                    (
                        "persisted_schema_rows",
                        f"{persisted_schema_enabled}/{persisted_schema_total}",
                    ),
                ],
            },
            {
                "title": "Health snapshot",
                "items": health_payload.get("summary", []),
            },
        ],
        "tables": [
            {
                "title": "Recent tasks",
                "columns": ["id", "name", "status", "progress", "created_at"],
                "rows": _safe_value(
                    lambda: list(
                        TaskExecution.objects.values(
                            "id", "name", "status", "progress", "created_at"
                        )[:10]
                    ),
                    [],
                ),
            },
            {
                "title": "Recent import batches",
                "columns": ["id", "app_label", "model_name", "status", "created_at"],
                "rows": _safe_value(
                    lambda: list(
                        ImportBatch.objects.values(
                            "id",
                            "app_label",
                            "model_name",
                            "status",
                            "created_at",
                        )[:10]
                    ),
                    [],
                ),
            },
        ],
    }


def _build_security_payload() -> dict[str, Any]:
    cors_allowed = list(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
    csrf_allowed = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
    mfa = SecurityConfig.get_mfa_config()
    warnings = SecurityConfig.validate_security_settings()

    AuditModel = get_audit_event_model()
    since_24h = now() - timedelta(hours=24)
    failed_logins = _safe_value(
        lambda: AuditModel.objects.filter(
            timestamp__gte=since_24h, event_type__icontains="login.failure"
        ).count(),
        0,
    )
    rate_limit_events = _safe_value(
        lambda: AuditModel.objects.filter(
            timestamp__gte=since_24h, event_type__icontains="rate.limit"
        ).count(),
        0,
    )

    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "DEBUG", "value": bool(getattr(settings, "DEBUG", False))},
            {
                "label": "CORS allow all",
                "value": bool(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False)),
            },
            {
                "label": "CORS credentials",
                "value": bool(getattr(settings, "CORS_ALLOW_CREDENTIALS", True)),
            },
            {"label": "MFA enabled", "value": bool(mfa.get("enabled"))},
            {"label": "Failed logins (24h)", "value": failed_logins},
            {"label": "Rate limit events (24h)", "value": rate_limit_events},
        ],
        "panels": [
            {"title": "Allowed hosts", "items": [(host, "") for host in allowed_hosts]},
            {
                "title": "CORS and CSRF",
                "items": [
                    ("CORS_ALLOWED_ORIGINS", ", ".join(cors_allowed) or "none"),
                    ("CSRF_TRUSTED_ORIGINS", ", ".join(csrf_allowed) or "none"),
                ],
            },
            {
                "title": "MFA configuration",
                "items": [
                    ("enabled", mfa.get("enabled", False)),
                    ("issuer_name", mfa.get("issuer_name", "")),
                    ("backup_codes_count", mfa.get("backup_codes_count", 0)),
                    ("sms_provider", mfa.get("sms_provider") or "disabled"),
                    ("twilio_account_sid", _mask(mfa.get("twilio_account_sid", ""))),
                    ("twilio_from_number", _mask(mfa.get("twilio_from_number", ""))),
                ],
            },
        ],
        "tables": [
            {
                "title": "Security warnings",
                "columns": ["warning"],
                "rows": [{"warning": warning} for warning in warnings]
                or [{"warning": "No warnings"}],
            }
        ],
    }


def _build_logs_payload(request: HttpRequest) -> dict[str, Any]:
    log_dir = _resolve_log_dir()
    known_files = ["django.log", "security.log", "audit.log", "celery.log"]
    file_rows = []
    for filename in known_files:
        path = log_dir / filename
        exists = path.exists()
        file_rows.append(
            {
                "file": filename,
                "exists": exists,
                "size": _human_size(path.stat().st_size) if exists else "-",
                "modified_at": _iso(
                    datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                )
                if exists
                else "-",
            }
        )

    selected_file = request.GET.get("file", "django.log")
    if selected_file not in known_files:
        selected_file = "django.log"
    preview_lines = 20
    try:
        preview_lines = int(request.GET.get("preview_lines", preview_lines))
    except (TypeError, ValueError):
        preview_lines = 20
    preview_lines = max(5, min(80, preview_lines))
    tail_path = log_dir / selected_file
    tail = _tail_lines(tail_path, lines=preview_lines)

    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "Log directory", "value": str(log_dir)},
            {
                "label": "Available files",
                "value": sum(1 for item in file_rows if item["exists"]),
            },
            {"label": "Selected file", "value": selected_file},
            {"label": "Tail preview lines", "value": len(tail)},
        ],
        "panels": [
            {
                "title": "Tail preview",
                "items": [(line, "") for line in tail] or [("No content", "")],
            }
        ],
        "tables": [
            {
                "title": "Log files",
                "columns": ["file", "exists", "size", "modified_at"],
                "rows": file_rows,
            }
        ],
    }


def _build_jobs_payload() -> dict[str, Any]:
    task_status = _safe_value(
        lambda: list(TaskExecution.objects.values("status").annotate(count=Count("id"))),
        [],
    )
    export_status = _safe_value(
        lambda: list(
            ReportingExportJob.objects.values("status").annotate(count=Count("id"))
        ),
        [],
    )
    import_status = _safe_value(
        lambda: list(ImportBatch.objects.values("status").annotate(count=Count("id"))),
        [],
    )

    return {
        "generated_at": _iso(now()),
        "summary": [
            {
                "label": "Task executions",
                "value": _safe_value(lambda: TaskExecution.objects.count(), 0),
            },
            {
                "label": "Reporting exports",
                "value": _safe_value(lambda: ReportingExportJob.objects.count(), 0),
            },
            {
                "label": "Import batches",
                "value": _safe_value(lambda: ImportBatch.objects.count(), 0),
            },
        ],
        "panels": [
            {
                "title": "Task status",
                "items": [(item["status"], item["count"]) for item in task_status],
            },
            {
                "title": "Export status",
                "items": [(item["status"], item["count"]) for item in export_status],
            },
            {
                "title": "Import status",
                "items": [(item["status"], item["count"]) for item in import_status],
            },
        ],
        "tables": [
            {
                "title": "Recent task executions",
                "columns": [
                    "id",
                    "name",
                    "status",
                    "progress",
                    "created_at",
                    "updated_at",
                ],
                "rows": _safe_value(
                    lambda: list(
                        TaskExecution.objects.values(
                            "id",
                            "name",
                            "status",
                            "progress",
                            "created_at",
                            "updated_at",
                        )[:20]
                    ),
                    [],
                ),
            },
            {
                "title": "Recent reporting exports",
                "columns": [
                    "id",
                    "title",
                    "format",
                    "status",
                    "created_at",
                    "finished_at",
                ],
                "rows": _safe_value(
                    lambda: list(
                        ReportingExportJob.objects.values(
                            "id",
                            "title",
                            "format",
                            "status",
                            "created_at",
                            "finished_at",
                        )[:20]
                    ),
                    [],
                ),
            },
        ],
    }


def _build_data_ops_payload() -> dict[str, Any]:
    pdf_templates = []
    for url_path, template_def in sorted(template_registry.all().items()):
        pdf_templates.append(
            {
                "path": f"/api/v1/templates/{url_path}/<pk>/",
                "title": template_def.title,
                "source": template_def.source,
                "model": template_def.model._meta.label if template_def.model else "-",
            }
        )
    excel_templates = []
    for url_path, template_def in sorted(excel_template_registry.all().items()):
        excel_templates.append(
            {
                "path": f"/api/v1/excel/{url_path}/?pk=<id>",
                "title": template_def.title,
                "source": template_def.source,
                "model": template_def.model._meta.label if template_def.model else "-",
            }
        )

    recent_imports = _safe_value(
        lambda: list(
            ImportBatch.objects.values(
                "id",
                "app_label",
                "model_name",
                "status",
                "total_rows",
                "valid_rows",
                "invalid_rows",
                "created_at",
            )[:20]
        ),
        [],
    )

    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "PDF templates", "value": len(pdf_templates)},
            {"label": "Excel templates", "value": len(excel_templates)},
            {
                "label": "Import batches",
                "value": _safe_value(lambda: ImportBatch.objects.count(), 0),
            },
        ],
        "panels": [
            {
                "title": "Operational endpoints",
                "items": [
                    ("/api/v1/templates/catalog/", "PDF template catalog"),
                    ("/api/v1/excel/catalog/", "Excel template catalog"),
                    (
                        "/api/v1/import/templates/<app>/<model>/",
                        "Import template download",
                    ),
                ],
            }
        ],
        "tables": [
            {
                "title": "PDF templates",
                "columns": ["path", "title", "source", "model"],
                "rows": pdf_templates,
            },
            {
                "title": "Excel templates",
                "columns": ["path", "title", "source", "model"],
                "rows": excel_templates,
            },
            {
                "title": "Recent imports",
                "columns": [
                    "id",
                    "app_label",
                    "model_name",
                    "status",
                    "total_rows",
                    "valid_rows",
                    "invalid_rows",
                    "created_at",
                ],
                "rows": recent_imports,
            },
        ],
    }


def _build_backups_payload() -> dict[str, Any]:
    backup_dir = _resolve_backup_dir()
    media_root = _resolve_media_root()
    media_export_dir = _resolve_media_export_dir()
    _cleanup_expired_media_exports()
    _reconcile_stale_media_jobs()
    retention_days = os.environ.get("BACKUP_RETENTION_DAYS", "30")
    files = []
    allowed_patterns = (".sql", ".sql.gz", ".dump")
    if backup_dir.exists():
        for path in sorted(
            (
                candidate
                for candidate in backup_dir.glob("backup_*")
                if candidate.is_file()
                and candidate.name.startswith("backup_")
                and candidate.name.endswith(allowed_patterns)
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "size": _human_size(stat.st_size),
                    "modified_at": _iso(
                        datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    ),
                    "download": reverse(
                        "control_center_backup_download",
                        kwargs={"backup_name": path.name},
                    ),
                    "path": str(path),
                }
            )

    newest = files[0] if files else None
    recent_media_exports = []
    for row in MediaExportJob.objects.values(
        "id",
        "status",
        "progress",
        "archive_name",
        "archive_size_bytes",
        "uncompressed_size_bytes",
        "created_at",
        "finished_at",
        "error_message",
    )[:20]:
        archive_name = row.get("archive_name") or ""
        download_url = ""
        if (
            row.get("status") == MediaExportJobStatus.SUCCESS
            and archive_name.endswith(".zip")
        ):
            archive_path = (media_export_dir / archive_name).resolve()
            if archive_path.is_file() and _is_within_directory(
                media_export_dir, archive_path
            ):
                download_url = reverse(
                    "control_center_media_export_download",
                    kwargs={"archive_name": archive_name},
                )
        recent_media_exports.append(
            {
                "id": str(row["id"]),
                "status": row["status"],
                "progress": row["progress"],
                "archive_name": archive_name or "-",
                "archive_size": _human_size(int(row["archive_size_bytes"] or 0)),
                "uncompressed_size": _human_size(
                    int(row["uncompressed_size_bytes"] or 0)
                ),
                "created_at": _iso(row["created_at"]),
                "finished_at": _iso(row["finished_at"]),
                "error_message": row["error_message"] or "-",
                "download": download_url,
            }
        )

    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "Backup directory", "value": str(backup_dir)},
            {"label": "Retention days", "value": retention_days},
            {"label": "Total backup files", "value": len(files)},
            {
                "label": "Media root",
                "value": str(media_root),
            },
            {
                "label": "Media export jobs",
                "value": _safe_value(lambda: MediaExportJob.objects.count(), 0),
            },
            {
                "label": "Latest backup",
                "value": newest.get("name") if newest else "none",
            },
        ],
        "panels": [
            {
                "title": "Backup operations",
                "items": [
                    ("Script", "deploy/backup.sh"),
                    ("One-shot", "bash deploy/backup.sh"),
                    ("Automate", "Use cron/systemd on server host"),
                    (
                        "Media export max size",
                        _human_size(_media_export_max_uncompressed_bytes()),
                    ),
                    (
                        "Media export retention",
                        f"{_media_export_retention_hours()}h",
                    ),
                ],
            }
        ],
        "tables": [
            {
                "title": "Backup files",
                "columns": ["name", "size", "modified_at", "download", "path"],
                "rows": files,
            },
            {
                "title": "Recent media exports",
                "columns": [
                    "id",
                    "status",
                    "progress",
                    "archive_name",
                    "archive_size",
                    "uncompressed_size",
                    "created_at",
                    "finished_at",
                    "error_message",
                    "download",
                ],
                "rows": recent_media_exports,
            },
        ],
    }


def _build_integrations_payload() -> dict[str, Any]:
    db_default = (getattr(settings, "DATABASES", {}) or {}).get("default", {})
    cache_default = (getattr(settings, "CACHES", {}) or {}).get("default", {})
    external_services = (
        (getattr(settings, "RAIL_DJANGO_HEALTH", {}) or {}).get("external_services", [])
    )
    integrations = [
        {
            "name": "Database",
            "configured": bool(db_default),
            "details": f"{db_default.get('ENGINE', '')} @ {db_default.get('HOST', '')}:{db_default.get('PORT', '')}",
        },
        {
            "name": "Cache",
            "configured": bool(cache_default),
            "details": f"{cache_default.get('BACKEND', '')} :: {cache_default.get('LOCATION', '')}",
        },
        {
            "name": "Email",
            "configured": bool(getattr(settings, "EMAIL_HOST", None)),
            "details": f"{getattr(settings, 'EMAIL_BACKEND', '')} @ {getattr(settings, 'EMAIL_HOST', '')}",
        },
        {
            "name": "Audit webhook",
            "configured": bool(getattr(settings, "AUDIT_WEBHOOK_URL", None)),
            "details": _mask(getattr(settings, "AUDIT_WEBHOOK_URL", "")),
        },
        {
            "name": "Redis URL",
            "configured": bool(os.environ.get("REDIS_URL", "")),
            "details": _mask(os.environ.get("REDIS_URL", "")),
        },
    ]
    for service in external_services:
        integrations.append(
            {
                "name": str(service.get("name") or "external_service"),
                "configured": True,
                "details": str(service.get("url") or service.get("host") or service),
            }
        )

    configured_count = sum(1 for item in integrations if item["configured"])
    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "Configured integrations", "value": configured_count},
            {"label": "Total integrations", "value": len(integrations)},
        ],
        "panels": [
            {
                "title": "Environment-backed values",
                "items": [
                    ("EMAIL_HOST", getattr(settings, "EMAIL_HOST", "")),
                    ("DEFAULT_FROM_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
                    (
                        "AUDIT_WEBHOOK_URL",
                        _mask(getattr(settings, "AUDIT_WEBHOOK_URL", "")),
                    ),
                ],
            }
        ],
        "tables": [
            {
                "title": "Integration status",
                "columns": ["name", "configured", "details"],
                "rows": integrations,
            }
        ],
    }


def _build_audit_payload() -> dict[str, Any]:
    AuditModel = get_audit_event_model()
    since_24h = now() - timedelta(hours=24)
    total_24h = _safe_value(
        lambda: AuditModel.objects.filter(timestamp__gte=since_24h).count(),
        0,
    )
    high_24h = _safe_value(
        lambda: AuditModel.objects.filter(
            timestamp__gte=since_24h, severity__in=["error", "critical", "high"]
        ).count(),
        0,
    )
    event_type_stats = _safe_value(
        lambda: list(
            AuditModel.objects.filter(timestamp__gte=since_24h)
            .values("event_type")
            .annotate(count=Count("id"))
            .order_by("-count")[:20]
        ),
        [],
    )
    ip_stats = _safe_value(
        lambda: list(
            AuditModel.objects.filter(timestamp__gte=since_24h)
            .exclude(client_ip__isnull=True)
            .values("client_ip")
            .annotate(count=Count("id"))
            .order_by("-count")[:20]
        ),
        [],
    )
    recent_events = _safe_value(
        lambda: list(
            AuditModel.objects.values(
                "id",
                "timestamp",
                "event_type",
                "severity",
                "username",
                "client_ip",
                "request_path",
                "success",
            )[:30]
        ),
        [],
    )

    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "Events (24h)", "value": total_24h},
            {"label": "High severity (24h)", "value": high_24h},
            {
                "label": "Stored events",
                "value": _safe_value(lambda: AuditModel.objects.count(), 0),
            },
        ],
        "panels": [
            {
                "title": "Top event types (24h)",
                "items": [
                    (row["event_type"], row["count"]) for row in event_type_stats
                ],
            },
            {
                "title": "Top client IPs (24h)",
                "items": [(row["client_ip"], row["count"]) for row in ip_stats],
            },
        ],
        "tables": [
            {
                "title": "Recent events",
                "columns": [
                    "id",
                    "timestamp",
                    "event_type",
                    "severity",
                    "username",
                    "client_ip",
                    "request_path",
                    "success",
                ],
                "rows": recent_events,
            }
        ],
    }


def _build_settings_payload() -> dict[str, Any]:
    db_default = (getattr(settings, "DATABASES", {}) or {}).get("default", {})
    cache_default = (getattr(settings, "CACHES", {}) or {}).get("default", {})
    safe_runtime = [
        ("DEBUG", getattr(settings, "DEBUG", False)),
        ("ALLOWED_HOSTS", ", ".join(getattr(settings, "ALLOWED_HOSTS", []))),
        (
            "CORS_ALLOW_ALL_ORIGINS",
            getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False),
        ),
        ("CORS_ALLOW_CREDENTIALS", getattr(settings, "CORS_ALLOW_CREDENTIALS", True)),
        ("CSRF_COOKIE_SECURE", getattr(settings, "CSRF_COOKIE_SECURE", False)),
        ("SESSION_COOKIE_SECURE", getattr(settings, "SESSION_COOKIE_SECURE", False)),
        ("SECURE_SSL_REDIRECT", getattr(settings, "SECURE_SSL_REDIRECT", False)),
        ("DJANGO_SETTINGS_MODULE", os.environ.get("DJANGO_SETTINGS_MODULE", "")),
        ("MEDIA_ROOT", str(getattr(settings, "MEDIA_ROOT", ""))),
        ("STATIC_ROOT", str(getattr(settings, "STATIC_ROOT", ""))),
    ]

    db_rows = (
        [
            {
                "engine": db_default.get("ENGINE", ""),
                "host": db_default.get("HOST", ""),
                "port": db_default.get("PORT", ""),
                "name": db_default.get("NAME", ""),
                "user": _mask(db_default.get("USER", "")),
                "password": _mask(db_default.get("PASSWORD", "")),
            }
        ]
        if db_default
        else []
    )

    cache_rows = (
        [
            {
                "backend": cache_default.get("BACKEND", ""),
                "location": cache_default.get("LOCATION", ""),
                "timeout": cache_default.get("TIMEOUT", ""),
            }
        ]
        if cache_default
        else []
    )

    return {
        "generated_at": _iso(now()),
        "summary": [
            {
                "label": "Settings module",
                "value": os.environ.get("DJANGO_SETTINGS_MODULE", "n/a"),
            },
            {"label": "Debug", "value": getattr(settings, "DEBUG", False)},
            {
                "label": "Allowed hosts",
                "value": len(getattr(settings, "ALLOWED_HOSTS", [])),
            },
        ],
        "panels": [
            {"title": "Runtime settings", "items": safe_runtime},
        ],
        "tables": [
            {
                "title": "Database (default)",
                "columns": ["engine", "host", "port", "name", "user", "password"],
                "rows": db_rows,
            },
            {
                "title": "Cache (default)",
                "columns": ["backend", "location", "timeout"],
                "rows": cache_rows,
            },
        ],
    }


SECTION_META = {
    "overview": {
        "title": "Overview",
        "description": "Live summary of runtime, health, schemas, and workload.",
    },
    "health": {
        "title": "Health",
        "description": "System health, component checks, and metrics snapshot.",
    },
    "security": {
        "title": "Security",
        "description": "Runtime security controls, hosts/CORS/CSRF, and MFA posture.",
    },
    "logs": {
        "title": "Logs",
        "description": "Server log inventory with live tail preview from protected files.",
    },
    "jobs": {
        "title": "Jobs",
        "description": "Background task and export/import pipeline state.",
    },
    "data-ops": {
        "title": "Data Ops",
        "description": "Template catalogs and import activity for operational data flows.",
    },
    "backups": {
        "title": "Backups",
        "description": "Backup directory status, retention settings, and recent artifacts.",
    },
    "integrations": {
        "title": "Integrations",
        "description": "Connectivity/configuration status for external services.",
    },
    "audit": {
        "title": "Audit",
        "description": "Audit event trends, top event categories, and recent trail.",
    },
    "settings": {
        "title": "Settings",
        "description": "Safe runtime configuration snapshot with sensitive data redacted.",
    },
}

SECTION_LOADERS: dict[str, Callable[[HttpRequest], dict[str, Any]]] = {
    "overview": lambda _request: _build_overview_payload(),
    "health": lambda _request: _build_health_payload(),
    "security": lambda _request: _build_security_payload(),
    "logs": _build_logs_payload,
    "jobs": lambda _request: _build_jobs_payload(),
    "data-ops": lambda _request: _build_data_ops_payload(),
    "backups": lambda _request: _build_backups_payload(),
    "integrations": lambda _request: _build_integrations_payload(),
    "audit": lambda _request: _build_audit_payload(),
    "settings": lambda _request: _build_settings_payload(),
}


def _build_control_sections() -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for key, meta in SECTION_META.items():
        sections.append(
            {
                "key": key,
                "title": meta["title"],
                "url": reverse("control_center_page", kwargs={"section_key": key}),
                "api_url": reverse("control_center_api", kwargs={"section_key": key}),
            }
        )
    return sections


class SuperuserRequiredViewMixin:
    """Restrict access to authenticated superusers."""

    login_url_name = "admin:login"

    def _resolve_login_url(self) -> str:
        try:
            return reverse(self.login_url_name)
        except NoReverseMatch:
            return "/admin/login/"

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        user = request.user
        wants_json = "application/json" in (request.headers.get("Accept", "").lower())
        if not user.is_authenticated:
            if wants_json:
                return JsonResponse({"error": "Authentication required"}, status=401)
            return redirect_to_login(
                request.get_full_path(),
                self._resolve_login_url(),
            )
        if not user.is_superuser:
            if wants_json:
                return JsonResponse({"error": "Superuser access required"}, status=403)
            raise PermissionDenied("Superuser access required.")
        return super().dispatch(request, *args, **kwargs)


class ControlCenterPageView(SuperuserRequiredViewMixin, TemplateView):
    """Render one control center section page."""

    template_name = "root/control_center_page.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        section_key = self.kwargs.get("section_key", "overview")
        if section_key not in SECTION_META:
            section_key = "overview"
        payload = _safe_value(
            lambda: SECTION_LOADERS[section_key](self.request),
            {"summary": [], "panels": [], "tables": []},
        )
        context["control_sections"] = _build_control_sections()
        context["active_section"] = section_key
        context["section_meta"] = SECTION_META[section_key]
        context["payload"] = payload
        context["payload_json"] = json.dumps(
            payload,
            cls=DjangoJSONEncoder,
            ensure_ascii=True,
        )
        context["api_endpoint"] = reverse(
            "control_center_api",
            kwargs={"section_key": section_key},
        )
        context["create_backup_endpoint"] = ""
        context["media_entries_endpoint"] = ""
        context["media_job_start_endpoint"] = ""
        context["media_job_status_template"] = ""
        context["media_poll_interval_seconds"] = _media_export_poll_interval_seconds()
        if section_key == "backups":
            context["create_backup_endpoint"] = reverse(
                "control_center_backup_create_download"
            )
            context["media_entries_endpoint"] = reverse(
                "control_center_media_export_entries"
            )
            context["media_job_start_endpoint"] = reverse(
                "control_center_media_export_job_create"
            )
            context["media_job_status_template"] = reverse(
                "control_center_media_export_job_status",
                kwargs={"job_id": UUID("00000000-0000-0000-0000-000000000000")},
            )
        return context


class ControlCenterApiView(SuperuserRequiredViewMixin, View):
    """Return JSON payload for one control center section."""

    def get(self, request: HttpRequest, section_key: str) -> JsonResponse:
        if section_key not in SECTION_META:
            return JsonResponse({"error": "Unknown section"}, status=404)
        payload = _safe_value(
            lambda: SECTION_LOADERS[section_key](request),
            {
                "summary": [],
                "panels": [],
                "tables": [],
                "error": "Unable to load payload",
            },
        )
        response = {
            "section": section_key,
            "meta": SECTION_META[section_key],
            "payload": payload,
        }
        return JsonResponse(response, safe=False)


class ControlCenterMediaExportEntriesView(SuperuserRequiredViewMixin, View):
    """List selectable top-level media entries for export."""

    def get(self, request: HttpRequest) -> JsonResponse:
        _cleanup_expired_media_exports()
        _reconcile_stale_media_jobs()
        entries, _entry_map = _list_media_top_level_entries()
        media_root = _resolve_media_root()
        response = {
            "media_root": str(media_root),
            "exists": media_root.exists() and media_root.is_dir(),
            "entries": entries,
            "constraints": {
                "max_uncompressed_bytes": _media_export_max_uncompressed_bytes(),
                "retention_hours": _media_export_retention_hours(),
                "poll_interval_seconds": _media_export_poll_interval_seconds(),
            },
        }
        return JsonResponse(response)


class ControlCenterMediaExportJobCreateView(SuperuserRequiredViewMixin, View):
    """Create asynchronous media export job."""

    def post(self, request: HttpRequest) -> JsonResponse:
        _cleanup_expired_media_exports()
        _reconcile_stale_media_jobs()

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

        selected_entry_ids = payload.get("selected_entry_ids")
        if not isinstance(selected_entry_ids, list):
            return JsonResponse(
                {"error": "selected_entry_ids must be a list."},
                status=400,
            )
        selected_entry_ids = [
            str(entry_id).strip()
            for entry_id in selected_entry_ids
            if str(entry_id).strip()
        ]
        if not selected_entry_ids:
            return JsonResponse(
                {"error": "At least one media entry must be selected."},
                status=400,
            )

        entries, entry_map = _list_media_top_level_entries()
        valid_ids = {row["id"] for row in entries}
        selected_ids: list[str] = []
        seen: set[str] = set()
        for entry_id in selected_entry_ids:
            if entry_id not in valid_ids:
                continue
            if entry_id in seen:
                continue
            seen.add(entry_id)
            selected_ids.append(entry_id)
        if not selected_ids:
            return JsonResponse(
                {"error": "Selected media entries are not valid."},
                status=400,
            )

        running_statuses = [MediaExportJobStatus.PENDING, MediaExportJobStatus.RUNNING]
        if MediaExportJob.objects.filter(
            requested_by=request.user, status__in=running_statuses
        ).exists():
            return JsonResponse(
                {
                    "error": (
                        "You already have a running media export job. "
                        "Wait for completion before starting a new one."
                    )
                },
                status=409,
            )
        global_running = MediaExportJob.objects.filter(status__in=running_statuses).count()
        if global_running >= _MEDIA_EXPORT_GLOBAL_CONCURRENCY:
            return JsonResponse(
                {"error": "Media export concurrency limit reached. Try again shortly."},
                status=429,
            )

        selected_paths = [entry_map[entry_id].name for entry_id in selected_ids]
        job = MediaExportJob.objects.create(
            requested_by=request.user,
            status=MediaExportJobStatus.PENDING,
            progress=0,
            selected_paths=selected_paths,
            message="Job queued.",
            metadata={"selected_entry_ids": selected_ids},
        )
        _start_media_export_job(job.id)
        return JsonResponse(
            {
                "job_id": str(job.id),
                "status": job.status,
                "created_at": _iso(job.created_at),
            },
            status=201,
        )


class ControlCenterMediaExportJobStatusView(SuperuserRequiredViewMixin, View):
    """Return asynchronous media export job status for polling."""

    def get(self, request: HttpRequest, job_id: UUID) -> JsonResponse:
        _cleanup_expired_media_exports()
        _reconcile_stale_media_jobs()
        job = MediaExportJob.objects.filter(pk=job_id).first()
        if job is None:
            return JsonResponse({"error": "Media export job not found."}, status=404)

        download_url = ""
        if job.status == MediaExportJobStatus.SUCCESS and job.archive_name:
            archive_path = (_resolve_media_export_dir() / job.archive_name).resolve()
            if archive_path.is_file() and _is_within_directory(
                _resolve_media_export_dir(), archive_path
            ):
                download_url = reverse(
                    "control_center_media_export_download",
                    kwargs={"archive_name": job.archive_name},
                )

        return JsonResponse(
            {
                "job_id": str(job.id),
                "status": job.status,
                "progress": int(job.progress or 0),
                "message": job.message or "",
                "error": job.error_message or "",
                "archive_name": job.archive_name or "",
                "download_url": download_url,
                "created_at": _iso(job.created_at),
                "started_at": _iso(job.started_at),
                "finished_at": _iso(job.finished_at),
                "expires_at": _iso(job.expires_at),
            }
        )


class ControlCenterMediaExportDownloadView(SuperuserRequiredViewMixin, View):
    """Download generated media export ZIP file."""

    def get(self, request: HttpRequest, archive_name: str) -> HttpResponse:
        archive_name = str(archive_name or "")
        if "/" in archive_name or "\\" in archive_name:
            raise Http404("Archive not found")
        if not archive_name.startswith("media_export_") or not archive_name.endswith(
            ".zip"
        ):
            raise Http404("Archive not found")

        export_dir = _resolve_media_export_dir().resolve()
        archive_path = (export_dir / archive_name).resolve()
        if not _is_within_directory(export_dir, archive_path):
            raise Http404("Archive not found")
        if not archive_path.is_file():
            raise Http404("Archive not found")

        return FileResponse(
            archive_path.open("rb"),
            as_attachment=True,
            filename=archive_name,
        )


class ControlCenterBackupDownloadView(SuperuserRequiredViewMixin, View):
    """Download one backup artifact from the configured backup directory."""

    def get(self, request: HttpRequest, backup_name: str) -> HttpResponse:
        if not backup_name.startswith("backup_"):
            raise Http404("Backup file not found")
        if not (
            backup_name.endswith(".sql")
            or backup_name.endswith(".sql.gz")
            or backup_name.endswith(".dump")
        ):
            raise Http404("Backup file not found")

        backup_dir = _resolve_backup_dir().resolve()
        backup_path = (backup_dir / backup_name).resolve()
        if backup_path.parent != backup_dir:
            raise Http404("Backup file not found")
        if not backup_path.is_file():
            raise Http404("Backup file not found")

        return FileResponse(
            backup_path.open("rb"),
            as_attachment=True,
            filename=backup_path.name,
        )


class ControlCenterBackupCreateDownloadView(SuperuserRequiredViewMixin, View):
    """Create a PostgreSQL backup and return it as an attachment."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not _is_postgresql_database():
            return HttpResponse(
                "Backup creation is supported only for PostgreSQL databases.",
                status=400,
                content_type="text/plain",
            )

        try:
            backup_file = _create_postgresql_backup_file()
        except RuntimeError as exc:
            return HttpResponse(
                f"Backup creation failed: {exc}",
                status=500,
                content_type="text/plain",
            )

        return FileResponse(
            backup_file.open("rb"),
            as_attachment=True,
            filename=backup_file.name,
        )


def get_control_center_urls():
    """Return URL patterns for control center pages and APIs."""
    from django.urls import path

    return [
        path(
            "control-center/",
            ControlCenterPageView.as_view(),
            {"section_key": "overview"},
            name="control_center_root",
        ),
        path(
            "control-center/<slug:section_key>/",
            ControlCenterPageView.as_view(),
            name="control_center_page",
        ),
        path(
            "control-center/api/<slug:section_key>/",
            ControlCenterApiView.as_view(),
            name="control_center_api",
        ),
        path(
            "control-center/backups/download/<str:backup_name>/",
            ControlCenterBackupDownloadView.as_view(),
            name="control_center_backup_download",
        ),
        path(
            "control-center/backups/create-download/",
            ControlCenterBackupCreateDownloadView.as_view(),
            name="control_center_backup_create_download",
        ),
        path(
            "control-center/api/media-export/entries/",
            ControlCenterMediaExportEntriesView.as_view(),
            name="control_center_media_export_entries",
        ),
        path(
            "control-center/media-export/jobs/",
            ControlCenterMediaExportJobCreateView.as_view(),
            name="control_center_media_export_job_create",
        ),
        path(
            "control-center/media-export/jobs/<uuid:job_id>/",
            ControlCenterMediaExportJobStatusView.as_view(),
            name="control_center_media_export_job_status",
        ),
        path(
            "control-center/media-export/download/<str:archive_name>/",
            ControlCenterMediaExportDownloadView.as_view(),
            name="control_center_media_export_download",
        ),
    ]


__all__ = [
    "ControlCenterApiView",
    "ControlCenterBackupCreateDownloadView",
    "ControlCenterBackupDownloadView",
    "ControlCenterMediaExportEntriesView",
    "ControlCenterMediaExportJobCreateView",
    "ControlCenterMediaExportJobStatusView",
    "ControlCenterMediaExportDownloadView",
    "ControlCenterPageView",
    "SECTION_META",
    "get_control_center_urls",
]

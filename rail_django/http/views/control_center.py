"""Superuser-only Control Center pages and APIs."""

from __future__ import annotations

import json
import logging
import os
import gzip
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
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
from rail_django.models import MetadataDeployVersionModel, SchemaRegistryModel
from rail_django.security.config import SecurityConfig

logger = logging.getLogger(__name__)
_PROCESS_STARTED_AT = now()


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


def _build_pg_dump_command(raw_file: Path) -> tuple[list[str], dict[str, str]]:
    db = _default_database_config()
    db_name = db.get("NAME")
    if not db_name:
        raise RuntimeError("PostgreSQL database name is not configured.")

    command = [
        "pg_dump",
        "--format=plain",
        "--no-owner",
        "--no-privileges",
        f"--file={raw_file}",
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
    raw_file = backup_dir / f"backup_{timestamp}.sql"
    archive_file = Path(f"{raw_file}.gz")
    command, env = _build_pg_dump_command(raw_file)

    try:
        subprocess.run(command, env=env, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("pg_dump is not installed on the server.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or "").strip() or "pg_dump failed."
        raise RuntimeError(message) from exc

    if not raw_file.exists() or raw_file.stat().st_size == 0:
        raw_file.unlink(missing_ok=True)
        raise RuntimeError("pg_dump produced an empty backup file.")

    with raw_file.open("rb") as source, gzip.open(archive_file, "wb") as target:
        target.write(source.read())
    raw_file.unlink(missing_ok=True)
    return archive_file


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
    retention_days = os.environ.get("BACKUP_RETENTION_DAYS", "30")
    files = []
    if backup_dir.exists():
        for path in sorted(
            backup_dir.glob("backup_*.sql*"),
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
    return {
        "generated_at": _iso(now()),
        "summary": [
            {"label": "Backup directory", "value": str(backup_dir)},
            {"label": "Retention days", "value": retention_days},
            {"label": "Total backup files", "value": len(files)},
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
                ],
            }
        ],
        "tables": [
            {
                "title": "Backup files",
                "columns": ["name", "size", "modified_at", "download", "path"],
                "rows": files,
            }
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
        if section_key == "backups":
            context["create_backup_endpoint"] = reverse(
                "control_center_backup_create_download"
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


class ControlCenterBackupDownloadView(SuperuserRequiredViewMixin, View):
    """Download one backup artifact from the configured backup directory."""

    def get(self, request: HttpRequest, backup_name: str) -> HttpResponse:
        if not backup_name.startswith("backup_"):
            raise Http404("Backup file not found")
        if not (backup_name.endswith(".sql") or backup_name.endswith(".sql.gz")):
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
    ]


__all__ = [
    "ControlCenterApiView",
    "ControlCenterBackupCreateDownloadView",
    "ControlCenterBackupDownloadView",
    "ControlCenterPageView",
    "SECTION_META",
    "get_control_center_urls",
]

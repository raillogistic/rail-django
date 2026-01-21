"""
Configuration for background task orchestration.
"""

from dataclasses import dataclass
from typing import Any, Optional

from ...config_proxy import get_setting


@dataclass(frozen=True)
class TaskSettings:
    enabled: bool
    backend: str
    default_queue: str
    result_ttl_seconds: int
    max_retries: int
    retry_backoff: bool
    track_in_database: bool
    emit_subscriptions: bool


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_task_settings(schema_name: Optional[str] = None) -> TaskSettings:
    enabled = _coerce_bool(get_setting("task_settings.enabled", False, schema_name), False)
    backend = _coerce_str(
        get_setting("task_settings.backend", "thread", schema_name), "thread"
    ).lower()
    default_queue = _coerce_str(
        get_setting("task_settings.default_queue", "default", schema_name), "default"
    )
    result_ttl_seconds = _coerce_int(
        get_setting("task_settings.result_ttl_seconds", 86400, schema_name), 86400
    )
    max_retries = _coerce_int(
        get_setting("task_settings.max_retries", 3, schema_name), 3
    )
    retry_backoff = _coerce_bool(
        get_setting("task_settings.retry_backoff", True, schema_name), True
    )
    track_in_database = _coerce_bool(
        get_setting("task_settings.track_in_database", True, schema_name), True
    )
    emit_subscriptions = _coerce_bool(
        get_setting("task_settings.emit_subscriptions", True, schema_name), True
    )

    return TaskSettings(
        enabled=enabled,
        backend=backend,
        default_queue=default_queue,
        result_ttl_seconds=result_ttl_seconds,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
        track_in_database=track_in_database,
        emit_subscriptions=emit_subscriptions,
    )


def tasks_enabled(schema_name: Optional[str] = None) -> bool:
    return get_task_settings(schema_name).enabled

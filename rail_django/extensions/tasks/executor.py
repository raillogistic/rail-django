"""
Task execution logic and backend integration.
"""

import inspect
import logging
import threading
import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Callable, Optional

import graphene
from django.contrib.auth import get_user_model
from django.utils import timezone
from graphene.types.generic import GenericScalar

from ...generators.subscriptions.utils import RailSubscription
from .models import TaskExecution, TaskStatus
from .config import get_task_settings
from .utils import (
    _update_task_execution,
    _normalize_task_result,
    _safe_json_value,
    _build_task_group,
    _resolve_schema_name,
    _task_is_expired,
    _task_access_allowed,
)

logger = logging.getLogger(__name__)

_TASK_SUBSCRIPTION_CLASS: Optional[type] = None


class TaskExecutionHandle:
    def __init__(self, task_id: str, schema_name: str, *, track_progress: bool = True):
        self.task_id = str(task_id)
        self.schema_name = schema_name
        self.track_progress = track_progress

    def update_progress(self, progress: int) -> None:
        if not self.track_progress:
            return
        _update_task_execution(
            self.task_id,
            schema_name=self.schema_name,
            progress=progress,
        )


def _get_task_subscription_class() -> Optional[type]:
    global _TASK_SUBSCRIPTION_CLASS
    if _TASK_SUBSCRIPTION_CLASS is not None:
        return _TASK_SUBSCRIPTION_CLASS

    from .queries import TaskExecutionPayloadType

    class TaskUpdatedSubscription(RailSubscription):
        task_id = graphene.ID(required=True)
        status = graphene.String(required=True)
        progress = graphene.Int()
        result = GenericScalar()
        error = graphene.String()
        task = graphene.Field(TaskExecutionPayloadType)

        @staticmethod
        def subscribe(root, info, task_id: str):
            schema_name = _resolve_schema_name(info)
            task = TaskExecution.objects.filter(pk=task_id).first()
            if not task or _task_is_expired(task):
                raise Exception("Task not found.")
            if not _task_access_allowed(info.context, task, schema_name):
                raise Exception("Task not found.")
            return [_build_task_group(schema_name, task_id)]

        @staticmethod
        def publish(payload, info, task_id: str):
            task = TaskExecution.objects.filter(pk=task_id).first()
            if not task or _task_is_expired(task):
                return RailSubscription.SKIP
            schema_name = _resolve_schema_name(info)
            if not _task_access_allowed(info.context, task, schema_name):
                return RailSubscription.SKIP
            return {
                "task_id": str(task.id),
                "status": task.status,
                "progress": task.progress,
                "result": task.result,
                "error": task.error,
                "task": task,
            }

    _TASK_SUBSCRIPTION_CLASS = TaskUpdatedSubscription
    return TaskUpdatedSubscription


def _build_task_context(payload: dict[str, Any], task_id: str) -> SimpleNamespace:
    schema_name = payload.get("schema_name") or "default"
    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    headers = payload.get("headers") or {}
    track_progress = bool(payload.get("track_progress", True))

    user = None
    if user_id:
        try:
            user = get_user_model().objects.filter(pk=user_id).first()
        except Exception:
            user = None

    task_handle = TaskExecutionHandle(
        task_id=task_id,
        schema_name=schema_name,
        track_progress=track_progress,
    )
    context = SimpleNamespace(
        user=user,
        schema_name=schema_name,
        tenant_id=tenant_id,
        headers=headers,
        task=task_handle,
    )
    return SimpleNamespace(context=context)


def _call_task_callable(
    func: Callable[..., Any],
    info: Any,
    payload: dict[str, Any],
    mode: str,
):
    if mode == "root_info":
        return func(None, info, **payload)
    if mode == "info":
        return func(info, **payload)
    return func(**payload)


def _import_callable(path: str) -> Optional[Callable[..., Any]]:
    try:
        from django.utils.module_loading import import_string
        return import_string(path)
    except Exception:
        return None


def _execute_task(
    task_id: str,
    func: Optional[Callable[..., Any]],
    func_path: Optional[str],
    payload: dict[str, Any],
    context_payload: dict[str, Any],
) -> None:
    schema_name = context_payload.get("schema_name") or "default"
    settings_obj = get_task_settings(schema_name)
    attempts = 0
    raw_retries = context_payload.get("max_retries", settings_obj.max_retries)
    try:
        max_retries = max(0, int(raw_retries))
    except (TypeError, ValueError):
        max_retries = settings_obj.max_retries
    while True:
        attempts += 1
        now = timezone.now()
        updates = {
            "status": TaskStatus.RUNNING,
            "started_at": now,
            "attempts": attempts,
        }
        _update_task_execution(task_id, schema_name=schema_name, **updates)

        try:
            callable_target = func or _import_callable(func_path or "")
            if callable_target is None:
                raise RuntimeError("Task callable is not available.")
            info = _build_task_context(context_payload, task_id)
            call_mode = context_payload.get("call_mode", "root_info")
            result = _call_task_callable(callable_target, info, payload, call_mode)
            result_value = _safe_json_value(result)
            completed_at = timezone.now()
            expires_at = None
            if settings_obj.result_ttl_seconds:
                expires_at = completed_at + timedelta(seconds=settings_obj.result_ttl_seconds)
            _update_task_execution(
                task_id,
                schema_name=schema_name,
                status=TaskStatus.SUCCESS,
                progress=100,
                result=result_value,
                completed_at=completed_at,
                expires_at=expires_at,
                error=None,
            )
            _normalize_task_result(task_id, schema_name=schema_name)
            return
        except Exception as exc:
            error_text = str(exc)
            if attempts <= max_retries:
                _update_task_execution(
                    task_id,
                    schema_name=schema_name,
                    status=TaskStatus.RETRYING,
                    error=error_text,
                )
                if settings_obj.retry_backoff:
                    delay = min(60, 2 ** (attempts - 1))
                    time.sleep(delay)
                continue
            completed_at = timezone.now()
            expires_at = None
            if settings_obj.result_ttl_seconds:
                expires_at = completed_at + timedelta(seconds=settings_obj.result_ttl_seconds)
            _update_task_execution(
                task_id,
                schema_name=schema_name,
                status=TaskStatus.FAILED,
                error=error_text,
                completed_at=completed_at,
                expires_at=expires_at,
            )
            return


def _schedule_task_execution(
    *,
    task_id: str,
    schema_name: str,
    func: Callable[..., Any],
    func_path: Optional[str],
    payload: dict[str, Any],
    context_payload: dict[str, Any],
    backend: str,
    default_queue: str,
) -> Optional[str]:
    if backend == "sync":
        _execute_task(task_id, func, func_path, payload, context_payload)
        return None

    if backend == "thread":
        thread = threading.Thread(
            target=_execute_task,
            args=(task_id, func, func_path, payload, context_payload),
            daemon=True,
        )
        thread.start()
        return None

    if backend == "celery":
        if task_execute_task is None:
            return "Celery backend not available"
        if not func_path:
            return "Celery backend requires an importable task function."
        task_execute_task.apply_async(
            args=[task_id, func_path, payload, context_payload],
            queue=default_queue,
        )
        return None

    if backend == "dramatiq":
        if task_execute_actor is None:
            return "Dramatiq backend not available"
        if not func_path:
            return "Dramatiq backend requires an importable task function."
        task_execute_actor.send(task_id, func_path, payload, context_payload)
        return None

    if backend == "django_q":
        try:
            from django_q.tasks import async_task
            async_task(_execute_task, task_id, None, func_path, payload, context_payload)
            return None
        except ImportError:
            return "Django Q backend not available"

    return f"Unknown task backend '{backend}'"


# Backend wrappers
try:
    from celery import shared_task
except Exception:
    shared_task = None

if shared_task:
    @shared_task(name="rail_django.task_execute")
    def task_execute_task(task_id: str, func_path: str, payload: dict, context_payload: dict):
        _execute_task(task_id, None, func_path, payload, context_payload)
else:
    task_execute_task = None

try:
    import dramatiq
except Exception:
    dramatiq = None

if dramatiq:
    @dramatiq.actor
    def task_execute_actor(task_id: str, func_path: str, payload: dict, context_payload: dict):
        _execute_task(task_id, None, func_path, payload, context_payload)
else:
    task_execute_actor = None

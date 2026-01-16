"""
Background task orchestration helpers.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Callable, Optional, Union, get_args, get_origin

import graphene
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views import View
from graphene.types.generic import GenericScalar
from graphql import GraphQLError

from ..config_proxy import get_setting

logger = logging.getLogger(__name__)

_GROUP_NAME_SAFE_RE = re.compile(r"[^0-9A-Za-z_.-]")
_TASK_SUBSCRIPTION_CLASS: Optional[type] = None


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


def _authentication_required(schema_name: Optional[str]) -> bool:
    return _coerce_bool(
        get_setting("schema_settings.authentication_required", False, schema_name),
        False,
    )


class TaskStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    RETRYING = "RETRYING", "Retrying"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    CANCELED = "CANCELED", "Canceled"


class TaskExecution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING
    )
    progress = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    result_reference = models.CharField(max_length=255, null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    owner_id = models.CharField(max_length=64, null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_retries = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "rail_django"
        verbose_name = "Task Execution"
        verbose_name_plural = "Task Executions"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"


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


class TaskExecutionPayloadType(graphene.ObjectType):
    id = graphene.ID(required=True)
    name = graphene.String()
    status = graphene.String()
    progress = graphene.Int()
    result = GenericScalar()
    result_reference = graphene.String()
    error = graphene.String()
    metadata = GenericScalar()
    created_at = graphene.DateTime()
    started_at = graphene.DateTime()
    completed_at = graphene.DateTime()
    expires_at = graphene.DateTime()
    owner_id = graphene.String()
    attempts = graphene.Int()
    max_retries = graphene.Int()
    updated_at = graphene.DateTime()

    class Meta:
        name = "TaskExecution"


class TaskQuery(graphene.ObjectType):
    task = graphene.Field(TaskExecutionPayloadType, id=graphene.ID(required=True))
    tasks = graphene.List(
        TaskExecutionPayloadType,
        status=graphene.String(required=False),
        limit=graphene.Int(required=False),
    )

    @staticmethod
    def resolve_task(root, info, id: str):
        schema_name = _resolve_schema_name(info)
        settings = get_task_settings(schema_name)
        if not settings.enabled:
            raise GraphQLError("Task orchestration is disabled.")

        task = TaskExecution.objects.filter(pk=id).first()
        if not task or _task_is_expired(task) or not _task_matches_schema(task, schema_name):
            raise GraphQLError("Task not found.")
        if not _task_access_allowed(info.context, task, schema_name):
            raise GraphQLError("Task not found.")
        return task

    @staticmethod
    def resolve_tasks(root, info, status: Optional[str] = None, limit: Optional[int] = None):
        schema_name = _resolve_schema_name(info)
        settings = get_task_settings(schema_name)
        if not settings.enabled:
            raise GraphQLError("Task orchestration is disabled.")

        queryset = TaskExecution.objects.all()
        if status:
            queryset = queryset.filter(status=str(status).upper())
        queryset = _filter_queryset_for_user(info.context, queryset, schema_name)
        tasks = [task for task in queryset if _task_matches_schema(task, schema_name)]
        if limit:
            tasks = tasks[: int(limit)]
        return tasks


def _task_is_expired(task: TaskExecution) -> bool:
    if not task.expires_at:
        return False
    return timezone.now() > task.expires_at


def _resolve_schema_name(info: Any) -> str:
    context = getattr(info, "context", None)
    if context is None:
        return "default"
    schema_name = getattr(context, "schema_name", None)
    if schema_name:
        return schema_name
    if isinstance(context, dict):
        return context.get("schema_name", "default") or "default"
    return "default"

def _task_matches_schema(task: TaskExecution, schema_name: str) -> bool:
    resolved_schema = schema_name or "default"
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    task_schema = metadata.get("schema_name")
    if task_schema:
        return str(task_schema) == str(resolved_schema)
    return resolved_schema == "default"


def _task_access_allowed(context: Any, task: TaskExecution, schema_name: str) -> bool:
    user = _get_context_user(context)
    if user and getattr(user, "is_authenticated", False):
        if getattr(user, "is_superuser", False):
            return True
        return bool(task.owner_id and str(task.owner_id) == str(user.id))
    if _authentication_required(schema_name):
        return False
    return task.owner_id is None


def _filter_queryset_for_user(
    context: Any, queryset: models.QuerySet, schema_name: str
) -> models.QuerySet:
    user = _get_context_user(context)
    if user and getattr(user, "is_authenticated", False):
        if getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(owner_id=str(user.id))
    if _authentication_required(schema_name):
        return queryset.none()
    return queryset.filter(owner_id__isnull=True)


def _get_context_user(context: Any) -> Any:
    if context is None:
        return None
    if isinstance(context, dict):
        return context.get("user")
    return getattr(context, "user", None)


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except (TypeError, ValueError):
                pass
        return value
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _safe_json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_json_value(value) for key, value in payload.items()}


def _update_task_execution(
    task_id: str,
    *,
    schema_name: str,
    **updates: Any,
) -> None:
    updates = dict(updates)
    if "progress" in updates:
        try:
            progress = int(updates["progress"])
        except (TypeError, ValueError):
            progress = 0
        updates["progress"] = max(0, min(100, progress))
    updates["updated_at"] = timezone.now()
    TaskExecution.objects.filter(pk=task_id).update(**updates)
    _emit_task_update(task_id, schema_name=schema_name)

def _normalize_task_result(task_id: str, *, schema_name: str) -> None:
    task = TaskExecution.objects.filter(pk=task_id).only("result").first()
    if not task:
        return
    normalized = _safe_json_value(task.result)
    if normalized is task.result:
        return
    task.result = normalized
    task.updated_at = timezone.now()
    task.save(update_fields=["result", "updated_at"])
    _emit_task_update(task_id, schema_name=schema_name)


def _build_task_group(schema_name: str, task_id: str) -> str:
    raw = f"rail_task:{schema_name}:{task_id}"
    safe = _GROUP_NAME_SAFE_RE.sub("_", raw)
    return safe[:90]


def _emit_task_update(task_id: str, *, schema_name: Optional[str] = None) -> None:
    if schema_name is None:
        task = TaskExecution.objects.filter(pk=task_id).first()
        if task and isinstance(task.metadata, dict):
            schema_name = task.metadata.get("schema_name")
    if not schema_name:
        schema_name = "default"

    settings = get_task_settings(schema_name)
    if not settings.enabled or not settings.emit_subscriptions:
        return

    subscription_class = _get_task_subscription_class()
    if subscription_class is None:
        return
    try:
        subscription_class.broadcast(
            group=_build_task_group(schema_name, task_id),
            payload={"task_id": str(task_id)},
        )
    except Exception as exc:
        logger.warning("Task update broadcast failed: %s", exc)


def _get_task_subscription_class() -> Optional[type]:
    global _TASK_SUBSCRIPTION_CLASS
    if _TASK_SUBSCRIPTION_CLASS is not None:
        return _TASK_SUBSCRIPTION_CLASS
    try:
        import channels_graphql_ws  # type: ignore
    except Exception:
        return None

    class TaskUpdatedSubscription(channels_graphql_ws.Subscription):
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
                raise GraphQLError("Task not found.")
            if not _task_access_allowed(info.context, task, schema_name):
                raise GraphQLError("Task not found.")
            return [_build_task_group(schema_name, task_id)]

        @staticmethod
        def publish(payload, info, task_id: str):
            task = TaskExecution.objects.filter(pk=task_id).first()
            if not task or _task_is_expired(task):
                return channels_graphql_ws.Subscription.SKIP
            schema_name = _resolve_schema_name(info)
            if not _task_access_allowed(info.context, task, schema_name):
                return channels_graphql_ws.Subscription.SKIP
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


def get_task_subscription_field(schema_name: str) -> Optional[graphene.Field]:
    settings = get_task_settings(schema_name)
    if not settings.enabled or not settings.emit_subscriptions:
        return None
    subscription_class = _get_task_subscription_class()
    if subscription_class is None:
        return None
    return subscription_class.Field()


def _snapshot_context(info: Any, schema_name: str, track_progress: bool) -> dict[str, Any]:
    context = getattr(info, "context", None)
    user = _get_context_user(context)
    user_id = (
        str(user.id) if user and getattr(user, "is_authenticated", False) else None
    )
    tenant_id = getattr(context, "tenant_id", None)
    headers = {}
    if hasattr(context, "headers"):
        try:
            headers = dict(getattr(context, "headers") or {})
        except Exception:
            headers = {}
    return {
        "schema_name": schema_name,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "headers": headers,
        "track_progress": track_progress,
    }


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


def _resolve_call_mode(signature: inspect.Signature) -> str:
    params = [
        param
        for param in signature.parameters.values()
        if param.kind
        in (
            param.POSITIONAL_ONLY,
            param.POSITIONAL_OR_KEYWORD,
            param.KEYWORD_ONLY,
        )
    ]
    if params and params[0].name == "info":
        return "info"
    if len(params) >= 2 and params[0].name in {"root", "parent", "self"}:
        if params[1].name == "info":
            return "root_info"
    return "kwargs"


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


def _callable_path(func: Callable[..., Any]) -> Optional[str]:
    qualname = getattr(func, "__qualname__", "")
    if "<locals>" in qualname:
        return None
    return f"{func.__module__}.{qualname}"


def _import_callable(path: str) -> Optional[Callable[..., Any]]:
    try:
        from django.utils.module_loading import import_string

        return import_string(path)
    except Exception:
        return None


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
        if async_task is None:
            return "Django Q backend not available"
        if not func_path:
            return "Django Q backend requires an importable task function."
        async_task(_execute_task, task_id, None, func_path, payload, context_payload)
        return None

    return f"Unknown task backend '{backend}'"


def _execute_task(
    task_id: str,
    func: Optional[Callable[..., Any]],
    func_path: Optional[str],
    payload: dict[str, Any],
    context_payload: dict[str, Any],
) -> None:
    schema_name = context_payload.get("schema_name") or "default"
    settings = get_task_settings(schema_name)
    attempts = 0
    raw_retries = context_payload.get("max_retries", settings.max_retries)
    try:
        max_retries = max(0, int(raw_retries))
    except (TypeError, ValueError):
        max_retries = settings.max_retries
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
            if settings.result_ttl_seconds:
                expires_at = completed_at + timedelta(seconds=settings.result_ttl_seconds)
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
                if settings.retry_backoff:
                    delay = min(60, 2 ** (attempts - 1))
                    time.sleep(delay)
                continue
            completed_at = timezone.now()
            expires_at = None
            if settings.result_ttl_seconds:
                expires_at = completed_at + timedelta(seconds=settings.result_ttl_seconds)
            _update_task_execution(
                task_id,
                schema_name=schema_name,
                status=TaskStatus.FAILED,
                error=error_text,
                completed_at=completed_at,
                expires_at=expires_at,
            )
            return


def task_mutation(
    *,
    name: Optional[str] = None,
    track_progress: bool = True,
    max_retries: Optional[int] = None,
):
    def decorator(func: Callable[..., Any]):
        signature = inspect.signature(func)
        call_mode = _resolve_call_mode(signature)

        arguments: dict[str, Any] = {}
        for param in signature.parameters.values():
            if param.name in {"root", "info"}:
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            gql_type = _convert_annotation_to_graphene(param.annotation)
            if param.default is inspect.Parameter.empty:
                arguments[param.name] = gql_type(required=True)
            else:
                arguments[param.name] = gql_type(default_value=param.default)

        arguments_type = type("Arguments", (), arguments)
        task_name = name or func.__name__

        class TaskMutation(graphene.Mutation):
            Arguments = arguments_type

            task_id = graphene.ID(required=True)
            status = graphene.String(required=True)
            task = graphene.Field(TaskExecutionPayloadType)
            error = graphene.String()

            @staticmethod
            def mutate(root, info, **kwargs):
                schema_name = _resolve_schema_name(info)
                settings = get_task_settings(schema_name)
                if not settings.enabled:
                    raise GraphQLError("Task orchestration is disabled.")

                context_payload = _snapshot_context(info, schema_name, track_progress)
                context_payload["call_mode"] = call_mode
                metadata = {
                    "schema_name": schema_name,
                    "payload": _safe_json_payload(kwargs),
                }
                if context_payload.get("user_id") is not None:
                    metadata["user_id"] = context_payload.get("user_id")
                if context_payload.get("tenant_id") is not None:
                    metadata["tenant_id"] = context_payload.get("tenant_id")

                retries = max_retries if max_retries is not None else settings.max_retries
                max_retries_value = max(0, int(retries or 0))
                context_payload["max_retries"] = max_retries_value

                task = TaskExecution.objects.create(
                    name=task_name,
                    status=TaskStatus.PENDING,
                    progress=0,
                    metadata=metadata,
                    owner_id=context_payload.get("user_id"),
                    max_retries=max_retries_value,
                )

                func_path = _callable_path(func)
                payload = _safe_json_payload(kwargs)

                schedule_error: Optional[str] = None

                def _enqueue():
                    nonlocal schedule_error
                    error = _schedule_task_execution(
                        task_id=str(task.id),
                        schema_name=schema_name,
                        func=func,
                        func_path=func_path,
                        payload=payload,
                        context_payload=context_payload,
                        backend=settings.backend,
                        default_queue=settings.default_queue,
                    )
                    if error:
                        schedule_error = error
                        _update_task_execution(
                            str(task.id),
                            schema_name=schema_name,
                            status=TaskStatus.FAILED,
                            error=error,
                            completed_at=timezone.now(),
                        )

                if settings.backend == "sync":
                    _enqueue()
                else:
                    try:
                        transaction.on_commit(_enqueue)
                    except Exception:
                        _enqueue()

                if settings.backend == "sync":
                    task.refresh_from_db()
                    normalized_result = _safe_json_value(task.result)
                    if normalized_result is not task.result:
                        task.result = normalized_result
                        task.updated_at = timezone.now()
                        task.save(update_fields=["result", "updated_at"])

                return TaskMutation(
                    task_id=str(task.id),
                    status=task.status,
                    task=task,
                    error=schedule_error,
                )

        return TaskMutation.Field(description=(func.__doc__ or None))

    return decorator


def _convert_annotation_to_graphene(annotation: Any) -> type[graphene.Scalar]:
    if annotation is inspect.Parameter.empty:
        return graphene.String

    origin = get_origin(annotation)
    if origin is not None:
        if origin in {list, tuple, set, dict}:
            return GenericScalar
        if origin is Union:
            args = [arg for arg in get_args(annotation) if arg is not type(None)]
            if args:
                return _convert_annotation_to_graphene(args[0])

    if isinstance(annotation, str):
        lowered = annotation.lower()
        if lowered in {"int", "integer"}:
            return graphene.Int
        if lowered in {"float"}:
            return graphene.Float
        if lowered in {"bool", "boolean"}:
            return graphene.Boolean
        if lowered in {"dict", "mapping", "list", "tuple", "set", "any"}:
            return GenericScalar
        return graphene.String

    try:
        if issubclass(annotation, graphene.Scalar):
            return annotation
    except Exception:
        pass

    type_mapping = {
        str: graphene.String,
        int: graphene.Int,
        float: graphene.Float,
        bool: graphene.Boolean,
        dict: GenericScalar,
        list: GenericScalar,
        Any: GenericScalar,
    }
    return type_mapping.get(annotation, graphene.String)


class TaskStatusView(View):
    def get(self, request, task_id):
        schema_name = getattr(request, "schema_name", None) or "default"
        settings = get_task_settings(schema_name)
        if not settings.enabled:
            raise Http404("Tasks are disabled")

        task = TaskExecution.objects.filter(pk=task_id).first()
        if not task or _task_is_expired(task) or not _task_matches_schema(task, schema_name):
            raise Http404("Task not found")
        if not _task_access_allowed(request, task, schema_name):
            return JsonResponse({"error": "Task not permitted"}, status=403)

        payload = {
            "task_id": str(task.id),
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "result_reference": task.result_reference,
            "error": task.error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "expires_at": task.expires_at.isoformat() if task.expires_at else None,
        }
        return JsonResponse(payload)


def get_task_urls():
    from django.urls import path

    return [
        path("tasks/<uuid:task_id>/", TaskStatusView.as_view(), name="task-status"),
    ]


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

try:
    from django_q.tasks import async_task
except Exception:
    async_task = None

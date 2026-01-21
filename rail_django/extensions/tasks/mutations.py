"""
Task mutations and decorator.
"""

import inspect
import logging
from typing import Any, Callable, Optional, Union, get_args, get_origin

import graphene
from django.db import transaction
from django.utils import timezone
from graphene.types.generic import GenericScalar
from graphql import GraphQLError

from .models import TaskExecution, TaskStatus
from .config import get_task_settings
from .utils import (
    _resolve_schema_name,
    _snapshot_context,
    _safe_json_payload,
    _safe_json_value,
    _update_task_execution,
)
from .executor import _schedule_task_execution, _call_task_callable
from .queries import TaskExecutionPayloadType

logger = logging.getLogger(__name__)


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


def _callable_path(func: Callable[..., Any]) -> Optional[str]:
    qualname = getattr(func, "__qualname__", "")
    if "<locals>" in qualname:
        return None
    return f"{func.__module__}.{qualname}"


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
                settings_obj = get_task_settings(schema_name)
                if not settings_obj.enabled:
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

                retries = max_retries if max_retries is not None else settings_obj.max_retries
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
                        backend=settings_obj.backend,
                        default_queue=settings_obj.default_queue,
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

                if settings_obj.backend == "sync":
                    _enqueue()
                else:
                    try:
                        transaction.on_commit(_enqueue)
                    except Exception:
                        _enqueue()

                if settings_obj.backend == "sync":
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

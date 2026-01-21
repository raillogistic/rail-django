"""
Internal utility functions for task orchestration.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional, Union

import graphene
from django.conf import settings
from django.utils import timezone
from graphene.types.generic import GenericScalar

from .models import TaskExecution
from .config import get_task_settings, _coerce_bool
from ...config_proxy import get_setting

logger = logging.getLogger(__name__)

_GROUP_NAME_SAFE_RE = re.compile(r"[^0-9A-Za-z_.-]")


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


def _authentication_required(schema_name: Optional[str]) -> bool:
    return _coerce_bool(
        get_setting("schema_settings.authentication_required", False, schema_name),
        False,
    )


def _get_context_user(context: Any) -> Any:
    if context is None:
        return None
    if isinstance(context, dict):
        return context.get("user")
    return getattr(context, "user", None)


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
    context: Any, queryset: Any, schema_name: str
) -> Any:
    user = _get_context_user(context)
    if user and getattr(user, "is_authenticated", False):
        if getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(owner_id=str(user.id))
    if _authentication_required(schema_name):
        return queryset.none()
    return queryset.filter(owner_id__isnull=True)


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


def _build_task_group(schema_name: str, task_id: str) -> str:
    raw = f"rail_task:{schema_name}:{task_id}"
    safe = _GROUP_NAME_SAFE_RE.sub("_", raw)
    return safe[:90]


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


def _emit_task_update(task_id: str, *, schema_name: Optional[str] = None) -> None:
    if schema_name is None:
        task = TaskExecution.objects.filter(pk=task_id).first()
        if task and isinstance(task.metadata, dict):
            schema_name = task.metadata.get("schema_name")
    if not schema_name:
        schema_name = "default"

    settings_obj = get_task_settings(schema_name)
    if not settings_obj.enabled or not settings_obj.emit_subscriptions:
        return

    from .executor import _get_task_subscription_class
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


def get_task_subscription_field(schema_name: str) -> Optional[graphene.Field]:
    settings_obj = get_task_settings(schema_name)
    if not settings_obj.enabled or not settings_obj.emit_subscriptions:
        return None
    from .executor import _get_task_subscription_class
    subscription_class = _get_task_subscription_class()
    if subscription_class is None:
        return None
    return subscription_class.Field()


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
